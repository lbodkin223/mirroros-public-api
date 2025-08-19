#!/usr/bin/env python3
"""
MirrorOS Public API Gateway - Minimal Version
Simple Flask app to test Railway deployment first.
"""

import os
from flask import Flask, jsonify
from flask_cors import CORS


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Basic configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    
    # Enable CORS
    CORS(app)
    
    @app.route('/')
    def home():
        return jsonify({
            'message': 'MirrorOS Public API is running!',
            'status': 'healthy',
            'version': '1.0.0'
        })
    
    @app.route('/health')
    def health():
        return jsonify({
            'status': 'healthy',
            'service': 'mirroros-public-api'
        })
    
    return app


# For development
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=8000)