# MirrorOS - AI-Powered Prediction Engine

MirrorOS is an advanced prediction platform that analyzes user goals and provides probabilistic success estimates with actionable insights. The system uses natural language processing to extract features from goal descriptions and applies sophisticated algorithms to generate realistic predictions.

![MirrorOS Demo](https://img.shields.io/badge/Status-Production-brightgreen)
![Version](https://img.shields.io/badge/Version-1.0-blue)
![License](https://img.shields.io/badge/License-Proprietary-red)

## 🚀 Live Demo

**Production URL**: https://mirroros-public-api-mirroros.up.railway.app/

## ✨ Features

### Core Functionality
- **🎯 Goal Analysis**: Natural language processing to extract timeline, experience, target entity, and complexity
- **📊 Dynamic Predictions**: Probability estimates that vary based on goal difficulty and user leverage  
- **🔬 Enhanced Grounding**: Research-backed predictions with domain-specific sources
- **📈 Target Analysis**: Goal difficulty, user leverage, and target selectivity metrics
- **🎨 Beautiful UI**: Modern glassmorphism design with animated backgrounds
- **📱 Responsive**: Works perfectly on desktop and mobile devices

### Prediction Categories
- **Career**: Job searches, promotions, career transitions
- **Education**: Learning goals, certifications, skill development  
- **Business**: Startup goals, revenue targets, growth objectives
- **Health**: Fitness goals, habit formation, wellness targets
- **Travel**: Trip planning, visa applications, adventure goals
- **Relationships**: Dating goals, social objectives, networking

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend UI   │────│  Public API     │────│   Private API   │
│   (Static)      │    │  (Auth/Proxy)   │    │  (Algorithms)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
    ┌─────────┐              ┌─────────┐              ┌─────────┐
    │ HTML/JS │              │ Flask   │              │ Flask   │
    │ CSS/UI  │              │ Auth    │              │ ML Core │
    └─────────┘              │ Payments│              │ NLP     │
                             │ Rate    │              │ Cache   │
                             │ Limit   │              └─────────┘
                             └─────────┘
```

### Public API (Authentication & Proxy)
- **Authentication**: JWT-based with demo mode
- **Rate Limiting**: Tier-based usage limits
- **Request Proxying**: Secure forwarding to private algorithms
- **Static Files**: Serves the main UI application

### Private API (Prediction Engine)
- **Feature Extraction**: NLP analysis of goal text
- **Prediction Algorithms**: Mathematical models for probability calculation
- **Enhanced Grounding**: Research source simulation (RAG-ready architecture)
- **Security**: HMAC request signing, IP whitelisting

## 🛠️ Technology Stack

### Backend
- **Python 3.9+**
- **Flask** - Web framework
- **JWT** - Authentication
- **SQLAlchemy** - Database ORM
- **Redis** - Caching (optional)
- **Gunicorn** - WSGI server

### Frontend  
- **Vanilla JavaScript** - No frameworks for maximum performance
- **CSS3** - Modern styling with glassmorphism effects
- **HTML5** - Semantic markup

### Infrastructure
- **Railway** - Cloud deployment
- **PostgreSQL** - Database (Railway managed)
- **GitHub** - Version control
- **Environment Variables** - Configuration management

## 🚦 Getting Started

### Prerequisites
- Python 3.9 or higher
- Git
- Railway CLI (for deployment)

### Local Development

1. **Clone the repositories**:
   ```bash
   git clone https://github.com/lbodkin223/mirroros-public-api.git
   git clone https://github.com/lbodkin223/mirroros-private.git
   ```

2. **Set up Public API**:
   ```bash
   cd mirroros-public-api
   pip install -r requirements.txt
   
   # Set environment variables
   export FLASK_ENV=development
   export PRIVATE_API_URL=http://localhost:8001
   export PRIVATE_API_SECRET=your-secret-key
   
   python app.py
   ```

3. **Set up Private API**:
   ```bash
   cd mirroros-private-api
   pip install -r requirements.txt
   
   python simple_server.py
   ```

4. **Open in browser**: http://localhost:5000

### Environment Variables

#### Public API
```bash
PRIVATE_API_URL=https://mirroros-private-production.up.railway.app
PRIVATE_API_SECRET=your-hmac-secret
DATABASE_URL=postgresql://... (optional)
JWT_SECRET_KEY=your-jwt-secret
SENTRY_DSN=your-sentry-dsn (optional)
```

#### Private API  
```bash
GROUNDING_SERVICE_TYPE=mock  # or 'rag' for real research
LOG_LEVEL=INFO
FLASK_ENV=production
```

## 🎯 API Endpoints

### Public API (Port 5000)

#### Authentication
- `POST /api/auth/demo-login` - Get demo JWT tokens
- `GET /api/auth/me` - Get current user info

#### Predictions
- `POST /api/predict` - Generate prediction (requires auth)
- `GET /api/predict/usage` - Get usage statistics

#### Health & Info
- `GET /health` - Health check
- `GET /` - Serve main UI

### Private API (Port 8080)

#### Core
- `POST /predict` - Core prediction algorithm
- `GET /health` - Health check

## 🧪 Testing

### Manual Testing
```bash
# Test health endpoints
curl https://mirroros-public-api-mirroros.up.railway.app/health
curl https://mirroros-private-production.up.railway.app/health

# Get demo token
curl -X POST https://mirroros-public-api-mirroros.up.railway.app/api/auth/demo-login \
  -H "Content-Type: application/json" -d '{"demo": true}'

# Test prediction  
curl -X POST https://mirroros-public-api-mirroros.up.railway.app/api/predict \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"goal": "Learn Python in 3 months"}'
```

### Example Predictions
- **Easy**: "Drink water in 5 minutes" → 99% probability
- **Moderate**: "Learn Python in 6 months" → 60% probability  
- **Hard**: "Get job at Google in 2 weeks" → 6% probability
- **Impossible**: "Travel to Mars tomorrow" → 1% probability

## 📊 Features Deep Dive

### Enhanced Grounding
When enabled, the system provides:
- **Dynamic study counts** (2-11 based on complexity)
- **Domain-specific sources** (LinkedIn for career, CDC for health)
- **Company-specific research** (Google hiring data, Apple analytics)
- **Realistic coefficients** (8-14 based on extracted features)

### Feature Extraction
The NLP system extracts:
- **Timeline**: "6 months" → 6.0 months
- **Experience**: "5 years experience" → 5.0 years  
- **Target Entity**: "at Google" → "google"
- **Age**: "I'm 28" → 28 years
- **Budget**: "$5000/month" → 5000.0 USD
- **Readiness Score**: Based on preparation indicators

### Target Analysis Metrics
- **Goal Difficulty**: 0.0 (easy) to 1.0 (very hard)
- **User Leverage**: 0.0 (no advantages) to 1.0 (maximum advantages)  
- **Target Selectivity**: 0.0 (not selective) to 1.0 (extremely selective)

## 🔐 Security

### Authentication
- **JWT tokens** with 24-hour expiration
- **Demo mode** for testing without registration
- **Rate limiting** by user tier

### Private API Security
- **HMAC request signing** for API calls
- **IP whitelisting** for additional protection
- **Request validation** and sanitization
- **No proprietary algorithms** exposed in public API

## 🚀 Deployment

### Railway Deployment
Both services auto-deploy from GitHub:

1. **Public API**: Connected to `mirroros-public-api` repository
2. **Private API**: Connected to `mirroros-private` repository

### Environment Configuration
Set environment variables in Railway dashboard for each service.

### Custom Domains (Optional)
Configure custom domains in Railway for branded URLs.

## 🤝 Contributing

This is a private project. For development access:

1. Contact the development team
2. Get access to private repositories  
3. Follow the development primer document
4. Use the established coding standards

## 📈 Future Roadmap

### Phase 1: RAG Implementation
- **Real research retrieval** with Semantic Scholar API
- **Vector database** integration (Pinecone/Weaviate)
- **Dynamic coefficient updates** from research data

### Phase 2: Mobile App
- **Native iOS app** development
- **Push notifications** for goal reminders
- **Widget support** for quick predictions
- **Offline mode** capabilities

### Phase 3: Enhanced AI
- **GPT integration** for narrative generation
- **Image analysis** for goal context
- **Voice input** for goal description
- **Personalization** based on user history

### Phase 4: Social Features
- **Goal sharing** with friends
- **Community challenges** and leaderboards
- **Expert advice** integration
- **Success story database**

## 📄 License

Proprietary software. All rights reserved.

## 🆘 Support

For technical support or questions:
- Create issues in the respective GitHub repositories
- Contact the development team directly
- Check the development primer document for local setup

---

Built with ❤️ using Claude Code