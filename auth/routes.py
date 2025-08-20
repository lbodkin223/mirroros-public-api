"""
Authentication routes for MirrorOS Public API.
Handles user registration, login, logout, and profile management.
"""

import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from sqlalchemy.exc import IntegrityError

from database import db
from .models import User, Whitelist
from .middleware import require_auth, get_current_user

# Setup logging
logger = logging.getLogger(__name__)

# Create blueprint
auth_bp = Blueprint('auth', __name__)

def validate_email(email: str) -> bool:
    """
    Validate email format using regex.
    
    Args:
        email: Email address to validate
        
    Returns:
        True if email is valid, False otherwise
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password: str) -> Dict[str, Any]:
    """
    Validate password strength.
    
    Args:
        password: Password to validate
        
    Returns:
        Dictionary with validation result and errors
    """
    errors = []
    
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")
    
    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")
    
    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")
    
    if not re.search(r'\d', password):
        errors.append("Password must contain at least one number")
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }

@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register a new user account.
    
    Expected JSON:
        {
            "email": "user@example.com",
            "password": "SecurePassword123",
            "full_name": "John Doe"  // optional
        }
    
    Returns:
        201: User created successfully with access/refresh tokens
        400: Validation error
        409: User already exists
        500: Server error
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'error': 'invalid_request',
                'message': 'Request body must be valid JSON'
            }), 400
        
        # Extract and validate required fields
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        full_name = data.get('full_name', '').strip()
        
        if not email or not password:
            return jsonify({
                'error': 'missing_fields',
                'message': 'Email and password are required'
            }), 400
        
        # Validate email format
        if not validate_email(email):
            return jsonify({
                'error': 'invalid_email',
                'message': 'Please provide a valid email address'
            }), 400
        
        # Validate password strength
        password_validation = validate_password(password)
        if not password_validation['valid']:
            return jsonify({
                'error': 'weak_password',
                'message': 'Password does not meet requirements',
                'details': password_validation['errors']
            }), 400
        
        # Check if email is whitelisted
        if not Whitelist.is_email_whitelisted(email):
            logger.warning(f"Registration attempt with non-whitelisted email: {email}")
            return jsonify({
                'error': 'email_not_whitelisted',
                'message': 'This email is not authorized for registration. Contact admin for access.'
            }), 403
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({
                'error': 'user_exists',
                'message': 'An account with this email already exists'
            }), 409
        
        # Create new user
        user = User(
            email=email,
            password=password,
            full_name=full_name if full_name else None
        )
        
        db.session.add(user)
        db.session.commit()
        
        # Mark whitelist entry as used
        Whitelist.use_whitelist_entry(email, user.id)
        
        # Create tokens
        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))
        
        logger.info(f"New user registered: {email}")
        
        return jsonify({
            'message': 'User registered successfully',
            'user': user.to_dict(),
            'access_token': access_token,
            'refresh_token': refresh_token
        }), 201
        
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'error': 'user_exists',
            'message': 'An account with this email already exists'
        }), 409
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Registration error: {str(e)}")
        return jsonify({
            'error': 'registration_failed',
            'message': 'Failed to create account'
        }), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Authenticate user and return tokens.
    
    Expected JSON:
        {
            "email": "user@example.com",
            "password": "SecurePassword123"
        }
    
    Returns:
        200: Login successful with access/refresh tokens
        400: Validation error
        401: Invalid credentials
        500: Server error
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'error': 'invalid_request',
                'message': 'Request body must be valid JSON'
            }), 400
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({
                'error': 'missing_credentials',
                'message': 'Email and password are required'
            }), 400
        
        # Find user by email
        user = User.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            logger.warning(f"Failed login attempt for email: {email}")
            return jsonify({
                'error': 'invalid_credentials',
                'message': 'Invalid email or password'
            }), 401
        
        if not user.is_active:
            return jsonify({
                'error': 'account_deactivated',
                'message': 'Your account has been deactivated'
            }), 401
        
        # Update last login timestamp
        user.update_last_login()
        
        # Create tokens
        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))
        
        logger.info(f"User logged in: {email}")
        
        return jsonify({
            'message': 'Login successful',
            'user': user.to_dict(),
            'access_token': access_token,
            'refresh_token': refresh_token
        }), 200
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({
            'error': 'login_failed',
            'message': 'Login failed'
        }), 500

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """
    Refresh access token using refresh token.
    
    Returns:
        200: New access token
        401: Invalid refresh token
        404: User not found
        500: Server error
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or not user.is_active:
            return jsonify({
                'error': 'user_not_found',
                'message': 'User not found or deactivated'
            }), 404
        
        # Create new access token
        access_token = create_access_token(identity=str(user.id))
        
        return jsonify({
            'access_token': access_token
        }), 200
        
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        return jsonify({
            'error': 'refresh_failed',
            'message': 'Failed to refresh token'
        }), 500

@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """
    Logout user (client should discard tokens).
    
    Returns:
        200: Logout successful
    """
    # In a production system, you might want to implement token blacklisting
    # For now, we rely on the client to discard the tokens
    
    user = get_current_user()
    if user:
        logger.info(f"User logged out: {user.email}")
    
    return jsonify({
        'message': 'Logout successful'
    }), 200

@auth_bp.route('/profile', methods=['GET'])
@require_auth
def get_profile():
    """
    Get current user's profile information.
    
    Returns:
        200: User profile data
        404: User not found
        500: Server error
    """
    try:
        user = get_current_user()
        
        if not user:
            return jsonify({
                'error': 'user_not_found',
                'message': 'User not found'
            }), 404
        
        return jsonify({
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        logger.error(f"Get profile error: {str(e)}")
        return jsonify({
            'error': 'profile_fetch_failed',
            'message': 'Failed to fetch profile'
        }), 500

@auth_bp.route('/profile', methods=['PUT'])
@require_auth
def update_profile():
    """
    Update user's profile information.
    
    Expected JSON:
        {
            "full_name": "New Name",
            "email": "new@example.com"  // optional
        }
    
    Returns:
        200: Profile updated successfully
        400: Validation error
        404: User not found
        409: Email already in use
        500: Server error
    """
    try:
        user = get_current_user()
        
        if not user:
            return jsonify({
                'error': 'user_not_found',
                'message': 'User not found'
            }), 404
        
        data = request.get_json()
        
        if not data:
            return jsonify({
                'error': 'invalid_request',
                'message': 'Request body must be valid JSON'
            }), 400
        
        # Update full name
        if 'full_name' in data:
            full_name = data['full_name'].strip() if data['full_name'] else None
            user.full_name = full_name
        
        # Update email (with validation)
        if 'email' in data:
            new_email = data['email'].strip().lower()
            
            if not validate_email(new_email):
                return jsonify({
                    'error': 'invalid_email',
                    'message': 'Please provide a valid email address'
                }), 400
            
            # Check if email is already in use by another user
            if new_email != user.email:
                existing_user = User.query.filter_by(email=new_email).first()
                if existing_user:
                    return jsonify({
                        'error': 'email_in_use',
                        'message': 'This email is already in use'
                    }), 409
                
                user.email = new_email
                user.is_verified = False  # Reset verification status
        
        user.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        
        logger.info(f"Profile updated for user: {user.email}")
        
        return jsonify({
            'message': 'Profile updated successfully',
            'user': user.to_dict()
        }), 200
        
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'error': 'email_in_use',
            'message': 'This email is already in use'
        }), 409
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Profile update error: {str(e)}")
        return jsonify({
            'error': 'profile_update_failed',
            'message': 'Failed to update profile'
        }), 500

@auth_bp.route('/change-password', methods=['POST'])
@require_auth
def change_password():
    """
    Change user's password.
    
    Expected JSON:
        {
            "current_password": "OldPassword123",
            "new_password": "NewPassword123"
        }
    
    Returns:
        200: Password changed successfully
        400: Validation error
        401: Current password incorrect
        404: User not found
        500: Server error
    """
    try:
        user = get_current_user()
        
        if not user:
            return jsonify({
                'error': 'user_not_found',
                'message': 'User not found'
            }), 404
        
        data = request.get_json()
        
        if not data:
            return jsonify({
                'error': 'invalid_request',
                'message': 'Request body must be valid JSON'
            }), 400
        
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')
        
        if not current_password or not new_password:
            return jsonify({
                'error': 'missing_passwords',
                'message': 'Current and new password are required'
            }), 400
        
        # Verify current password
        if not user.check_password(current_password):
            return jsonify({
                'error': 'incorrect_current_password',
                'message': 'Current password is incorrect'
            }), 401
        
        # Validate new password
        password_validation = validate_password(new_password)
        if not password_validation['valid']:
            return jsonify({
                'error': 'weak_password',
                'message': 'New password does not meet requirements',
                'details': password_validation['errors']
            }), 400
        
        # Update password
        user.set_password(new_password)
        user.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        
        logger.info(f"Password changed for user: {user.email}")
        
        return jsonify({
            'message': 'Password changed successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Password change error: {str(e)}")
        return jsonify({
            'error': 'password_change_failed',
            'message': 'Failed to change password'
        }), 500

@auth_bp.route('/usage', methods=['GET'])
@require_auth
def get_usage():
    """
    Get current user's usage statistics.
    
    Returns:
        200: Usage statistics
        404: User not found
        500: Server error
    """
    try:
        user = get_current_user()
        
        if not user:
            return jsonify({
                'error': 'user_not_found',
                'message': 'User not found'
            }), 404
        
        limits = user.get_tier_limits()
        
        # Calculate usage percentages
        daily_usage_percent = 0
        if limits['predictions_per_day'] > 0:
            daily_usage_percent = (user.predictions_used_today / limits['predictions_per_day']) * 100
        
        return jsonify({
            'tier': user.tier,
            'limits': limits,
            'usage': {
                'predictions_used_today': user.predictions_used_today,
                'daily_usage_percent': round(daily_usage_percent, 1),
                'can_make_prediction': user.can_make_prediction(),
                'last_reset_date': user.last_reset_date.isoformat() if user.last_reset_date else None
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Usage fetch error: {str(e)}")
        return jsonify({
            'error': 'usage_fetch_failed',
            'message': 'Failed to fetch usage statistics'
        }), 500

@auth_bp.route('/demo-login', methods=['POST'])
def demo_login():
    """
    Demo login endpoint for testing without database constraints.
    Returns a JWT token for testing purposes.
    """
    try:
        # Create a demo JWT token
        demo_user_id = "demo-user-123"
        access_token = create_access_token(
            identity=demo_user_id,
            expires_delta=timedelta(hours=24)
        )
        
        logger.info("Demo login successful")
        return jsonify({
            'access_token': access_token,
            'user': {
                'id': demo_user_id,
                'email': 'demo@mirroros.com',
                'name': 'Demo User',
                'tier': 'free'
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Demo login error: {str(e)}")
        return jsonify({
            'error': 'demo_login_failed',
            'message': 'Demo login failed'
        }), 500