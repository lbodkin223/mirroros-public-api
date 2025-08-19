"""
Configuration module for MirrorOS Public API.
Handles environment-specific settings and configuration loading.
"""

import os
from datetime import timedelta
from typing import Dict, Any


class Config:
    """Base configuration class."""
    
    # Flask Configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database Configuration
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or 'postgresql://localhost/mirroros_public'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 120,
        'pool_pre_ping': True,
        'max_overflow': 20,
    }
    
    # JWT Configuration
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or SECRET_KEY
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES', 3600)))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(seconds=int(os.environ.get('JWT_REFRESH_TOKEN_EXPIRES', 2592000)))
    JWT_ALGORITHM = 'HS256'
    JWT_BLACKLIST_ENABLED = True
    JWT_BLACKLIST_TOKEN_CHECKS = ['access', 'refresh']
    
    # Redis Configuration
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    
    # Rate Limiting Configuration
    RATELIMIT_STORAGE_URL = os.environ.get('RATE_LIMIT_STORAGE_URL') or REDIS_URL
    RATELIMIT_HEADERS_ENABLED = True
    
    # Stripe Configuration
    STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
    
    # Apple Configuration
    APPLE_SHARED_SECRET = os.environ.get('APPLE_SHARED_SECRET')
    
    # Private API Configuration
    PRIVATE_API_URL = os.environ.get('PRIVATE_API_URL')
    PRIVATE_API_SECRET = os.environ.get('PRIVATE_API_SECRET')
    
    # CORS Configuration
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*').split(',')
    CORS_ALLOW_HEADERS = ['Content-Type', 'Authorization', 'X-Requested-With']
    CORS_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
    
    # Application Configuration
    APP_NAME = os.environ.get('APP_NAME', 'MirrorOS Public API')
    APP_VERSION = os.environ.get('APP_VERSION', '1.0.0')
    ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')
    
    # Security Configuration
    BCRYPT_LOG_ROUNDS = int(os.environ.get('BCRYPT_LOG_ROUNDS', 12))
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # File Upload Configuration
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 16777216))  # 16MB
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
    
    # Pagination Configuration
    DEFAULT_PAGE_SIZE = int(os.environ.get('DEFAULT_PAGE_SIZE', 20))
    MAX_PAGE_SIZE = int(os.environ.get('MAX_PAGE_SIZE', 100))
    
    # Monitoring Configuration
    SENTRY_DSN = os.environ.get('SENTRY_DSN')
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    
    # Email Configuration (optional)
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    
    # Cache Configuration
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'redis')
    CACHE_REDIS_URL = os.environ.get('CACHE_REDIS_URL') or REDIS_URL
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get('CACHE_DEFAULT_TIMEOUT', 300))


class DevelopmentConfig(Config):
    """Development configuration."""
    
    DEBUG = True
    TESTING = False
    
    # More verbose logging in development
    LOG_LEVEL = 'DEBUG'
    
    # Relaxed security for development
    SESSION_COOKIE_SECURE = False
    BCRYPT_LOG_ROUNDS = 4  # Faster for development
    
    # JWT expires faster in development for testing
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=2)


class TestingConfig(Config):
    """Testing configuration."""
    
    TESTING = True
    DEBUG = True
    
    # Use in-memory database for testing
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    
    # Disable CSRF for testing
    WTF_CSRF_ENABLED = False
    
    # Fast bcrypt for testing
    BCRYPT_LOG_ROUNDS = 4
    
    # Short-lived JWT for testing
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)
    
    # Use different Redis DB for testing
    REDIS_URL = 'redis://localhost:6379/15'


class ProductionConfig(Config):
    """Production configuration."""
    
    DEBUG = False
    TESTING = False
    
    # Enhanced security for production
    SESSION_COOKIE_SECURE = True
    BCRYPT_LOG_ROUNDS = 15
    
    # Stricter database settings
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 20,
        'pool_recycle': 300,
        'pool_pre_ping': True,
        'max_overflow': 40,
    }


class StagingConfig(ProductionConfig):
    """Staging configuration (like production but with debug info)."""
    
    LOG_LEVEL = 'DEBUG'


# Configuration mapping
config_mapping = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'staging': StagingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config(environment: str = None) -> Config:
    """
    Get configuration class based on environment.
    
    Args:
        environment: Environment name
        
    Returns:
        Configuration class instance
    """
    if environment is None:
        environment = os.environ.get('FLASK_ENV', 'development')
    
    return config_mapping.get(environment, DevelopmentConfig)


def load_config(app, config: Dict[str, Any] = None) -> None:
    """
    Load configuration into Flask app.
    
    Args:
        app: Flask application instance
        config: Additional configuration overrides
    """
    # Load environment-based configuration
    environment = os.environ.get('FLASK_ENV', 'development')
    config_class = get_config(environment)
    app.config.from_object(config_class)
    
    # Apply any additional configuration
    if config:
        app.config.update(config)
    
    # Validate required configuration
    required_configs = ['SECRET_KEY', 'SQLALCHEMY_DATABASE_URI']
    
    if environment == 'production':
        required_configs.extend([
            'STRIPE_SECRET_KEY',
            'PRIVATE_API_URL',
            'PRIVATE_API_SECRET'
        ])
    
    missing_configs = [key for key in required_configs if not app.config.get(key)]
    
    if missing_configs:
        raise ValueError(f"Missing required configuration: {', '.join(missing_configs)}")


def get_database_config() -> Dict[str, Any]:
    """
    Get database configuration for external tools.
    
    Returns:
        Database configuration dictionary
    """
    return {
        'url': Config.SQLALCHEMY_DATABASE_URI,
        'pool_size': Config.SQLALCHEMY_ENGINE_OPTIONS['pool_size'],
        'pool_recycle': Config.SQLALCHEMY_ENGINE_OPTIONS['pool_recycle'],
        'pool_pre_ping': Config.SQLALCHEMY_ENGINE_OPTIONS['pool_pre_ping'],
        'max_overflow': Config.SQLALCHEMY_ENGINE_OPTIONS['max_overflow'],
    }