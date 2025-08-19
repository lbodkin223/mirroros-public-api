#!/usr/bin/env python3
"""
MirrorOS Public API Gateway
Production-ready Flask application for user management, payments, and prediction proxying.
Deployed to Railway/Heroku - contains NO proprietary algorithms.
"""

import os
import time
import logging
from datetime import timedelta
from typing import Dict, Any
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

# Import our modules
from auth import auth_bp, init_auth
from auth.middleware import require_auth, get_current_user
from payments import payments_bp, init_payments
from database import init_database
from gateway import gateway_bp
from security import init_security

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('mirroros-public.log')
    ]
)
logger = logging.getLogger(__name__)

def create_app(config: Dict[str, Any] = None) -> Flask:
    """
    Application factory pattern for creating Flask app instances.
    
    Args:
        config: Optional configuration dictionary
        
    Returns:
        Configured Flask application instance
    """
    app = Flask(__name__)
    
    # Load configuration
    load_config(app, config)
    
    # Initialize Sentry for error tracking
    if app.config.get('SENTRY_DSN'):
        sentry_sdk.init(
            dsn=app.config['SENTRY_DSN'],
            integrations=[FlaskIntegration()],
            traces_sample_rate=0.1,
        )
    
    # Initialize extensions
    init_extensions(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Add request logging
    setup_request_logging(app)
    
    logger.info("MirrorOS Public API Gateway initialized")
    return app

def load_config(app: Flask, config: Dict[str, Any] = None) -> None:
    """Load application configuration."""
    # Default configuration
    app.config.update({
        'SECRET_KEY': os.getenv('SECRET_KEY', 'dev-secret-change-in-production'),
        'DATABASE_URL': os.getenv('DATABASE_URL', 'postgresql://localhost/mirroros_public'),
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'SQLALCHEMY_ENGINE_OPTIONS': {
            'pool_pre_ping': True,
            'pool_recycle': 300,
        },
        
        # JWT Configuration
        'JWT_SECRET_KEY': os.getenv('JWT_SECRET_KEY', 'jwt-secret-change-in-production'),
        'JWT_ACCESS_TOKEN_EXPIRES': timedelta(hours=24),
        'JWT_REFRESH_TOKEN_EXPIRES': timedelta(days=30),
        
        # Payment Configuration
        'STRIPE_SECRET_KEY': os.getenv('STRIPE_SECRET_KEY'),
        'STRIPE_WEBHOOK_SECRET': os.getenv('STRIPE_WEBHOOK_SECRET'),
        'APPLE_BUNDLE_ID': os.getenv('APPLE_BUNDLE_ID', 'com.mirroros.app'),
        
        # Private API Configuration
        'PRIVATE_API_URL': os.getenv('PRIVATE_API_URL', 'http://localhost:8000'),
        'PRIVATE_API_SECRET': os.getenv('PRIVATE_API_SECRET'),
        
        # Rate Limiting
        'RATELIMIT_STORAGE_URL': os.getenv('REDIS_URL', 'memory://'),
        'RATELIMIT_DEFAULT': "1000 per hour",
        
        # Monitoring
        'SENTRY_DSN': os.getenv('SENTRY_DSN'),
        
        # Environment
        'ENVIRONMENT': os.getenv('ENVIRONMENT', 'development'),
        'DEBUG': os.getenv('DEBUG', 'false').lower() == 'true',
    })
    
    # Override with provided config
    if config:
        app.config.update(config)

def init_extensions(app: Flask) -> None:
    """Initialize Flask extensions."""
    # CORS for iOS app
    CORS(app, origins=[
        "https://mirroros.com",
        "https://*.mirroros.com",
        "http://localhost:3000",  # Development
        "capacitor://localhost",  # iOS Capacitor
        "ionic://localhost",      # Ionic
    ])
    
    # Database
    init_database(app)
    
    # Authentication
    init_auth(app)
    
    # Payments
    init_payments(app)
    
    # Security
    init_security(app)
    
    # Rate limiting
    limiter = Limiter(
        app,
        key_func=get_user_rate_limit_key,
        default_limits=["1000 per hour"]
    )
    app.limiter = limiter

def get_user_rate_limit_key() -> str:
    """Get rate limit key based on authenticated user or IP."""
    user = get_current_user()
    if user:
        return f"user:{user.id}"
    return get_remote_address()

def register_blueprints(app: Flask) -> None:
    """Register application blueprints."""
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(payments_bp, url_prefix='/api/payments')
    app.register_blueprint(gateway_bp, url_prefix='/api')

def register_error_handlers(app: Flask) -> None:
    """Register error handlers."""
    
    @app.errorhandler(400)
    def bad_request(error):
        logger.warning(f"Bad request: {request.url}")
        return jsonify({
            'error': 'Bad request',
            'message': 'The request could not be understood by the server'
        }), 400
    
    @app.errorhandler(401)
    def unauthorized(error):
        logger.warning(f"Unauthorized access attempt: {request.url}")
        return jsonify({
            'error': 'Unauthorized',
            'message': 'Authentication required'
        }), 401
    
    @app.errorhandler(403)
    def forbidden(error):
        logger.warning(f"Forbidden access attempt: {request.url}")
        return jsonify({
            'error': 'Forbidden',
            'message': 'Insufficient permissions'
        }), 403
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'error': 'Not found',
            'message': 'The requested resource was not found'
        }), 404
    
    @app.errorhandler(429)
    def ratelimit_handler(e):
        user = get_current_user()
        user_info = f"user:{user.id}" if user else f"ip:{get_remote_address()}"
        logger.warning(f"Rate limit exceeded for {user_info}")
        return jsonify({
            'error': 'Rate limit exceeded',
            'message': 'Too many requests. Please try again later.',
            'retry_after': e.retry_after if hasattr(e, 'retry_after') else 3600
        }), 429
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {str(error)}")
        return jsonify({
            'error': 'Internal server error',
            'message': 'An unexpected error occurred'
        }), 500

def setup_request_logging(app: Flask) -> None:
    """Setup request and response logging."""
    
    @app.before_request
    def log_request_info():
        """Log incoming requests (excluding sensitive data)."""
        # Skip logging for health checks
        if request.endpoint in ['health', 'metrics']:
            return
        
        # Get user info if available
        user = get_current_user()
        user_info = f"user:{user.id}" if user else f"ip:{get_remote_address()}"
        
        # Log request
        logger.info(f"Request: {request.method} {request.path} from {user_info}")
        
        # Store request start time
        g.start_time = time.time()
    
    @app.after_request
    def log_response_info(response):
        """Log response information."""
        # Skip logging for health checks
        if request.endpoint in ['health', 'metrics']:
            return response
        
        # Calculate response time
        if hasattr(g, 'start_time'):
            response_time = (time.time() - g.start_time) * 1000
            response.headers['X-Response-Time'] = f"{response_time:.2f}ms"
        
        # Log response
        user = get_current_user()
        user_info = f"user:{user.id}" if user else f"ip:{get_remote_address()}"
        logger.info(f"Response: {response.status_code} for {request.method} {request.path} from {user_info}")
        
        return response

# Health check and monitoring endpoints
@app.route('/health')
def health():
    """Health check endpoint for load balancers."""
    return jsonify({
        'status': 'healthy',
        'service': 'mirroros-public-api',
        'version': '1.0.0',
        'environment': app.config.get('ENVIRONMENT', 'unknown')
    })

@app.route('/metrics')
def metrics():
    """Basic metrics endpoint."""
    from database.models import User
    from sqlalchemy import func
    
    try:
        total_users = User.query.count()
        active_users = User.query.filter(User.is_active == True).count()
        
        return jsonify({
            'users': {
                'total': total_users,
                'active': active_users
            },
            'status': 'operational'
        })
    except Exception as e:
        logger.error(f"Metrics error: {str(e)}")
        return jsonify({'status': 'error'}), 500

# Create application instance
app = create_app()

if __name__ == '__main__':
    
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'false').lower() == 'true'
    
    logger.info(f"Starting MirrorOS Public API Gateway on port {port}")
    logger.info(f"Environment: {app.config.get('ENVIRONMENT')}")
    logger.info(f"Debug mode: {debug}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)