"""
Authentication middleware for MirrorOS Public API.
JWT token verification and user context management.
"""

import logging
from functools import wraps
from typing import Optional, Dict, Any
from flask import request, jsonify, g
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request

from .models import User

# Setup logging
logger = logging.getLogger(__name__)

def get_current_user() -> Optional[User]:
    """
    Get the currently authenticated user from the request context.
    
    Returns:
        User object if authenticated, None otherwise
    """
    try:
        # Check if user is already cached in request context
        if hasattr(g, 'current_user'):
            return g.current_user
        
        # Verify JWT token and get user ID
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        
        if not user_id:
            return None
        
        # Handle demo user fallback case
        if user_id == 'demo-user-12345':
            # Create a mock user object for demo purposes
            from .models import User
            from datetime import datetime, timezone
            
            class DemoUser(User):
                def __init__(self):
                    super().__init__(email='demo@mirroros.com', full_name='Demo User')
                    self.id = user_id
                    self.tier = 'free'
                    self.is_verified = True
                    self.is_active = True
                    self.predictions_used_today = 0
                    self.last_reset_date = datetime.now(timezone.utc).date()
                
                def increment_prediction_usage(self) -> None:
                    """Mock increment for demo user."""
                    self.predictions_used_today += 1
                
                def can_make_prediction(self) -> bool:
                    """Mock check for demo user - always allow."""
                    return True
                
                def get_tier_limits(self):
                    """Mock tier limits for demo user."""
                    return {
                        'predictions_per_day': 10,
                        'max_requests_per_hour': 20
                    }
            
            demo_user = DemoUser()
            g.current_user = demo_user
            return demo_user
        
        # Fetch and cache user
        user = User.query.filter_by(id=user_id, is_active=True).first()
        g.current_user = user
        
        return user
        
    except Exception as e:
        logger.debug(f"Failed to get current user: {str(e)}")
        return None

def require_auth(f):
    """
    Decorator to require JWT authentication for routes.
    
    Args:
        f: Function to wrap
        
    Returns:
        Wrapped function that requires authentication
    """
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        
        if not user:
            return jsonify({
                'error': 'user_not_found',
                'message': 'Authentication required'
            }), 401
        
        return f(*args, **kwargs)
    
    return decorated_function

def require_verified_user(f):
    """
    Decorator to require email-verified user for routes.
    
    Args:
        f: Function to wrap
        
    Returns:
        Wrapped function that requires verified user
    """
    @wraps(f)
    @require_auth
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        
        if not user.is_verified:
            return jsonify({
                'error': 'email_verification_required',
                'message': 'Please verify your email address first'
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated_function

def require_tier(minimum_tier: str):
    """
    Decorator to require minimum subscription tier for routes.
    
    Args:
        minimum_tier: Minimum required tier (free, pro, enterprise)
        
    Returns:
        Decorator function
    """
    tier_hierarchy = {'free': 0, 'pro': 1, 'enterprise': 2}
    
    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            
            user_tier_level = tier_hierarchy.get(user.tier, 0)
            required_tier_level = tier_hierarchy.get(minimum_tier, 0)
            
            if user_tier_level < required_tier_level:
                return jsonify({
                    'error': 'insufficient_tier',
                    'message': f'This feature requires {minimum_tier} tier or higher',
                    'current_tier': user.tier,
                    'required_tier': minimum_tier
                }), 403
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def check_rate_limit(f):
    """
    Decorator to check user's rate limits before allowing request.
    
    Args:
        f: Function to wrap
        
    Returns:
        Wrapped function that checks rate limits
    """
    @wraps(f)
    @require_auth
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        
        if not user.can_make_prediction():
            limits = user.get_tier_limits()
            
            return jsonify({
                'error': 'rate_limit_exceeded',
                'message': 'Daily prediction limit reached',
                'current_usage': user.predictions_used_today,
                'daily_limit': limits['predictions_per_day'],
                'tier': user.tier
            }), 429
        
        return f(*args, **kwargs)
    
    return decorated_function

def get_user_tier_limits(user_id: str = None) -> Dict[str, int]:
    """
    Get tier limits for a specific user or current user.
    
    Args:
        user_id: Optional user ID, uses current user if not provided
        
    Returns:
        Dictionary with tier limits
    """
    if user_id:
        user = User.query.filter_by(id=user_id, is_active=True).first()
    else:
        user = get_current_user()
    
    if not user:
        # Return free tier limits for unauthenticated users
        return {
            'predictions_per_day': 3,
            'max_requests_per_hour': 10,
        }
    
    return user.get_tier_limits()

def log_user_activity(activity_type: str, details: Dict[str, Any] = None):
    """
    Log user activity for analytics and monitoring.
    
    Args:
        activity_type: Type of activity (login, prediction, etc.)
        details: Optional additional details
    """
    try:
        user = get_current_user()
        
        log_data = {
            'activity_type': activity_type,
            'user_id': str(user.id) if user else None,
            'user_tier': user.tier if user else 'anonymous',
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', 'Unknown'),
        }
        
        if details:
            log_data.update(details)
        
        logger.info(f"User activity: {log_data}")
        
    except Exception as e:
        logger.error(f"Failed to log user activity: {str(e)}")

def validate_request_source():
    """
    Validate that the request is coming from an authorized source.
    Can be used to restrict API access to specific domains or apps.
    
    Returns:
        True if request source is valid, False otherwise
    """
    # Get the origin header
    origin = request.headers.get('Origin')
    referer = request.headers.get('Referer')
    
    # List of allowed origins (configure based on your frontend domains)
    allowed_origins = [
        'https://mirroros.com',
        'https://app.mirroros.com',
        'http://localhost:3000',  # Development
        'capacitor://localhost',   # iOS app
        'ionic://localhost',       # Ionic app
    ]
    
    # Allow requests without origin (mobile apps, API calls)
    if not origin and not referer:
        return True
    
    # Check if origin is in allowed list
    if origin in allowed_origins:
        return True
    
    # Check referer as fallback
    if referer:
        for allowed_origin in allowed_origins:
            if referer.startswith(allowed_origin):
                return True
    
    return False

def require_valid_source(f):
    """
    Decorator to require requests from valid sources only.
    
    Args:
        f: Function to wrap
        
    Returns:
        Wrapped function that validates request source
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not validate_request_source():
            logger.warning(f"Request from invalid source: {request.headers.get('Origin', 'Unknown')}")
            return jsonify({
                'error': 'invalid_source',
                'message': 'Request not allowed from this source'
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated_function