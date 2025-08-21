-- Enhanced Vector Tracking Schema for MirrorOS
-- Adds comprehensive prediction vector tracking

-- Create prediction_vectors table to track all analyzed features
CREATE TABLE IF NOT EXISTS prediction_vectors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255), -- Can be UUID or demo-user-123
    request_hash VARCHAR(64) NOT NULL,
    
    -- Goal Analysis Vectors
    goal_text TEXT NOT NULL,
    goal_type VARCHAR(50), -- career, education, business, health, creative, general
    goal_length INTEGER,
    target_entity VARCHAR(255),
    
    -- Temporal Vectors
    timeframe TEXT,
    timeframe_length INTEGER,
    time_horizon_months DECIMAL(10,2),
    
    -- Context Vectors
    context TEXT,
    context_length INTEGER,
    
    -- Experience Vectors
    relevant_experience_years DECIMAL(5,2),
    readiness_score DECIMAL(5,4), -- 0.0000 to 1.0000
    
    -- Personal Vectors
    age_years INTEGER,
    monthly_budget_usd DECIMAL(12,2),
    
    -- Assessment Vectors
    goal_difficulty DECIMAL(5,4), -- 0.0000 to 1.0000
    user_leverage DECIMAL(5,4), -- 0.0000 to 1.0000
    target_selectivity DECIMAL(5,4), -- 0.0000 to 1.0000
    impossibility_factor DECIMAL(5,4), -- 0.0000 to 1.0000
    
    -- Prediction Results
    probability DECIMAL(5,4) NOT NULL, -- 0.0000 to 1.0000
    ci_lower DECIMAL(5,4),
    ci_upper DECIMAL(5,4),
    outcome_category VARCHAR(50), -- highly_likely, likely_success, possible, challenging
    
    -- Factor Analysis
    key_success_factors JSONB,
    risk_factors JSONB,
    math_breakdown JSONB,
    
    -- Grounding Layer
    enhanced_grounding BOOLEAN DEFAULT false,
    studies_count INTEGER,
    coefficients_count INTEGER,
    grounding_details JSONB,
    
    -- Request Metadata
    response_time_ms INTEGER,
    ip_address INET,
    user_agent TEXT,
    api_version VARCHAR(20),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_prediction_vectors_user_id ON prediction_vectors(user_id);
CREATE INDEX IF NOT EXISTS idx_prediction_vectors_created_at ON prediction_vectors(created_at);
CREATE INDEX IF NOT EXISTS idx_prediction_vectors_goal_type ON prediction_vectors(goal_type);
CREATE INDEX IF NOT EXISTS idx_prediction_vectors_target_entity ON prediction_vectors(target_entity);
CREATE INDEX IF NOT EXISTS idx_prediction_vectors_probability ON prediction_vectors(probability);

-- Create prediction_outcomes table for tracking actual results
CREATE TABLE IF NOT EXISTS prediction_outcomes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prediction_vector_id UUID REFERENCES prediction_vectors(id) ON DELETE CASCADE,
    user_id VARCHAR(255),
    
    -- Outcome Tracking
    outcome_achieved BOOLEAN,
    outcome_date DATE,
    outcome_notes TEXT,
    accuracy_score DECIMAL(5,4), -- How accurate was the prediction
    
    -- Follow-up Data
    actual_timeline_months DECIMAL(10,2),
    major_obstacles TEXT[],
    success_factors_used TEXT[],
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index for outcomes
CREATE INDEX IF NOT EXISTS idx_prediction_outcomes_vector_id ON prediction_outcomes(prediction_vector_id);
CREATE INDEX IF NOT EXISTS idx_prediction_outcomes_user_id ON prediction_outcomes(user_id);
CREATE INDEX IF NOT EXISTS idx_prediction_outcomes_outcome_date ON prediction_outcomes(outcome_date);

-- Create analytics view for prediction insights
CREATE OR REPLACE VIEW prediction_analytics AS
SELECT 
    goal_type,
    target_entity,
    COUNT(*) as prediction_count,
    AVG(probability) as avg_probability,
    AVG(goal_difficulty) as avg_difficulty,
    AVG(user_leverage) as avg_leverage,
    AVG(target_selectivity) as avg_selectivity,
    AVG(response_time_ms) as avg_response_time,
    COUNT(CASE WHEN enhanced_grounding = true THEN 1 END) as grounding_count,
    DATE_TRUNC('day', created_at) as prediction_date
FROM prediction_vectors 
GROUP BY goal_type, target_entity, DATE_TRUNC('day', created_at)
ORDER BY prediction_date DESC;

-- Grant permissions
GRANT ALL PRIVILEGES ON prediction_vectors TO postgres;
GRANT ALL PRIVILEGES ON prediction_outcomes TO postgres;
GRANT SELECT ON prediction_analytics TO postgres;

-- Show success message
SELECT 'Enhanced vector tracking schema created successfully!' as message;
SELECT 'Tables: prediction_vectors, prediction_outcomes, prediction_analytics view' as tables_created;