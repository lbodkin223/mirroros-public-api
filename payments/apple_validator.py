"""
Apple In-App Purchase receipt validation for MirrorOS Public API.
Handles iOS subscription validation and status updates.
"""

import logging
import json
import base64
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
import requests
from flask import Blueprint, request, jsonify, current_app

from database import db
from auth.models import User, Subscription
from auth.middleware import require_auth, get_current_user

# Setup logging
logger = logging.getLogger(__name__)

# Create blueprint
apple_bp = Blueprint('apple', __name__)

# Apple App Store URLs
APPLE_SANDBOX_URL = 'https://sandbox.itunes.apple.com/verifyReceipt'
APPLE_PRODUCTION_URL = 'https://buy.itunes.apple.com/verifyReceipt'

# Apple product IDs mapping to tiers
APPLE_PRODUCT_IDS = {
    'com.mirroros.pro.monthly': 'pro',
    'com.mirroros.pro.yearly': 'pro',
    'com.mirroros.enterprise.monthly': 'enterprise',
    'com.mirroros.enterprise.yearly': 'enterprise',
}

def validate_receipt_with_apple(receipt_data: str, is_sandbox: bool = False) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Validate receipt with Apple's servers.
    
    Args:
        receipt_data: Base64 encoded receipt data
        is_sandbox: Whether to use sandbox environment
        
    Returns:
        Tuple of (is_valid, receipt_info)
    """
    url = APPLE_SANDBOX_URL if is_sandbox else APPLE_PRODUCTION_URL
    
    payload = {
        'receipt-data': receipt_data,
        'password': current_app.config.get('APPLE_SHARED_SECRET'),  # Your app's shared secret
        'exclude-old-transactions': True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        status = result.get('status', -1)
        
        # Status 0 means valid receipt
        if status == 0:
            return True, result
        
        # Status 21007 means this receipt is from sandbox but sent to production
        if status == 21007 and not is_sandbox:
            logger.info("Receipt is from sandbox, retrying with sandbox URL")
            return validate_receipt_with_apple(receipt_data, is_sandbox=True)
        
        # Status 21008 means this receipt is from production but sent to sandbox
        if status == 21008 and is_sandbox:
            logger.info("Receipt is from production, retrying with production URL")
            return validate_receipt_with_apple(receipt_data, is_sandbox=False)
        
        logger.warning(f"Apple receipt validation failed with status: {status}")
        return False, None
        
    except requests.RequestException as e:
        logger.error(f"Error validating receipt with Apple: {str(e)}")
        return False, None
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing Apple response: {str(e)}")
        return False, None

def get_latest_receipt_info(receipt_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract the latest receipt info from Apple's response.
    
    Args:
        receipt_data: Receipt data from Apple
        
    Returns:
        Latest receipt info or None
    """
    try:
        # Get latest receipt info (for auto-renewable subscriptions)
        latest_receipt_info = receipt_data.get('latest_receipt_info', [])
        
        if not latest_receipt_info:
            # Fallback to in_app purchases
            in_app = receipt_data.get('receipt', {}).get('in_app', [])
            if in_app:
                latest_receipt_info = in_app
        
        if not latest_receipt_info:
            return None
        
        # Find the most recent transaction
        latest_transaction = max(
            latest_receipt_info,
            key=lambda x: int(x.get('purchase_date_ms', 0))
        )
        
        return latest_transaction
        
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Error extracting latest receipt info: {str(e)}")
        return None

def is_subscription_active(transaction: Dict[str, Any]) -> bool:
    """
    Check if a subscription transaction is currently active.
    
    Args:
        transaction: Transaction data from Apple
        
    Returns:
        True if subscription is active, False otherwise
    """
    try:
        # Check if there's an expiration date
        expires_date_ms = transaction.get('expires_date_ms')
        
        if not expires_date_ms:
            # Non-subscription purchase
            return True
        
        # Convert to datetime and compare with current time
        expires_date = datetime.fromtimestamp(int(expires_date_ms) / 1000, timezone.utc)
        current_time = datetime.now(timezone.utc)
        
        return current_time < expires_date
        
    except (ValueError, TypeError) as e:
        logger.error(f"Error checking subscription status: {str(e)}")
        return False

def get_tier_from_product_id(product_id: str) -> str:
    """
    Get subscription tier from Apple product ID.
    
    Args:
        product_id: Apple product identifier
        
    Returns:
        Subscription tier string
    """
    return APPLE_PRODUCT_IDS.get(product_id, 'free')

@apple_bp.route('/validate-receipt', methods=['POST'])
@require_auth
def validate_receipt():
    """
    Validate Apple In-App Purchase receipt and update user subscription.
    
    Expected JSON:
        {
            "receipt_data": "base64_encoded_receipt",
            "transaction_id": "1000000123456789"  // optional
        }
    
    Returns:
        200: Receipt validation successful
        400: Invalid receipt data
        500: Validation error
    """
    try:
        user = get_current_user()
        data = request.get_json()
        
        if not data:
            return jsonify({
                'error': 'invalid_request',
                'message': 'Request body must be valid JSON'
            }), 400
        
        receipt_data = data.get('receipt_data')
        transaction_id = data.get('transaction_id')
        
        if not receipt_data:
            return jsonify({
                'error': 'missing_receipt_data',
                'message': 'receipt_data is required'
            }), 400
        
        # Validate receipt with Apple
        is_valid, receipt_info = validate_receipt_with_apple(receipt_data)
        
        if not is_valid or not receipt_info:
            return jsonify({
                'error': 'invalid_receipt',
                'message': 'Receipt validation failed'
            }), 400
        
        # Extract latest transaction info
        latest_transaction = get_latest_receipt_info(receipt_info)
        
        if not latest_transaction:
            return jsonify({
                'error': 'no_transaction_found',
                'message': 'No valid transaction found in receipt'
            }), 400
        
        # Get product info
        product_id = latest_transaction.get('product_id')
        actual_transaction_id = latest_transaction.get('transaction_id')
        
        if not product_id:
            return jsonify({
                'error': 'invalid_product',
                'message': 'Product ID not found in receipt'
            }), 400
        
        # Verify transaction ID if provided
        if transaction_id and actual_transaction_id != transaction_id:
            return jsonify({
                'error': 'transaction_id_mismatch',
                'message': 'Transaction ID does not match receipt'
            }), 400
        
        # Get tier from product ID
        tier = get_tier_from_product_id(product_id)
        
        if tier == 'free':
            return jsonify({
                'error': 'unknown_product',
                'message': 'Unknown product ID'
            }), 400
        
        # Check if subscription is active
        is_active = is_subscription_active(latest_transaction)
        
        # Update or create subscription
        subscription = Subscription.query.filter_by(user_id=user.id).first()
        
        if not subscription:
            subscription = Subscription(user_id=user.id)
            db.session.add(subscription)
        
        subscription.apple_transaction_id = actual_transaction_id
        subscription.tier = tier if is_active else 'free'
        subscription.status = 'active' if is_active else 'expired'
        
        # Set subscription period if available
        if latest_transaction.get('purchase_date_ms'):
            subscription.current_period_start = datetime.fromtimestamp(
                int(latest_transaction['purchase_date_ms']) / 1000, timezone.utc
            )
        
        if latest_transaction.get('expires_date_ms'):
            subscription.current_period_end = datetime.fromtimestamp(
                int(latest_transaction['expires_date_ms']) / 1000, timezone.utc
            )
        
        # Update user tier
        user.tier = subscription.tier
        
        db.session.commit()
        
        logger.info(f"Apple receipt validated for user {user.email}: {tier} ({'active' if is_active else 'expired'})")
        
        return jsonify({
            'message': 'Receipt validated successfully',
            'tier': subscription.tier,
            'status': subscription.status,
            'is_active': is_active,
            'product_id': product_id,
            'transaction_id': actual_transaction_id,
            'expires_date': subscription.current_period_end.isoformat() if subscription.current_period_end else None
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error validating Apple receipt: {str(e)}")
        return jsonify({
            'error': 'validation_failed',
            'message': 'Receipt validation failed'
        }), 500

@apple_bp.route('/subscription-status', methods=['GET'])
@require_auth
def get_apple_subscription_status():
    """
    Get current user's Apple subscription status.
    
    Returns:
        200: Subscription status information
        404: No subscription found
        500: Server error
    """
    try:
        user = get_current_user()
        subscription = Subscription.query.filter_by(user_id=user.id).first()
        
        if not subscription or not subscription.apple_transaction_id:
            return jsonify({
                'tier': user.tier,
                'status': 'no_subscription',
                'has_apple_subscription': False
            }), 200
        
        return jsonify({
            'tier': subscription.tier,
            'status': subscription.status,
            'has_apple_subscription': True,
            'is_active': subscription.is_active(),
            'transaction_id': subscription.apple_transaction_id,
            'current_period_end': subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            'subscription': subscription.to_dict()
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting Apple subscription status: {str(e)}")
        return jsonify({
            'error': 'status_fetch_failed',
            'message': 'Failed to fetch subscription status'
        }), 500

@apple_bp.route('/restore-purchases', methods=['POST'])
@require_auth
def restore_purchases():
    """
    Restore Apple In-App Purchases for the current user.
    
    Expected JSON:
        {
            "receipt_data": "base64_encoded_receipt"
        }
    
    Returns:
        200: Purchases restored successfully
        400: Invalid receipt data
        500: Restoration error
    """
    try:
        user = get_current_user()
        data = request.get_json()
        
        if not data:
            return jsonify({
                'error': 'invalid_request',
                'message': 'Request body must be valid JSON'
            }), 400
        
        receipt_data = data.get('receipt_data')
        
        if not receipt_data:
            return jsonify({
                'error': 'missing_receipt_data',
                'message': 'receipt_data is required'
            }), 400
        
        # Validate receipt with Apple
        is_valid, receipt_info = validate_receipt_with_apple(receipt_data)
        
        if not is_valid or not receipt_info:
            return jsonify({
                'error': 'invalid_receipt',
                'message': 'Receipt validation failed'
            }), 400
        
        # Get all transactions from receipt
        latest_receipt_info = receipt_info.get('latest_receipt_info', [])
        
        if not latest_receipt_info:
            in_app = receipt_info.get('receipt', {}).get('in_app', [])
            latest_receipt_info = in_app
        
        if not latest_receipt_info:
            return jsonify({
                'message': 'No purchases found to restore',
                'restored_purchases': []
            }), 200
        
        restored_purchases = []
        highest_tier = 'free'
        active_subscription = None
        
        # Process all transactions to find the highest active tier
        for transaction in latest_receipt_info:
            product_id = transaction.get('product_id')
            
            if not product_id:
                continue
            
            tier = get_tier_from_product_id(product_id)
            
            if tier != 'free':
                is_active = is_subscription_active(transaction)
                
                restored_purchases.append({
                    'product_id': product_id,
                    'tier': tier,
                    'transaction_id': transaction.get('transaction_id'),
                    'is_active': is_active,
                    'purchase_date': datetime.fromtimestamp(
                        int(transaction.get('purchase_date_ms', 0)) / 1000, timezone.utc
                    ).isoformat() if transaction.get('purchase_date_ms') else None,
                    'expires_date': datetime.fromtimestamp(
                        int(transaction.get('expires_date_ms', 0)) / 1000, timezone.utc
                    ).isoformat() if transaction.get('expires_date_ms') else None
                })
                
                # Track highest active tier
                if is_active:
                    tier_priority = {'pro': 1, 'enterprise': 2}
                    current_priority = tier_priority.get(highest_tier, 0)
                    new_priority = tier_priority.get(tier, 0)
                    
                    if new_priority > current_priority:
                        highest_tier = tier
                        active_subscription = transaction
        
        # Update user's subscription if we found an active one
        if active_subscription and highest_tier != 'free':
            subscription = Subscription.query.filter_by(user_id=user.id).first()
            
            if not subscription:
                subscription = Subscription(user_id=user.id)
                db.session.add(subscription)
            
            subscription.apple_transaction_id = active_subscription.get('transaction_id')
            subscription.tier = highest_tier
            subscription.status = 'active'
            
            if active_subscription.get('purchase_date_ms'):
                subscription.current_period_start = datetime.fromtimestamp(
                    int(active_subscription['purchase_date_ms']) / 1000, timezone.utc
                )
            
            if active_subscription.get('expires_date_ms'):
                subscription.current_period_end = datetime.fromtimestamp(
                    int(active_subscription['expires_date_ms']) / 1000, timezone.utc
                )
            
            user.tier = highest_tier
            db.session.commit()
        
        logger.info(f"Purchases restored for user {user.email}: {len(restored_purchases)} purchases, highest tier: {highest_tier}")
        
        return jsonify({
            'message': f'Successfully restored {len(restored_purchases)} purchases',
            'restored_purchases': restored_purchases,
            'current_tier': highest_tier,
            'active_subscription_found': highest_tier != 'free'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error restoring Apple purchases: {str(e)}")
        return jsonify({
            'error': 'restore_failed',
            'message': 'Failed to restore purchases'
        }), 500