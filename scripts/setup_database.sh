#!/bin/bash

# MirrorOS Database Setup Script - AWS RDS Version
# This script will set up your PostgreSQL database on AWS RDS

set -e  # Exit on any error

echo "🚀 MirrorOS Database Setup Starting (AWS RDS)..."
echo "=============================================="

# Check if we're in the right directory
if [ ! -f "aws_migration_schema.sql" ]; then
    echo "❌ Error: aws_migration_schema.sql not found. Please run this from the mirroros-public-api directory."
    exit 1
fi

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "❌ Error: DATABASE_URL environment variable not set."
    echo "   Please set it to your AWS RDS connection string:"
    echo "   export DATABASE_URL='postgresql://postgres:password@your-rds-endpoint:5432/postgres'"
    exit 1
fi

echo "✅ DATABASE_URL found"

# Check if psql is available
if ! command -v psql &> /dev/null; then
    echo "❌ Error: psql not found. Please install PostgreSQL client:"
    echo "   macOS: brew install postgresql"
    echo "   Ubuntu: sudo apt-get install postgresql-client"
    exit 1
fi

echo "✅ PostgreSQL client found"

# Test connection
echo "🔗 Testing AWS RDS connection..."
if ! psql "$DATABASE_URL" -c "SELECT version();" &> /dev/null; then
    echo "❌ Error: Cannot connect to AWS RDS database."
    echo "   Please check your DATABASE_URL and network connectivity."
    exit 1
fi

echo "✅ Connected to AWS RDS"

# Run the database schema
echo "📋 Setting up database schema..."
echo "   This will create tables: users, whitelist, prediction_requests, etc."

echo "🗄️  Connecting to PostgreSQL and running AWS migration schema..."
psql "$DATABASE_URL" -f aws_migration_schema.sql

echo ""
echo "🎉 AWS Database setup complete!"
echo "==============================="
echo "✅ Schema loaded successfully"
echo "✅ Tables created: users, whitelist, prediction_requests"
echo "✅ Initial whitelist entries added"
echo "✅ UUID extension enabled"
echo "✅ RLS policies configured"
echo ""
echo "Next steps:"
echo "1. Add your email to whitelist:"
echo "   psql \"\$DATABASE_URL\" -c \"INSERT INTO whitelist (email, notes) VALUES ('your-email@domain.com', 'My account');\""
echo "2. Test the authentication endpoints"
echo "3. Deploy to AWS App Runner for production"
echo ""