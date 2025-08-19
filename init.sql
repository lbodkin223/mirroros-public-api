-- Initial database setup for MirrorOS Public API
-- This file is used by Docker Compose for development setup

-- Create database if it doesn't exist (for PostgreSQL 15+)
SELECT 'CREATE DATABASE mirroros_public'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mirroros_public')\gexec

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create indexes for better performance
-- Note: Tables will be created by SQLAlchemy, this just adds indexes

-- Function to create indexes after tables exist
CREATE OR REPLACE FUNCTION create_performance_indexes()
RETURNS void AS $$
BEGIN
    -- Users table indexes
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'users') THEN
        CREATE INDEX IF NOT EXISTS idx_users_email_trgm ON users USING gin(email gin_trgm_ops);
        CREATE INDEX IF NOT EXISTS idx_users_tier_active ON users(tier, is_active);
        CREATE INDEX IF NOT EXISTS idx_users_created_at_desc ON users(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_users_last_login_desc ON users(last_login_at DESC NULLS LAST);
    END IF;
    
    -- Subscriptions table indexes
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'subscriptions') THEN
        CREATE INDEX IF NOT EXISTS idx_subscriptions_user_tier_status ON subscriptions(user_id, tier, status);
        CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_active ON subscriptions(stripe_subscription_id) WHERE status = 'active';
        CREATE INDEX IF NOT EXISTS idx_subscriptions_apple_active ON subscriptions(apple_transaction_id) WHERE status = 'active';
        CREATE INDEX IF NOT EXISTS idx_subscriptions_period_end_active ON subscriptions(current_period_end) WHERE status = 'active';
    END IF;
    
    -- Prediction requests table indexes
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'prediction_requests') THEN
        CREATE INDEX IF NOT EXISTS idx_prediction_requests_user_date ON prediction_requests(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_prediction_requests_success_date ON prediction_requests(success, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_prediction_requests_hash_user ON prediction_requests(request_data_hash, user_id);
        CREATE INDEX IF NOT EXISTS idx_prediction_requests_response_time ON prediction_requests(response_time_ms) WHERE response_time_ms IS NOT NULL;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Note: This function will be called after SQLAlchemy creates the tables