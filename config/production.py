"""
Production environment configuration for MirrorOS Public API.
Handles environment variables, secrets management, and deployment settings.
"""

import os
import secrets
from datetime import timedelta
from typing import Dict, Any, Optional

class ProductionConfig:
    """Production configuration with security best practices."""
    
    # Flask Core Settings
    ENV = 'production'
    DEBUG = False
    TESTING = False
    
    # Security Settings
    SECRET_KEY = os.getenv('SECRET_KEY') or secrets.token_hex(32)
    
    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 20,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
        'pool_timeout': 30,
        'max_overflow': 30
    }
    
    # JWT Configuration
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY') or secrets.token_hex(32)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_ALGORITHM = 'HS256'
    
    # Private API Configuration
    PRIVATE_API_URL = os.getenv('PRIVATE_API_URL')
    PRIVATE_API_SECRET = os.getenv('PRIVATE_API_SECRET')
    PRIVATE_API_TIMEOUT = 30
    
    # Payment Configuration
    STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
    STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
    STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
    APPLE_BUNDLE_ID = os.getenv('APPLE_BUNDLE_ID', 'com.mirroros.app')
    
    # Redis Configuration (for rate limiting and caching)
    REDIS_URL = os.getenv('REDIS_URL')
    RATELIMIT_STORAGE_URL = REDIS_URL or 'memory://'
    
    # Monitoring Configuration
    SENTRY_DSN = os.getenv('SENTRY_DSN')
    DATADOG_API_KEY = os.getenv('DATADOG_API_KEY')
    DATADOG_APP_KEY = os.getenv('DATADOG_APP_KEY')
    
    # Email Configuration (for verification, notifications)
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.sendgrid.net')
    MAIL_PORT = int(os.getenv('MAIL_PORT', '587'))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@mirroros.com')
    
    # File Upload Configuration
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', '/tmp/uploads')
    
    # CORS Configuration
    CORS_ORIGINS = [
        'https://mirroros.com',
        'https://app.mirroros.com',
        'https://www.mirroros.com'
    ]
    
    # Rate Limiting Configuration
    RATELIMIT_DEFAULT = "1000 per hour"
    RATELIMIT_HEADERS_ENABLED = True
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    
    # Feature Flags
    FEATURE_FLAGS = {
        'enhanced_grounding': True,
        'api_access': True,
        'social_sharing': True,
        'team_accounts': False,  # Coming soon
        'analytics_dashboard': True
    }
    
    @classmethod
    def validate_config(cls) -> Dict[str, Any]:
        """
        Validate production configuration and return status.
        
        Returns:
            Dictionary with validation results
        """
        issues = []
        warnings = []
        
        # Check required environment variables
        required_vars = [
            'DATABASE_URL',
            'JWT_SECRET_KEY',
            'PRIVATE_API_URL',
            'PRIVATE_API_SECRET',
            'STRIPE_SECRET_KEY',
            'STRIPE_WEBHOOK_SECRET'
        ]
        
        for var in required_vars:
            if not os.getenv(var):
                issues.append(f"Missing required environment variable: {var}")
        
        # Check optional but recommended variables
        recommended_vars = [
            'SENTRY_DSN',
            'REDIS_URL',
            'MAIL_USERNAME',
            'MAIL_PASSWORD'
        ]
        
        for var in recommended_vars:
            if not os.getenv(var):
                warnings.append(f"Missing recommended environment variable: {var}")
        
        # Validate database URL format
        db_url = os.getenv('DATABASE_URL')
        if db_url and not db_url.startswith(('postgresql://', 'postgres://')):
            issues.append("DATABASE_URL must be a PostgreSQL URL")
        
        # Validate private API URL
        private_api_url = os.getenv('PRIVATE_API_URL')
        if private_api_url and not private_api_url.startswith('https://'):
            warnings.append("PRIVATE_API_URL should use HTTPS in production")
        
        # Check secret key strength
        secret_key = os.getenv('SECRET_KEY')
        if secret_key and len(secret_key) < 32:
            warnings.append("SECRET_KEY should be at least 32 characters long")
        
        jwt_secret = os.getenv('JWT_SECRET_KEY')
        if jwt_secret and len(jwt_secret) < 32:
            warnings.append("JWT_SECRET_KEY should be at least 32 characters long")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings
        }
    
    @classmethod
    def get_config_summary(cls) -> Dict[str, Any]:
        """
        Get configuration summary (without sensitive values).
        
        Returns:
            Dictionary with configuration summary
        """
        return {
            'environment': cls.ENV,
            'debug': cls.DEBUG,
            'database_configured': bool(cls.SQLALCHEMY_DATABASE_URI),
            'private_api_configured': bool(cls.PRIVATE_API_URL and cls.PRIVATE_API_SECRET),
            'stripe_configured': bool(cls.STRIPE_SECRET_KEY and cls.STRIPE_WEBHOOK_SECRET),
            'redis_configured': bool(cls.REDIS_URL),
            'sentry_configured': bool(cls.SENTRY_DSN),
            'datadog_configured': bool(cls.DATADOG_API_KEY),
            'mail_configured': bool(cls.MAIL_USERNAME and cls.MAIL_PASSWORD),
            'feature_flags': cls.FEATURE_FLAGS
        }

class StagingConfig(ProductionConfig):
    """Staging environment configuration."""
    
    ENV = 'staging'
    DEBUG = True  # Enable debug mode in staging
    
    # Override CORS for staging
    CORS_ORIGINS = [
        'https://staging.mirroros.com',
        'https://mirroros-staging.up.railway.app',
        'http://localhost:3000',  # For local frontend development
        'http://localhost:5000'   # For local backend development
    ]
    
    # Relaxed rate limiting for testing
    RATELIMIT_DEFAULT = "10000 per hour"
    
    # Enable additional logging
    LOG_LEVEL = 'DEBUG'

class DevelopmentConfig:
    """Development environment configuration."""
    
    ENV = 'development'
    DEBUG = True
    TESTING = False
    
    # Use simple secrets for development
    SECRET_KEY = 'dev-secret-key-change-in-production'
    JWT_SECRET_KEY = 'dev-jwt-secret-change-in-production'
    
    # Local database
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://localhost/mirroros_dev')
    SQLALCHEMY_TRACK_MODIFICATIONS = True
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 5,
        'pool_recycle': -1,
        'pool_pre_ping': True
    }
    
    # Local private API
    PRIVATE_API_URL = os.getenv('PRIVATE_API_URL', 'http://localhost:8080')
    PRIVATE_API_SECRET = os.getenv('PRIVATE_API_SECRET', 'dev-private-secret')
    
    # Development payment keys (Stripe test mode)
    STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', 'sk_test_...')
    STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', 'whsec_...')
    
    # Memory-based rate limiting
    RATELIMIT_STORAGE_URL = 'memory://'
    RATELIMIT_DEFAULT = "100000 per hour"  # Very permissive for development
    
    # Disable external services in development
    SENTRY_DSN = None
    DATADOG_API_KEY = None
    
    # Console logging for development
    LOG_LEVEL = 'DEBUG'
    
    # All features enabled in development
    FEATURE_FLAGS = {
        'enhanced_grounding': True,
        'api_access': True,
        'social_sharing': True,
        'team_accounts': True,
        'analytics_dashboard': True
    }

def get_config() -> type:
    """
    Get configuration class based on environment.
    
    Returns:
        Configuration class
    """
    env = os.getenv('ENVIRONMENT', 'development').lower()
    
    if env == 'production':
        return ProductionConfig
    elif env == 'staging':
        return StagingConfig
    else:
        return DevelopmentConfig

def create_env_file(environment: str = 'production') -> str:
    """
    Create example environment file for deployment.
    
    Args:
        environment: Target environment (production, staging, development)
        
    Returns:
        String content for .env file
    """
    if environment == 'production':
        return """# MirrorOS Production Environment Variables
# Copy this file to .env and fill in the actual values

# Environment
ENVIRONMENT=production

# Security
SECRET_KEY=your-secret-key-here-32-chars-minimum
JWT_SECRET_KEY=your-jwt-secret-key-here-32-chars-minimum

# Database
DATABASE_URL=postgresql://user:password@host:port/database

# Private API
PRIVATE_API_URL=https://your-private-api-domain.com
PRIVATE_API_SECRET=your-private-api-secret-here

# Stripe Payments
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PUBLISHABLE_KEY=pk_live_...

# Monitoring (Optional but recommended)
SENTRY_DSN=https://your-sentry-dsn
DATADOG_API_KEY=your-datadog-api-key
DATADOG_APP_KEY=your-datadog-app-key

# Redis (Optional, for better rate limiting)
REDIS_URL=redis://localhost:6379

# Email (Optional, for notifications)
MAIL_USERNAME=your-email-username
MAIL_PASSWORD=your-email-password
MAIL_DEFAULT_SENDER=noreply@yourdomain.com

# Logging
LOG_LEVEL=INFO
"""
    
    elif environment == 'staging':
        return """# MirrorOS Staging Environment Variables

# Environment
ENVIRONMENT=staging

# Security (use different keys than production)
SECRET_KEY=staging-secret-key-here
JWT_SECRET_KEY=staging-jwt-secret-key-here

# Database
DATABASE_URL=postgresql://user:password@staging-host:port/database

# Private API
PRIVATE_API_URL=https://your-staging-private-api-domain.com
PRIVATE_API_SECRET=staging-private-api-secret

# Stripe (use test keys)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PUBLISHABLE_KEY=pk_test_...

# Monitoring
SENTRY_DSN=https://your-staging-sentry-dsn

# Redis
REDIS_URL=redis://staging-redis:6379

# Logging
LOG_LEVEL=DEBUG
"""
    
    else:  # development
        return """# MirrorOS Development Environment Variables

# Environment
ENVIRONMENT=development

# Security (development only - not secure)
SECRET_KEY=dev-secret-key
JWT_SECRET_KEY=dev-jwt-secret

# Database (local)
DATABASE_URL=postgresql://localhost/mirroros_dev

# Private API (local)
PRIVATE_API_URL=http://localhost:8080
PRIVATE_API_SECRET=dev-private-secret

# Stripe (test keys)
STRIPE_SECRET_KEY=sk_test_your_test_key
STRIPE_WEBHOOK_SECRET=whsec_your_test_webhook_secret

# Logging
LOG_LEVEL=DEBUG
"""