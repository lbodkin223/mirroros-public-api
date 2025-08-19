"""
Database module for MirrorOS Public API.
PostgreSQL database configuration and initialization.
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Create SQLAlchemy instance
db = SQLAlchemy()
migrate = Migrate()

def init_database(app: Flask) -> None:
    """
    Initialize database with Flask app.
    
    Args:
        app: Flask application instance
    """
    # Initialize SQLAlchemy
    db.init_app(app)
    
    # Initialize Flask-Migrate
    migrate.init_app(app, db)
    
    # Create tables in development
    with app.app_context():
        if app.config.get('ENVIRONMENT') == 'development':
            db.create_all()

__all__ = ['db', 'migrate', 'init_database']