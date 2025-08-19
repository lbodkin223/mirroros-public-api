"""
Authentication module for MirrorOS Public API.
Handles user registration, login, JWT tokens, and session management.
"""

from flask import Flask
from flask_jwt_extended import JWTManager

from .routes import auth_bp
from .middleware import require_auth, get_current_user, get_user_tier_limits

# JWT manager instance
jwt = JWTManager()

def init_auth(app: Flask) -> None:
    """
    Initialize authentication system with Flask app.
    
    Args:
        app: Flask application instance
    """
    # Initialize JWT
    jwt.init_app(app)
    
    # Configure JWT callbacks
    setup_jwt_callbacks(app)

def setup_jwt_callbacks(app: Flask) -> None:
    """Setup JWT error handlers and callbacks."""
    
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return {
            'error': 'token_expired',
            'message': 'The token has expired'
        }, 401
    
    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return {
            'error': 'invalid_token',
            'message': 'The token is invalid'
        }, 401
    
    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return {
            'error': 'authorization_required',
            'message': 'Request does not contain an access token'
        }, 401
    
    @jwt.needs_fresh_token_loader
    def token_not_fresh_callback(jwt_header, jwt_payload):
        return {
            'error': 'fresh_token_required',
            'message': 'The token is not fresh'
        }, 401
    
    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return {
            'error': 'token_revoked',
            'message': 'The token has been revoked'
        }, 401

__all__ = ['auth_bp', 'jwt', 'init_auth', 'require_auth', 'get_current_user', 'get_user_tier_limits']