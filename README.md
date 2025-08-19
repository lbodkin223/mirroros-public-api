# MirrorOS Public API

A production-ready Flask API server for MirrorOS that handles user authentication, payments, and proxies prediction requests to a private server. This API is designed to be deployed on Railway, Heroku, or similar cloud platforms.

## Features

- **JWT Authentication**: Secure user registration, login, and session management
- **Payment Processing**: Dual payment support for Stripe (web) and Apple In-App Purchases (iOS)
- **Prediction Proxy**: Secure HMAC-signed requests to private prediction server
- **Rate Limiting**: Tier-based usage limits with Redis backend
- **Database**: PostgreSQL with optimized schema and analytics views
- **Security**: CORS, request signing, input validation, and security headers
- **Monitoring**: Sentry integration and comprehensive logging
- **Deployment**: Docker, Railway, and Heroku ready

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   iOS/Web App   │────│  Public API      │────│  Private Server │
│   (Frontend)    │    │  (This Project)  │    │  (Predictions)  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                       ┌──────────────┐
                       │  PostgreSQL  │
                       │    Redis     │
                       │   Stripe     │
                       │    Apple     │
                       └──────────────┘
```

## Quick Start

### Local Development

1. **Clone and Setup**
   ```bash
   git clone <repository-url>
   cd mirroros-public
   pip install -r requirements.txt
   ```

2. **Environment Configuration**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Database Setup**
   ```bash
   # Start PostgreSQL and Redis (or use Docker Compose)
   docker-compose up -d db redis
   
   # Initialize database
   flask db upgrade
   python -c "from database.schema import initialize_production_database; initialize_production_database()"
   ```

4. **Run Development Server**
   ```bash
   flask run --port=8000
   ```

### Docker Development

```bash
docker-compose up
```

### Railway Deployment

1. **Connect Repository**: Link your GitHub repository to Railway
2. **Set Environment Variables**: Configure all required environment variables
3. **Deploy**: Railway will automatically build and deploy using the Dockerfile

### Heroku Deployment

```bash
heroku create your-app-name
heroku addons:create heroku-postgresql:hobby-dev
heroku addons:create heroku-redis:hobby-dev
heroku config:set FLASK_ENV=production
# Set other environment variables...
git push heroku main
```

## API Documentation

### Authentication Endpoints

#### Register User
```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

#### Login
```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

#### Get Profile
```http
GET /api/auth/profile
Authorization: Bearer <jwt_token>
```

### Payment Endpoints

#### Create Stripe Checkout Session
```http
POST /api/payments/stripe/create-checkout-session
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "tier": "pro",
  "billing_cycle": "monthly"
}
```

#### Validate Apple Receipt
```http
POST /api/payments/apple/validate-receipt
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "receipt_data": "base64_encoded_receipt"
}
```

### Prediction Endpoints

#### Make Prediction
```http
POST /api/gateway/predict
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "goal": "I want to get a job at OpenAI within 6 months",
  "timeframe": "6 months",
  "context": "I have 3 years of ML experience",
  "options": {
    "enhanced_grounding": true,
    "confidence_level": "high"
  }
}
```

#### Get Usage Statistics
```http
GET /api/gateway/predict/usage
Authorization: Bearer <jwt_token>
```

### Health Check
```http
GET /health
```

## Configuration

### Required Environment Variables

```bash
# Core
SECRET_KEY=your-secret-key
DATABASE_URL=postgresql://user:pass@host:port/dbname
PRIVATE_API_URL=https://your-private-server.com
PRIVATE_API_SECRET=your-hmac-secret

# Payments
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
APPLE_SHARED_SECRET=your-apple-secret

# Optional
REDIS_URL=redis://localhost:6379/0
SENTRY_DSN=https://...@sentry.io/...
```

### User Tiers and Limits

| Tier       | Predictions/Day | Features |
|------------|-----------------|----------|
| Free       | 5               | Basic predictions |
| Pro        | 100             | Enhanced grounding, priority support |
| Enterprise | Unlimited       | All features, dedicated support |

## Security Features

- **HMAC Request Signing**: All requests to private server are HMAC-SHA256 signed
- **JWT Authentication**: Secure token-based authentication
- **Rate Limiting**: Prevents abuse with Redis-backed rate limiting
- **Input Validation**: Comprehensive request validation and sanitization
- **CORS Protection**: Configurable cross-origin resource sharing
- **Security Headers**: Automatic security headers via middleware

## Database Schema

### Users Table
- `id` (UUID): Primary key
- `email` (String): Unique user email
- `password_hash` (String): Bcrypt hashed password
- `tier` (String): Subscription tier (free/pro/enterprise)
- `is_active` (Boolean): Account status
- `is_verified` (Boolean): Email verification status

### Subscriptions Table
- `id` (UUID): Primary key
- `user_id` (UUID): Foreign key to users
- `stripe_subscription_id` (String): Stripe subscription ID
- `apple_transaction_id` (String): Apple transaction ID
- `tier` (String): Subscription tier
- `status` (String): Subscription status

### Prediction Requests Table
- `id` (UUID): Primary key
- `user_id` (UUID): Foreign key to users
- `request_data_hash` (String): Hash of request data
- `success` (Boolean): Request success status
- `response_time_ms` (Integer): Response time
- `error_code` (String): Error code if failed

## Monitoring and Logging

### Health Checks
- **Application Health**: `/health` endpoint
- **Database Health**: Connection and query checks
- **Private Server Health**: `/api/gateway/predict/health`

### Metrics and Analytics
- User registration and activity metrics
- Subscription analytics (Stripe + Apple)
- Prediction usage analytics
- Performance metrics (response times, success rates)

### Logging
- Structured JSON logging
- Request/response logging
- Error tracking with Sentry
- Security event logging

## Development

### Project Structure
```
mirroros-public/
├── app.py                 # Flask application factory
├── config.py              # Configuration management
├── requirements.txt       # Python dependencies
├── Dockerfile            # Docker configuration
├── railway.json          # Railway deployment config
├── auth/                 # Authentication module
│   ├── models.py         # User and subscription models
│   ├── routes.py         # Auth endpoints
│   └── middleware.py     # JWT and rate limiting
├── payments/             # Payment processing
│   ├── stripe_handler.py # Stripe integration
│   └── apple_validator.py# Apple IAP validation
├── gateway/              # Prediction proxy
│   └── prediction_proxy.py
├── security/             # Security utilities
│   └── request_signer.py # HMAC signing
└── database/             # Database configuration
    ├── __init__.py       # Database initialization
    └── schema.py         # Schema and migrations
```

### Testing

```bash
# Install test dependencies
pip install pytest pytest-flask pytest-cov

# Run tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html
```

### Code Quality

```bash
# Format code
black .

# Lint code
flake8 .
```

## Deployment Considerations

### Environment-Specific Settings

- **Development**: Debug enabled, relaxed security, in-memory caching
- **Staging**: Production-like but with debug logging
- **Production**: Security hardened, optimized performance, monitoring enabled

### Scaling

- **Horizontal Scaling**: Stateless design allows multiple instances
- **Database**: Connection pooling and read replicas supported
- **Caching**: Redis for session storage and rate limiting
- **CDN**: Static assets can be served via CDN

### Security Checklist

- [ ] Environment variables properly configured
- [ ] HTTPS enabled in production
- [ ] CORS origins restricted to your domains
- [ ] Rate limiting configured appropriately
- [ ] Database credentials secured
- [ ] Webhook secrets properly set
- [ ] Monitoring and alerting configured

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review logs and error messages
3. Verify environment configuration
4. Check database connectivity
5. Validate webhook endpoints

## License

[Your License Here]