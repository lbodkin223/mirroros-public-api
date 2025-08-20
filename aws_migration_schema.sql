-- MirrorOS Production Database Schema for AWS RDS
-- PostgreSQL 15.14 compatible schema

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    tier VARCHAR(50) DEFAULT 'free' CHECK (tier IN ('free', 'pro', 'enterprise')),
    is_active BOOLEAN DEFAULT true,
    is_verified BOOLEAN DEFAULT false,
    predictions_used_today INTEGER DEFAULT 0,
    last_reset_date DATE DEFAULT CURRENT_DATE,
    last_login TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create whitelist table
CREATE TABLE IF NOT EXISTS whitelist (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    is_used BOOLEAN DEFAULT false,
    used_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    invited_by VARCHAR(255),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_whitelist_email ON whitelist(email);
CREATE INDEX IF NOT EXISTS idx_whitelist_used ON whitelist(is_used);

-- Enable Row Level Security (RLS)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE whitelist ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for users table
DO $$
BEGIN
    -- Drop existing policies if they exist
    DROP POLICY IF EXISTS users_select_own ON users;
    DROP POLICY IF EXISTS users_update_own ON users;
    
    -- Users can only see and update their own records
    CREATE POLICY users_select_own ON users
        FOR SELECT
        USING (id = current_setting('app.current_user_id')::uuid);
    
    CREATE POLICY users_update_own ON users
        FOR UPDATE
        USING (id = current_setting('app.current_user_id')::uuid);
        
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'Could not create RLS policies - insufficient privileges';
END
$$;

-- Insert initial whitelist entries for testing
INSERT INTO whitelist (email, notes) VALUES 
    ('liambodkin@gmail.com', 'Initial admin user'),
    ('demo@mirroros.com', 'Demo user for testing')
ON CONFLICT (email) DO NOTHING;

-- Create function to reset daily usage
CREATE OR REPLACE FUNCTION reset_daily_usage()
RETURNS void AS $$
BEGIN
    UPDATE users 
    SET predictions_used_today = 0, 
        last_reset_date = CURRENT_DATE
    WHERE last_reset_date < CURRENT_DATE;
END;
$$ LANGUAGE plpgsql;

-- Create function to check if user can make prediction
CREATE OR REPLACE FUNCTION can_make_prediction(user_id UUID)
RETURNS boolean AS $$
DECLARE
    user_record users%ROWTYPE;
    daily_limit INTEGER;
BEGIN
    SELECT * INTO user_record FROM users WHERE id = user_id AND is_active = true;
    
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    
    -- Reset usage if new day
    IF user_record.last_reset_date < CURRENT_DATE THEN
        UPDATE users 
        SET predictions_used_today = 0, 
            last_reset_date = CURRENT_DATE
        WHERE id = user_id;
        user_record.predictions_used_today := 0;
    END IF;
    
    -- Get daily limit based on tier
    CASE user_record.tier
        WHEN 'free' THEN daily_limit := 3;
        WHEN 'pro' THEN daily_limit := 50;
        WHEN 'enterprise' THEN daily_limit := 1000;
        ELSE daily_limit := 3;
    END CASE;
    
    RETURN user_record.predictions_used_today < daily_limit;
END;
$$ LANGUAGE plpgsql;

-- Grant necessary permissions
GRANT USAGE ON SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO postgres;

-- Display table information
SELECT 'Schema created successfully!' as message;
SELECT table_name, column_name, data_type 
FROM information_schema.columns 
WHERE table_schema = 'public' 
ORDER BY table_name, ordinal_position;