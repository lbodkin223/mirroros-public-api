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
from flask import Flask, request, jsonify, g, send_from_directory
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
    
    # Initialize monitoring and error tracking
    init_monitoring_and_errors(app)
    
    # Initialize extensions
    init_extensions(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Add request logging
    setup_request_logging(app)
    
    logger.info("MirrorOS Public API Gateway initialized")
    return app

def load_config(app: Flask, config: Dict[str, Any] = None) -> None:
    """Load application configuration using environment-specific settings."""
    from config.production import get_config
    
    # Get configuration class based on environment
    config_class = get_config()
    
    # Load configuration from class
    for key in dir(config_class):
        if key.isupper() and not key.startswith('_'):
            app.config[key] = getattr(config_class, key)
    
    # Override with provided config
    if config:
        app.config.update(config)
    
    # Set version if available
    try:
        from pathlib import Path
        version_file = Path(__file__).parent / 'VERSION'
        if version_file.exists():
            app.config['VERSION'] = version_file.read_text().strip()
    except Exception:
        app.config['VERSION'] = 'unknown'

def init_monitoring_and_errors(app: Flask) -> None:
    """Initialize monitoring and error handling systems."""
    try:
        # Initialize monitoring
        from config.monitoring import init_monitoring
        init_monitoring(app)
        
        # Initialize error handlers
        from utils.error_handlers import register_error_handlers
        register_error_handlers(app)
        
        # Initialize rate limiting
        from utils.rate_limiter import register_rate_limiting
        register_rate_limiting(app)
        
        logger.info("Monitoring and error handling initialized")
        
    except Exception as e:
        logger.error(f"Failed to initialize monitoring/error handling: {e}")
        # Continue without monitoring rather than failing

def init_extensions(app: Flask) -> None:
    """Initialize Flask extensions with graceful error handling."""
    # CORS for iOS app
    CORS(app, origins=[
        "https://mirroros.com",
        "https://*.mirroros.com",
        "http://localhost:3000",  # Development
        "capacitor://localhost",  # iOS Capacitor
        "ionic://localhost",      # Ionic
    ])
    
    try:
        # Database
        init_database(app)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        # Continue without database for now
    
    try:
        # Authentication
        init_auth(app)
        logger.info("Authentication initialized successfully")
    except Exception as e:
        logger.error(f"Authentication initialization failed: {str(e)}")
    
    try:
        # Payments
        init_payments(app)
        logger.info("Payments initialized successfully")
    except Exception as e:
        logger.error(f"Payments initialization failed: {str(e)}")
    
    try:
        # Security
        init_security(app)
        logger.info("Security initialized successfully")
    except Exception as e:
        logger.error(f"Security initialization failed: {str(e)}")
    
    try:
        # Rate limiting
        limiter = Limiter(
            app,
            key_func=get_user_rate_limit_key,
            default_limits=["1000 per hour"]
        )
        app.limiter = limiter
        logger.info("Rate limiter initialized successfully")
    except Exception as e:
        logger.error(f"Rate limiter initialization failed: {str(e)}")

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
    
    # Add static file serving
    @app.route('/')
    def index():
        """Serve the main UI."""
        return send_from_directory('static', 'index.html')
    
    @app.route('/<path:filename>')
    def static_files(filename):
        """Serve static files."""
        return send_from_directory('static', filename)

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
        try:
            from database.models import User
            from sqlalchemy import func
            
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
    
    return app

# Create application instance
app = create_app()

if __name__ == '__main__':
    
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'false').lower() == 'true'
    
    logger.info(f"Starting MirrorOS Public API Gateway on port {port}")
    logger.info(f"Environment: {app.config.get('ENVIRONMENT')}")
    logger.info(f"Debug mode: {debug}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)