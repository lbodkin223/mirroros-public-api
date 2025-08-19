"""
Database schema definition for MirrorOS Public API.
PostgreSQL table definitions and migrations.
"""

from database import db

# Import all models to ensure they're registered with SQLAlchemy
from auth.models import User, Subscription, PredictionRequest

def create_indexes():
    """
    Create database indexes for optimal performance.
    This should be called after table creation.
    """
    try:
        # User table indexes
        db.engine.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);')
        db.engine.execute('CREATE INDEX IF NOT EXISTS idx_users_tier ON users(tier);')
        db.engine.execute('CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);')
        db.engine.execute('CREATE INDEX IF NOT EXISTS idx_users_last_login_at ON users(last_login_at);')
        
        # Subscription table indexes
        db.engine.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);')
        db.engine.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_id ON subscriptions(stripe_subscription_id);')
        db.engine.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_apple_id ON subscriptions(apple_transaction_id);')
        db.engine.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);')
        db.engine.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_period_end ON subscriptions(current_period_end);')
        
        # Prediction request table indexes
        db.engine.execute('CREATE INDEX IF NOT EXISTS idx_prediction_requests_user_id ON prediction_requests(user_id);')
        db.engine.execute('CREATE INDEX IF NOT EXISTS idx_prediction_requests_created_at ON prediction_requests(created_at);')
        db.engine.execute('CREATE INDEX IF NOT EXISTS idx_prediction_requests_success ON prediction_requests(success);')
        db.engine.execute('CREATE INDEX IF NOT EXISTS idx_prediction_requests_hash ON prediction_requests(request_data_hash);')
        
        print("Database indexes created successfully")
        
    except Exception as e:
        print(f"Warning: Could not create indexes: {str(e)}")

def create_constraints():
    """
    Create additional database constraints for data integrity.
    """
    try:
        # User constraints
        db.engine.execute('''
            ALTER TABLE users 
            ADD CONSTRAINT chk_users_tier 
            CHECK (tier IN ('free', 'pro', 'enterprise'))
        ''')
        
        db.engine.execute('''
            ALTER TABLE users 
            ADD CONSTRAINT chk_users_predictions_used_today 
            CHECK (predictions_used_today >= 0)
        ''')
        
        # Subscription constraints
        db.engine.execute('''
            ALTER TABLE subscriptions 
            ADD CONSTRAINT chk_subscriptions_tier 
            CHECK (tier IN ('free', 'pro', 'enterprise'))
        ''')
        
        db.engine.execute('''
            ALTER TABLE subscriptions 
            ADD CONSTRAINT chk_subscriptions_status 
            CHECK (status IN ('active', 'canceled', 'past_due', 'incomplete', 'incomplete_expired', 'trialing', 'unpaid'))
        ''')
        
        db.engine.execute('''
            ALTER TABLE subscriptions 
            ADD CONSTRAINT chk_subscriptions_period 
            CHECK (current_period_end IS NULL OR current_period_start IS NULL OR current_period_end > current_period_start)
        ''')
        
        # Prediction request constraints
        db.engine.execute('''
            ALTER TABLE prediction_requests 
            ADD CONSTRAINT chk_prediction_requests_response_time 
            CHECK (response_time_ms IS NULL OR response_time_ms >= 0)
        ''')
        
        print("Database constraints created successfully")
        
    except Exception as e:
        print(f"Warning: Could not create constraints (may already exist): {str(e)}")

def setup_database_functions():
    """
    Create useful database functions and triggers.
    """
    try:
        # Function to automatically update updated_at timestamp
        db.engine.execute('''
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql';
        ''')
        
        # Trigger for users table
        db.engine.execute('''
            CREATE TRIGGER update_users_updated_at 
            BEFORE UPDATE ON users 
            FOR EACH ROW 
            EXECUTE FUNCTION update_updated_at_column();
        ''')
        
        # Trigger for subscriptions table
        db.engine.execute('''
            CREATE TRIGGER update_subscriptions_updated_at 
            BEFORE UPDATE ON subscriptions 
            FOR EACH ROW 
            EXECUTE FUNCTION update_updated_at_column();
        ''')
        
        print("Database functions and triggers created successfully")
        
    except Exception as e:
        print(f"Warning: Could not create database functions: {str(e)}")

def create_analytics_views():
    """
    Create database views for analytics and reporting.
    """
    try:
        # User analytics view
        db.engine.execute('''
            CREATE OR REPLACE VIEW user_analytics AS
            SELECT 
                DATE_TRUNC('day', created_at) as date,
                tier,
                COUNT(*) as new_users,
                COUNT(*) FILTER (WHERE is_verified = true) as verified_users,
                COUNT(*) FILTER (WHERE last_login_at IS NOT NULL) as users_with_login
            FROM users
            GROUP BY DATE_TRUNC('day', created_at), tier
            ORDER BY date DESC;
        ''')
        
        # Subscription analytics view
        db.engine.execute('''
            CREATE OR REPLACE VIEW subscription_analytics AS
            SELECT 
                DATE_TRUNC('day', created_at) as date,
                tier,
                status,
                COUNT(*) as subscription_count,
                COUNT(*) FILTER (WHERE stripe_subscription_id IS NOT NULL) as stripe_subscriptions,
                COUNT(*) FILTER (WHERE apple_transaction_id IS NOT NULL) as apple_subscriptions
            FROM subscriptions
            GROUP BY DATE_TRUNC('day', created_at), tier, status
            ORDER BY date DESC;
        ''')
        
        # Prediction usage analytics view
        db.engine.execute('''
            CREATE OR REPLACE VIEW prediction_analytics AS
            SELECT 
                DATE_TRUNC('day', pr.created_at) as date,
                u.tier,
                COUNT(*) as total_requests,
                COUNT(*) FILTER (WHERE pr.success = true) as successful_requests,
                COUNT(*) FILTER (WHERE pr.success = false) as failed_requests,
                AVG(pr.response_time_ms) FILTER (WHERE pr.response_time_ms IS NOT NULL) as avg_response_time_ms,
                COUNT(DISTINCT pr.user_id) as unique_users
            FROM prediction_requests pr
            JOIN users u ON pr.user_id = u.id
            GROUP BY DATE_TRUNC('day', pr.created_at), u.tier
            ORDER BY date DESC;
        ''')
        
        # Daily metrics view
        db.engine.execute('''
            CREATE OR REPLACE VIEW daily_metrics AS
            SELECT 
                CURRENT_DATE as date,
                COUNT(DISTINCT u.id) as total_users,
                COUNT(DISTINCT u.id) FILTER (WHERE u.tier != 'free') as paid_users,
                COUNT(DISTINCT u.id) FILTER (WHERE u.last_login_at >= CURRENT_DATE) as daily_active_users,
                COUNT(DISTINCT pr.user_id) FILTER (WHERE pr.created_at >= CURRENT_DATE) as users_with_predictions_today,
                COUNT(pr.id) FILTER (WHERE pr.created_at >= CURRENT_DATE) as total_predictions_today,
                COUNT(pr.id) FILTER (WHERE pr.created_at >= CURRENT_DATE AND pr.success = true) as successful_predictions_today
            FROM users u
            LEFT JOIN prediction_requests pr ON u.id = pr.user_id;
        ''')
        
        print("Analytics views created successfully")
        
    except Exception as e:
        print(f"Warning: Could not create analytics views: {str(e)}")

def initialize_production_database():
    """
    Initialize production database with all optimizations.
    """
    print("Initializing production database...")
    
    # Create all tables
    db.create_all()
    print("Tables created")
    
    # Create indexes
    create_indexes()
    
    # Create constraints
    create_constraints()
    
    # Setup functions and triggers
    setup_database_functions()
    
    # Create analytics views
    create_analytics_views()
    
    print("Production database initialization complete")

def get_database_stats():
    """
    Get database statistics for monitoring.
    
    Returns:
        Dictionary with database statistics
    """
    try:
        stats = {}
        
        # User statistics
        user_result = db.engine.execute('''
            SELECT 
                COUNT(*) as total_users,
                COUNT(*) FILTER (WHERE tier = 'free') as free_users,
                COUNT(*) FILTER (WHERE tier = 'pro') as pro_users,
                COUNT(*) FILTER (WHERE tier = 'enterprise') as enterprise_users,
                COUNT(*) FILTER (WHERE is_active = true) as active_users,
                COUNT(*) FILTER (WHERE is_verified = true) as verified_users
            FROM users
        ''').fetchone()
        
        stats['users'] = dict(user_result)
        
        # Subscription statistics
        subscription_result = db.engine.execute('''
            SELECT 
                COUNT(*) as total_subscriptions,
                COUNT(*) FILTER (WHERE status = 'active') as active_subscriptions,
                COUNT(*) FILTER (WHERE stripe_subscription_id IS NOT NULL) as stripe_subscriptions,
                COUNT(*) FILTER (WHERE apple_transaction_id IS NOT NULL) as apple_subscriptions
            FROM subscriptions
        ''').fetchone()
        
        stats['subscriptions'] = dict(subscription_result)
        
        # Prediction statistics
        prediction_result = db.engine.execute('''
            SELECT 
                COUNT(*) as total_predictions,
                COUNT(*) FILTER (WHERE success = true) as successful_predictions,
                COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) as predictions_today,
                AVG(response_time_ms) FILTER (WHERE response_time_ms IS NOT NULL) as avg_response_time_ms
            FROM prediction_requests
        ''').fetchone()
        
        stats['predictions'] = dict(prediction_result)
        
        return stats
        
    except Exception as e:
        print(f"Error getting database stats: {str(e)}")
        return {'error': str(e)}

# Export the models for migrations
__all__ = [
    'User', 'Subscription', 'PredictionRequest',
    'create_indexes', 'create_constraints', 'setup_database_functions',
    'create_analytics_views', 'initialize_production_database',
    'get_database_stats'
]