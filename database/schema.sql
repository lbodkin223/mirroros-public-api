-- MirrorOS Production Database Schema
-- PostgreSQL Database Schema for User Management and Payments
-- Version: 1.0
-- Last Updated: 2024-08-20

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table - Core user authentication and profile
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    
    -- Account status
    tier VARCHAR(20) NOT NULL DEFAULT 'free' CHECK (tier IN ('free', 'pro', 'enterprise')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Usage tracking
    predictions_used_today INTEGER NOT NULL DEFAULT 0,
    last_reset_date DATE DEFAULT CURRENT_DATE,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

-- Create indexes for users table
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_tier ON users(tier);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);
CREATE INDEX IF NOT EXISTS idx_users_verified ON users(is_verified);

-- Whitelist table - For email-based access control
CREATE TABLE IF NOT EXISTS whitelist (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    invite_code VARCHAR(50) UNIQUE,
    invited_by UUID REFERENCES users(id),
    notes TEXT,
    
    -- Status
    is_used BOOLEAN NOT NULL DEFAULT FALSE,
    used_at TIMESTAMPTZ,
    used_by UUID REFERENCES users(id),
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ -- Optional expiration for invites
);

-- Create indexes for whitelist table
CREATE INDEX IF NOT EXISTS idx_whitelist_email ON whitelist(email);
CREATE INDEX IF NOT EXISTS idx_whitelist_invite_code ON whitelist(invite_code);
CREATE INDEX IF NOT EXISTS idx_whitelist_is_used ON whitelist(is_used);
CREATE INDEX IF NOT EXISTS idx_whitelist_expires_at ON whitelist(expires_at);

-- Subscriptions table - Payment and subscription management
CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    
    -- Payment provider identifiers
    stripe_subscription_id VARCHAR(255) UNIQUE,
    apple_transaction_id VARCHAR(255),
    
    -- Subscription details
    tier VARCHAR(20) NOT NULL CHECK (tier IN ('free', 'pro', 'enterprise')),
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'canceled', 'past_due', 'unpaid', 'incomplete')),
    
    -- Billing period
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for subscriptions table
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_id ON subscriptions(stripe_subscription_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_period_end ON subscriptions(current_period_end);

-- Prediction requests table - Analytics and logging (no sensitive data)
CREATE TABLE IF NOT EXISTS prediction_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Request metadata (no sensitive goal data)
    request_data_hash VARCHAR(64) NOT NULL, -- SHA-256 hash
    success BOOLEAN NOT NULL,
    error_code VARCHAR(50),
    response_time_ms INTEGER,
    
    -- Timestamp
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for prediction_requests table
CREATE INDEX IF NOT EXISTS idx_prediction_requests_user_id ON prediction_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_prediction_requests_success ON prediction_requests(success);
CREATE INDEX IF NOT EXISTS idx_prediction_requests_created_at ON prediction_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_prediction_requests_hash ON prediction_requests(request_data_hash);

-- Payment events table - Track all payment-related events
CREATE TABLE IF NOT EXISTS payment_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Event details
    event_type VARCHAR(50) NOT NULL, -- payment_succeeded, payment_failed, subscription_created, etc.
    provider VARCHAR(20) NOT NULL CHECK (provider IN ('stripe', 'apple')),
    provider_event_id VARCHAR(255) UNIQUE,
    
    -- Event data
    amount_cents INTEGER, -- Amount in cents
    currency VARCHAR(3) DEFAULT 'USD',
    subscription_id UUID REFERENCES subscriptions(id),
    
    -- Status and metadata
    processed BOOLEAN NOT NULL DEFAULT FALSE,
    error_message TEXT,
    
    -- Timestamp
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for payment_events table
CREATE INDEX IF NOT EXISTS idx_payment_events_user_id ON payment_events(user_id);
CREATE INDEX IF NOT EXISTS idx_payment_events_type ON payment_events(event_type);
CREATE INDEX IF NOT EXISTS idx_payment_events_provider ON payment_events(provider);
CREATE INDEX IF NOT EXISTS idx_payment_events_processed ON payment_events(processed);
CREATE INDEX IF NOT EXISTS idx_payment_events_created_at ON payment_events(created_at);

-- User sessions table - Track user sessions for security
CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Session details
    token_jti VARCHAR(255) UNIQUE, -- JWT ID for token blacklisting
    ip_address INET,
    user_agent TEXT,
    
    -- Session metadata
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    expires_at TIMESTAMPTZ NOT NULL,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for user_sessions table
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_token_jti ON user_sessions(token_jti);
CREATE INDEX IF NOT EXISTS idx_user_sessions_active ON user_sessions(is_active);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions(expires_at);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at
CREATE TRIGGER update_users_updated_at 
    BEFORE UPDATE ON users 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_subscriptions_updated_at 
    BEFORE UPDATE ON subscriptions 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Views for common queries
CREATE OR REPLACE VIEW user_subscription_status AS
SELECT 
    u.id as user_id,
    u.email,
    u.tier as user_tier,
    u.is_active as user_active,
    u.predictions_used_today,
    u.last_reset_date,
    s.id as subscription_id,
    s.tier as subscription_tier,
    s.status as subscription_status,
    s.current_period_end,
    CASE 
        WHEN s.current_period_end IS NULL THEN TRUE
        WHEN s.current_period_end > NOW() THEN TRUE
        ELSE FALSE
    END as subscription_active
FROM users u
LEFT JOIN subscriptions s ON u.id = s.user_id;

-- Security: Row Level Security (RLS) policies
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE whitelist ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE prediction_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_sessions ENABLE ROW LEVEL SECURITY;

-- RLS Policies (users can only access their own data)
CREATE POLICY users_own_data ON users
    FOR ALL USING (id = current_setting('app.current_user_id')::UUID);

CREATE POLICY subscriptions_own_data ON subscriptions
    FOR ALL USING (user_id = current_setting('app.current_user_id')::UUID);

CREATE POLICY prediction_requests_own_data ON prediction_requests
    FOR ALL USING (user_id = current_setting('app.current_user_id')::UUID);

CREATE POLICY payment_events_own_data ON payment_events
    FOR ALL USING (user_id = current_setting('app.current_user_id')::UUID);

CREATE POLICY user_sessions_own_data ON user_sessions
    FOR ALL USING (user_id = current_setting('app.current_user_id')::UUID);

-- Whitelist policies - Admin access only for management
CREATE POLICY whitelist_admin_access ON whitelist
    FOR ALL USING (current_setting('app.current_user_role', true) = 'admin');

-- Create application user for Railway/production
-- DO NOT run this in production - use Railway's database user
-- CREATE USER mirroros_app WITH PASSWORD 'secure_password_here';
-- GRANT CONNECT ON DATABASE mirroros_production TO mirroros_app;
-- GRANT USAGE ON SCHEMA public TO mirroros_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mirroros_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mirroros_app;

-- Data cleanup scheduled function (optional)
CREATE OR REPLACE FUNCTION cleanup_old_data()
RETURNS void AS $$
BEGIN
    -- Delete old sessions (older than 30 days)
    DELETE FROM user_sessions 
    WHERE expires_at < NOW() - INTERVAL '30 days';
    
    -- Delete old prediction requests (older than 90 days) for free users
    DELETE FROM prediction_requests pr
    USING users u
    WHERE pr.user_id = u.id 
    AND u.tier = 'free'
    AND pr.created_at < NOW() - INTERVAL '90 days';
    
    -- Delete old payment events (older than 7 years for compliance)
    DELETE FROM payment_events 
    WHERE created_at < NOW() - INTERVAL '7 years';
END;
$$ LANGUAGE plpgsql;

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_versions (
    version VARCHAR(20) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    description TEXT
);

INSERT INTO schema_versions (version, description) 
VALUES ('1.0', 'Initial production schema with users, subscriptions, and analytics')
ON CONFLICT (version) DO NOTHING;

-- Comments for documentation
COMMENT ON TABLE users IS 'Core user accounts and authentication';
COMMENT ON TABLE subscriptions IS 'User subscription and payment status';
COMMENT ON TABLE prediction_requests IS 'Analytics logging (no sensitive goal data)';
COMMENT ON TABLE payment_events IS 'Payment processing event log';
COMMENT ON TABLE user_sessions IS 'User session tracking for security';

COMMENT ON COLUMN users.predictions_used_today IS 'Daily usage counter, resets at midnight';
COMMENT ON COLUMN prediction_requests.request_data_hash IS 'SHA-256 hash of request for deduplication';
COMMENT ON COLUMN payment_events.amount_cents IS 'Payment amount in cents to avoid decimal issues';