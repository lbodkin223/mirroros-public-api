#!/usr/bin/env python3
"""
Debug version of MirrorOS Public API to isolate the crashing issue.
"""

import os
import logging
from flask import Flask, jsonify

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    """Create minimal Flask app to test basic functionality."""
    app = Flask(__name__)
    
    # Basic configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    
    @app.route('/')
    def home():
        return jsonify({
            'message': 'MirrorOS Debug API is running!',
            'status': 'healthy',
            'version': 'debug-1.0.0'
        })
    
    @app.route('/health')
    def health():
        return jsonify({
            'status': 'healthy',
            'service': 'mirroros-debug-api'
        })
    
    @app.route('/api/auth/demo-login', methods=['POST'])
    def demo_login():
        """Basic demo login without database dependencies."""
        return jsonify({
            'message': 'Demo login successful',
            'access_token': 'fake-token-for-testing',
            'refresh_token': 'fake-refresh-token',
            'user': {
                'id': 'demo-user-id',
                'email': 'demo@mirroros.com',
                'full_name': 'Demo User',
                'tier': 'free'
            }
        }), 200
    
    logger.info("Debug app created successfully")
    return app

# Create the WSGI application instance
app = create_app()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    app.run(debug=True, host='0.0.0.0', port=port)