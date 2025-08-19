"""
Gateway module for MirrorOS Public API.
Handles request proxying to private prediction server.
"""

from flask import Blueprint

from .prediction_proxy import prediction_proxy_bp

# Create combined blueprint for external registration
gateway_bp = Blueprint('gateway', __name__)

# Register sub-blueprints
gateway_bp.register_blueprint(prediction_proxy_bp)

__all__ = ['gateway_bp']