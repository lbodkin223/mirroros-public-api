#!/bin/bash

# MirrorOS Database Setup Script
# This script will set up your PostgreSQL database on Railway

set -e  # Exit on any error

echo "🚀 MirrorOS Database Setup Starting..."
echo "======================================"

# Check if we're in the right directory
if [ ! -f "database/schema.sql" ]; then
    echo "❌ Error: database/schema.sql not found. Please run this from the mirroros-public-api directory."
    exit 1
fi

# Check if Railway CLI is available
if ! command -v railway &> /dev/null; then
    echo "❌ Error: Railway CLI not found. Please install it first:"
    echo "   npm install -g @railway/cli"
    exit 1
fi

echo "✅ Railway CLI found"

# Check if we're linked to a Railway project
echo "🔗 Checking Railway project connection..."
if ! railway status &> /dev/null; then
    echo "❌ Error: Not connected to a Railway project."
    echo "   Please run: railway link"
    exit 1
fi

echo "✅ Connected to Railway project"

# Run the database schema
echo "📋 Setting up database schema..."
echo "   This will create tables: users, whitelist, subscriptions, etc."

# Create a temporary SQL file with schema + initial data
cat > /tmp/mirroros_setup.sql << 'EOF'
-- Load the main schema
\i database/schema.sql

-- Add initial whitelist entries
INSERT INTO whitelist (email, notes) 
VALUES ('admin@mirroros.com', 'Default admin user')
ON CONFLICT (email) DO NOTHING;

INSERT INTO whitelist (email, notes) 
VALUES ('test@mirroros.com', 'Test user for development')
ON CONFLICT (email) DO NOTHING;

-- Show created tables
\dt

-- Show whitelist entries
SELECT email, notes, created_at, is_used FROM whitelist;

-- Show success message
SELECT 'Database setup complete! ✅' as status;
EOF

echo "🗄️  Connecting to PostgreSQL and running setup..."
railway run psql -f /tmp/mirroros_setup.sql

# Clean up
rm -f /tmp/mirroros_setup.sql

echo ""
echo "🎉 Database setup complete!"
echo "=============================="
echo "✅ Schema loaded successfully"
echo "✅ Tables created: users, whitelist, subscriptions, etc."
echo "✅ Initial whitelist entries added"
echo ""
echo "Next steps:"
echo "1. Add your email to whitelist: railway run psql -c \"INSERT INTO whitelist (email, notes) VALUES ('your-email@domain.com', 'My account');\""
echo "2. Test the authentication endpoints"
echo ""