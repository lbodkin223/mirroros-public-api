"""
Payment processing module for MirrorOS Public API.
Handles Stripe subscriptions and Apple In-App Purchase validation.
"""

from flask import Flask

from .stripe_handler import stripe_bp
from .apple_validator import apple_bp

def init_payments(app: Flask) -> None:
    """
    Initialize payment processing with Flask app.
    
    Args:
        app: Flask application instance
    """
    # Initialize Stripe
    import stripe
    stripe.api_key = app.config.get('STRIPE_SECRET_KEY')
    
    # Register blueprints
    app.register_blueprint(stripe_bp, url_prefix='/stripe')
    app.register_blueprint(apple_bp, url_prefix='/apple')

# Create combined blueprint for external registration
from flask import Blueprint
payments_bp = Blueprint('payments', __name__)

# Import routes to register them
from . import stripe_handler, apple_validator

__all__ = ['payments_bp', 'init_payments']