"""
Security module for MirrorOS Public API.
Handles request signing, validation, and security utilities.
"""

from .request_signer import RequestSigner, sign_request, verify_signature

def init_security(app):
    """
    Initialize security components for the Flask app.
    
    Args:
        app: Flask application instance
    """
    # Configure security headers
    @app.after_request
    def add_security_headers(response):
        """Add security headers to all responses."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response
    
    # You can add more security initialization here
    return app

__all__ = ['RequestSigner', 'sign_request', 'verify_signature', 'init_security']