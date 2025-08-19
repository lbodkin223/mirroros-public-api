"""
Stripe payment processing for MirrorOS Public API.
Handles subscription creation, webhooks, and billing management.
"""

import logging
import hmac
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from flask import Blueprint, request, jsonify, current_app
import stripe
from stripe.error import StripeError

from database import db
from auth.models import User, Subscription
from auth.middleware import require_auth, get_current_user

# Setup logging
logger = logging.getLogger(__name__)

# Create blueprint
stripe_bp = Blueprint('stripe', __name__)

# Stripe price IDs (configure these in your Stripe dashboard)
STRIPE_PRICE_IDS = {
    'pro_monthly': 'price_pro_monthly_id',
    'pro_yearly': 'price_pro_yearly_id', 
    'enterprise_monthly': 'price_enterprise_monthly_id',
    'enterprise_yearly': 'price_enterprise_yearly_id',
}

def get_tier_from_price_id(price_id: str) -> str:
    """
    Get subscription tier from Stripe price ID.
    
    Args:
        price_id: Stripe price ID
        
    Returns:
        Subscription tier string
    """
    if 'pro' in price_id:
        return 'pro'
    elif 'enterprise' in price_id:
        return 'enterprise'
    return 'free'

def verify_stripe_signature(payload: bytes, sig_header: str, webhook_secret: str) -> bool:
    """
    Verify Stripe webhook signature.
    
    Args:
        payload: Raw request payload
        sig_header: Stripe signature header
        webhook_secret: Webhook secret from Stripe
        
    Returns:
        True if signature is valid, False otherwise
    """
    try:
        stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        return True
    except ValueError:
        logger.error("Invalid Stripe webhook payload")
        return False
    except stripe.error.SignatureVerificationError:
        logger.error("Invalid Stripe webhook signature")
        return False

@stripe_bp.route('/create-checkout-session', methods=['POST'])
@require_auth
def create_checkout_session():
    """
    Create a Stripe checkout session for subscription.
    
    Expected JSON:
        {
            "price_id": "price_pro_monthly_id",
            "success_url": "https://yourapp.com/success",
            "cancel_url": "https://yourapp.com/cancel"
        }
    
    Returns:
        200: Checkout session created with session_id
        400: Validation error
        500: Stripe error
    """
    try:
        user = get_current_user()
        data = request.get_json()
        
        if not data:
            return jsonify({
                'error': 'invalid_request',
                'message': 'Request body must be valid JSON'
            }), 400
        
        price_id = data.get('price_id')
        success_url = data.get('success_url')
        cancel_url = data.get('cancel_url')
        
        if not price_id or not success_url or not cancel_url:
            return jsonify({
                'error': 'missing_parameters',
                'message': 'price_id, success_url, and cancel_url are required'
            }), 400
        
        # Validate price ID
        if price_id not in STRIPE_PRICE_IDS.values():
            return jsonify({
                'error': 'invalid_price_id',
                'message': 'Invalid subscription plan'
            }), 400
        
        # Create checkout session
        session = stripe.checkout.Session.create(
            customer_email=user.email,
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=cancel_url,
            metadata={
                'user_id': str(user.id),
                'user_email': user.email,
            },
            subscription_data={
                'metadata': {
                    'user_id': str(user.id),
                }
            }
        )
        
        logger.info(f"Stripe checkout session created for user {user.email}: {session.id}")
        
        return jsonify({
            'session_id': session.id,
            'url': session.url
        }), 200
        
    except StripeError as e:
        logger.error(f"Stripe error creating checkout session: {str(e)}")
        return jsonify({
            'error': 'stripe_error',
            'message': 'Failed to create checkout session'
        }), 500
        
    except Exception as e:
        logger.error(f"Error creating checkout session: {str(e)}")
        return jsonify({
            'error': 'checkout_session_failed',
            'message': 'Failed to create checkout session'
        }), 500

@stripe_bp.route('/create-portal-session', methods=['POST'])
@require_auth
def create_portal_session():
    """
    Create a Stripe customer portal session for subscription management.
    
    Expected JSON:
        {
            "return_url": "https://yourapp.com/account"
        }
    
    Returns:
        200: Portal session created with session_url
        400: Validation error
        404: No active subscription
        500: Stripe error
    """
    try:
        user = get_current_user()
        data = request.get_json()
        
        if not data:
            return jsonify({
                'error': 'invalid_request',
                'message': 'Request body must be valid JSON'
            }), 400
        
        return_url = data.get('return_url')
        
        if not return_url:
            return jsonify({
                'error': 'missing_return_url',
                'message': 'return_url is required'
            }), 400
        
        # Get user's subscription
        subscription = Subscription.query.filter_by(user_id=user.id).first()
        
        if not subscription or not subscription.stripe_subscription_id:
            return jsonify({
                'error': 'no_subscription',
                'message': 'No active subscription found'
            }), 404
        
        # Get Stripe subscription to find customer ID
        stripe_subscription = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
        customer_id = stripe_subscription.customer
        
        # Create portal session
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        
        logger.info(f"Stripe portal session created for user {user.email}")
        
        return jsonify({
            'url': session.url
        }), 200
        
    except StripeError as e:
        logger.error(f"Stripe error creating portal session: {str(e)}")
        return jsonify({
            'error': 'stripe_error',
            'message': 'Failed to create portal session'
        }), 500
        
    except Exception as e:
        logger.error(f"Error creating portal session: {str(e)}")
        return jsonify({
            'error': 'portal_session_failed',
            'message': 'Failed to create portal session'
        }), 500

@stripe_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """
    Handle Stripe webhooks for subscription events.
    
    Processes events like:
    - customer.subscription.created
    - customer.subscription.updated
    - customer.subscription.deleted
    - invoice.payment_succeeded
    - invoice.payment_failed
    
    Returns:
        200: Webhook processed successfully
        400: Invalid signature or payload
        500: Processing error
    """
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = current_app.config.get('STRIPE_WEBHOOK_SECRET')
    
    if not webhook_secret:
        logger.error("Stripe webhook secret not configured")
        return jsonify({'error': 'webhook_not_configured'}), 500
    
    if not verify_stripe_signature(payload, sig_header, webhook_secret):
        return jsonify({'error': 'invalid_signature'}), 400
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        
        # Handle subscription events
        if event['type'] == 'customer.subscription.created':
            handle_subscription_created(event['data']['object'])
        elif event['type'] == 'customer.subscription.updated':
            handle_subscription_updated(event['data']['object'])
        elif event['type'] == 'customer.subscription.deleted':
            handle_subscription_deleted(event['data']['object'])
        elif event['type'] == 'invoice.payment_succeeded':
            handle_payment_succeeded(event['data']['object'])
        elif event['type'] == 'invoice.payment_failed':
            handle_payment_failed(event['data']['object'])
        else:
            logger.info(f"Unhandled Stripe webhook event: {event['type']}")
        
        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        logger.error(f"Error processing Stripe webhook: {str(e)}")
        return jsonify({'error': 'webhook_processing_failed'}), 500

def handle_subscription_created(subscription_data: Dict[str, Any]) -> None:
    """
    Handle subscription creation webhook.
    
    Args:
        subscription_data: Stripe subscription object
    """
    try:
        user_id = subscription_data['metadata'].get('user_id')
        
        if not user_id:
            logger.error("No user_id in subscription metadata")
            return
        
        user = User.query.get(user_id)
        
        if not user:
            logger.error(f"User not found for subscription: {user_id}")
            return
        
        # Get subscription tier from price
        price_id = subscription_data['items']['data'][0]['price']['id']
        tier = get_tier_from_price_id(price_id)
        
        # Create or update subscription record
        subscription = Subscription.query.filter_by(user_id=user.id).first()
        
        if not subscription:
            subscription = Subscription(user_id=user.id)
            db.session.add(subscription)
        
        subscription.stripe_subscription_id = subscription_data['id']
        subscription.tier = tier
        subscription.status = subscription_data['status']
        subscription.current_period_start = datetime.fromtimestamp(
            subscription_data['current_period_start'], timezone.utc
        )
        subscription.current_period_end = datetime.fromtimestamp(
            subscription_data['current_period_end'], timezone.utc
        )
        
        # Update user tier
        user.tier = tier
        
        db.session.commit()
        
        logger.info(f"Subscription created for user {user.email}: {tier}")
        
    except Exception as e:
        logger.error(f"Error handling subscription created: {str(e)}")
        db.session.rollback()

def handle_subscription_updated(subscription_data: Dict[str, Any]) -> None:
    """
    Handle subscription update webhook.
    
    Args:
        subscription_data: Stripe subscription object
    """
    try:
        subscription = Subscription.query.filter_by(
            stripe_subscription_id=subscription_data['id']
        ).first()
        
        if not subscription:
            logger.error(f"Subscription not found: {subscription_data['id']}")
            return
        
        # Update subscription status and period
        subscription.status = subscription_data['status']
        subscription.current_period_start = datetime.fromtimestamp(
            subscription_data['current_period_start'], timezone.utc
        )
        subscription.current_period_end = datetime.fromtimestamp(
            subscription_data['current_period_end'], timezone.utc
        )
        
        # Update user tier if subscription is active
        if subscription_data['status'] == 'active':
            price_id = subscription_data['items']['data'][0]['price']['id']
            tier = get_tier_from_price_id(price_id)
            subscription.tier = tier
            subscription.user.tier = tier
        else:
            # Downgrade to free if subscription is not active
            subscription.user.tier = 'free'
        
        db.session.commit()
        
        logger.info(f"Subscription updated for user {subscription.user.email}: {subscription.status}")
        
    except Exception as e:
        logger.error(f"Error handling subscription updated: {str(e)}")
        db.session.rollback()

def handle_subscription_deleted(subscription_data: Dict[str, Any]) -> None:
    """
    Handle subscription deletion webhook.
    
    Args:
        subscription_data: Stripe subscription object
    """
    try:
        subscription = Subscription.query.filter_by(
            stripe_subscription_id=subscription_data['id']
        ).first()
        
        if not subscription:
            logger.error(f"Subscription not found: {subscription_data['id']}")
            return
        
        # Update subscription status and downgrade user
        subscription.status = 'canceled'
        subscription.user.tier = 'free'
        
        db.session.commit()
        
        logger.info(f"Subscription canceled for user {subscription.user.email}")
        
    except Exception as e:
        logger.error(f"Error handling subscription deleted: {str(e)}")
        db.session.rollback()

def handle_payment_succeeded(invoice_data: Dict[str, Any]) -> None:
    """
    Handle successful payment webhook.
    
    Args:
        invoice_data: Stripe invoice object
    """
    try:
        subscription_id = invoice_data.get('subscription')
        
        if not subscription_id:
            return
        
        subscription = Subscription.query.filter_by(
            stripe_subscription_id=subscription_id
        ).first()
        
        if subscription:
            logger.info(f"Payment succeeded for user {subscription.user.email}")
            # You can add additional logic here (send receipt email, etc.)
        
    except Exception as e:
        logger.error(f"Error handling payment succeeded: {str(e)}")

def handle_payment_failed(invoice_data: Dict[str, Any]) -> None:
    """
    Handle failed payment webhook.
    
    Args:
        invoice_data: Stripe invoice object
    """
    try:
        subscription_id = invoice_data.get('subscription')
        
        if not subscription_id:
            return
        
        subscription = Subscription.query.filter_by(
            stripe_subscription_id=subscription_id
        ).first()
        
        if subscription:
            logger.warning(f"Payment failed for user {subscription.user.email}")
            # You can add additional logic here (send notification email, etc.)
        
    except Exception as e:
        logger.error(f"Error handling payment failed: {str(e)}")

@stripe_bp.route('/subscription-status', methods=['GET'])
@require_auth
def get_subscription_status():
    """
    Get current user's subscription status.
    
    Returns:
        200: Subscription status information
        404: No subscription found
        500: Server error
    """
    try:
        user = get_current_user()
        subscription = Subscription.query.filter_by(user_id=user.id).first()
        
        if not subscription:
            return jsonify({
                'tier': user.tier,
                'status': 'no_subscription',
                'has_subscription': False
            }), 200
        
        return jsonify({
            'tier': subscription.tier,
            'status': subscription.status,
            'has_subscription': True,
            'is_active': subscription.is_active(),
            'current_period_end': subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            'subscription': subscription.to_dict()
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting subscription status: {str(e)}")
        return jsonify({
            'error': 'status_fetch_failed',
            'message': 'Failed to fetch subscription status'
        }), 500