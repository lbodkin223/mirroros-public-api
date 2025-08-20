"""
Enhanced rate limiting for MirrorOS Public API.
Implements sliding window rate limiting with Redis backend and fallback to memory.
"""

import time
import json
import logging
from typing import Dict, Any, Optional, Tuple
from functools import wraps
from datetime import datetime, timedelta
from flask import request, current_app, g
from auth.middleware import get_current_user

# Setup logging
logger = logging.getLogger(__name__)

class RateLimiter:
    """
    Advanced rate limiter with multiple algorithms and backends.
    """
    
    def __init__(self, redis_client=None):
        """
        Initialize rate limiter.
        
        Args:
            redis_client: Optional Redis client for distributed rate limiting
        """
        self.redis_client = redis_client
        self.memory_store = {}  # Fallback to memory if Redis unavailable
        
    def _get_client_id(self) -> str:
        """Get unique identifier for the client."""
        user = get_current_user()
        if user:
            return f"user:{user.id}"
        else:
            # Fall back to IP address for unauthenticated requests
            return f"ip:{request.remote_addr}"
    
    def _get_redis_key(self, identifier: str, window: str) -> str:
        """Generate Redis key for rate limit tracking."""
        return f"rate_limit:{identifier}:{window}"
    
    def _sliding_window_check(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, Dict[str, Any]]:
        """
        Sliding window rate limiting algorithm.
        
        Args:
            key: Unique key for this rate limit
            limit: Maximum requests allowed
            window_seconds: Time window in seconds
            
        Returns:
            Tuple of (allowed, metadata)
        """
        now = time.time()
        window_start = now - window_seconds
        
        if self.redis_client:
            try:
                # Use Redis for distributed rate limiting
                pipe = self.redis_client.pipeline()
                
                # Remove old entries
                pipe.zremrangebyscore(key, 0, window_start)
                
                # Count current requests
                pipe.zcard(key)
                
                # Add current request
                pipe.zadd(key, {str(now): now})
                
                # Set expiration
                pipe.expire(key, window_seconds + 1)
                
                results = pipe.execute()
                current_count = results[1] + 1  # +1 for the request we just added
                
                allowed = current_count <= limit
                
                if not allowed:
                    # Remove the request we just added since it's not allowed
                    self.redis_client.zrem(key, str(now))
                
                # Get time until reset
                oldest_request = self.redis_client.zrange(key, 0, 0, withscores=True)
                if oldest_request:
                    time_until_reset = int(oldest_request[0][1] + window_seconds - now)
                else:
                    time_until_reset = window_seconds
                
                return allowed, {
                    'current_count': current_count,
                    'limit': limit,
                    'window_seconds': window_seconds,
                    'time_until_reset': max(0, time_until_reset),
                    'backend': 'redis'
                }
                
            except Exception as e:
                logger.warning(f"Redis rate limiting failed, falling back to memory: {e}")
                # Fall through to memory implementation
        
        # Memory-based fallback
        if key not in self.memory_store:
            self.memory_store[key] = []
        
        # Clean old entries
        self.memory_store[key] = [
            timestamp for timestamp in self.memory_store[key] 
            if timestamp > window_start
        ]
        
        current_count = len(self.memory_store[key])
        allowed = current_count < limit
        
        if allowed:
            self.memory_store[key].append(now)
            current_count += 1
        
        # Calculate time until reset
        if self.memory_store[key]:
            time_until_reset = int(min(self.memory_store[key]) + window_seconds - now)
        else:
            time_until_reset = 0
        
        return allowed, {
            'current_count': current_count,
            'limit': limit,
            'window_seconds': window_seconds,
            'time_until_reset': max(0, time_until_reset),
            'backend': 'memory'
        }
    
    def check_rate_limit(self, identifier: str, limits: Dict[str, Tuple[int, int]]) -> Tuple[bool, Dict[str, Any]]:
        """
        Check multiple rate limits for an identifier.
        
        Args:
            identifier: Unique identifier (user ID, IP, etc.)
            limits: Dictionary of {limit_name: (count, window_seconds)}
            
        Returns:
            Tuple of (allowed, details)
        """
        details = {'limits': {}}
        overall_allowed = True
        
        for limit_name, (count, window_seconds) in limits.items():
            key = f"{identifier}:{limit_name}"
            allowed, metadata = self._sliding_window_check(key, count, window_seconds)
            
            details['limits'][limit_name] = metadata
            
            if not allowed:
                overall_allowed = False
                details['exceeded_limit'] = limit_name
                details['retry_after'] = metadata['time_until_reset']
        
        return overall_allowed, details

# Global rate limiter instance
rate_limiter = RateLimiter()

def init_rate_limiter(app):
    """
    Initialize rate limiter with Flask app.
    
    Args:
        app: Flask application instance
    """
    global rate_limiter
    
    # Try to connect to Redis
    redis_client = None
    redis_url = app.config.get('REDIS_URL') or app.config.get('RATELIMIT_STORAGE_URL')
    
    if redis_url and redis_url != 'memory://':
        try:
            import redis
            if redis_url.startswith('redis://'):
                redis_client = redis.from_url(redis_url)
                # Test connection
                redis_client.ping()
                logger.info("Connected to Redis for rate limiting")
            else:
                logger.info("Using memory-based rate limiting")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis, using memory fallback: {e}")
    
    rate_limiter = RateLimiter(redis_client)

def get_user_rate_limits(user=None) -> Dict[str, Tuple[int, int]]:
    """
    Get rate limits for a user based on their tier.
    
    Args:
        user: User object (optional, will get current user if None)
        
    Returns:
        Dictionary of rate limits {name: (count, window_seconds)}
    """
    if user is None:
        user = get_current_user()
    
    if user:
        # Get limits based on user tier
        if user.tier == 'enterprise':
            return {
                'requests_per_minute': (1000, 60),
                'requests_per_hour': (50000, 3600),
                'predictions_per_hour': (1000, 3600),
                'predictions_per_day': (10000, 86400)
            }
        elif user.tier == 'pro':
            return {
                'requests_per_minute': (200, 60),
                'requests_per_hour': (5000, 3600),
                'predictions_per_hour': (100, 3600),
                'predictions_per_day': (1000, 86400)
            }
        else:  # free tier
            return {
                'requests_per_minute': (30, 60),
                'requests_per_hour': (500, 3600),
                'predictions_per_hour': (10, 3600),
                'predictions_per_day': (50, 86400)
            }
    else:
        # Anonymous/unauthenticated users
        return {
            'requests_per_minute': (10, 60),
            'requests_per_hour': (100, 3600)
        }

def apply_rate_limit(endpoint_type: str = 'general'):
    """
    Decorator to apply rate limiting to routes.
    
    Args:
        endpoint_type: Type of endpoint ('general', 'prediction', 'auth')
        
    Returns:
        Decorator function
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from utils.error_handlers import RateLimitError
            
            # Get client identifier
            identifier = rate_limiter._get_client_id()
            
            # Get appropriate rate limits
            user = get_current_user()
            all_limits = get_user_rate_limits(user)
            
            # Filter limits based on endpoint type
            if endpoint_type == 'prediction':
                # Prediction endpoints have stricter limits
                relevant_limits = {
                    k: v for k, v in all_limits.items() 
                    if 'prediction' in k or 'requests_per_minute' in k
                }
            elif endpoint_type == 'auth':
                # Auth endpoints have special limits
                relevant_limits = {
                    'auth_per_minute': (5, 60),
                    'auth_per_hour': (20, 3600)
                }
            else:
                # General endpoints
                relevant_limits = {
                    k: v for k, v in all_limits.items() 
                    if 'requests_per' in k
                }
            
            # Check rate limits
            allowed, details = rate_limiter.check_rate_limit(identifier, relevant_limits)
            
            if not allowed:
                # Log rate limit violation
                logger.warning(f"Rate limit exceeded for {identifier} on {endpoint_type} endpoint")
                
                # Add rate limit info to response
                raise RateLimitError(
                    message=f"Rate limit exceeded for {details.get('exceeded_limit', 'unknown limit')}",
                    retry_after=details.get('retry_after', 60)
                )
            
            # Add rate limit info to response headers (will be added by after_request)
            g.rate_limit_info = details
            
            return f(*args, **kwargs)
        
        return wrapper
    return decorator

def add_rate_limit_headers(response):
    """
    Add rate limiting headers to response.
    
    Args:
        response: Flask response object
        
    Returns:
        Modified response object
    """
    if hasattr(g, 'rate_limit_info') and g.rate_limit_info:
        # Add headers for the most restrictive limit
        most_restrictive = None
        lowest_remaining = float('inf')
        
        for limit_name, info in g.rate_limit_info.get('limits', {}).items():
            remaining = info['limit'] - info['current_count']
            if remaining < lowest_remaining:
                lowest_remaining = remaining
                most_restrictive = info
        
        if most_restrictive:
            response.headers['X-RateLimit-Limit'] = str(most_restrictive['limit'])
            response.headers['X-RateLimit-Remaining'] = str(max(0, lowest_remaining))
            response.headers['X-RateLimit-Reset'] = str(int(time.time() + most_restrictive['time_until_reset']))
            response.headers['X-RateLimit-Window'] = str(most_restrictive['window_seconds'])
    
    return response

# Specialized rate limiting functions
def check_prediction_limits(user):
    """
    Check if user can make a prediction based on their tier limits.
    
    Args:
        user: User object
        
    Returns:
        Tuple of (allowed, reason)
    """
    if not user:
        return False, "Authentication required"
    
    # Check daily prediction limit (stored in database)
    if not user.can_make_prediction():
        return False, "Daily prediction limit exceeded"
    
    # Check rate limiting
    identifier = f"user:{user.id}"
    limits = {
        'predictions_per_hour': get_user_rate_limits(user)['predictions_per_hour']
    }
    
    allowed, details = rate_limiter.check_rate_limit(identifier, limits)
    
    if not allowed:
        return False, f"Hourly prediction rate limit exceeded"
    
    return True, "OK"

def register_rate_limiting(app):
    """
    Register rate limiting with Flask app.
    
    Args:
        app: Flask application instance
    """
    # Initialize rate limiter
    init_rate_limiter(app)
    
    # Add after_request handler for rate limit headers
    @app.after_request
    def add_rate_limit_headers_to_response(response):
        return add_rate_limit_headers(response)
    
    logger.info("Rate limiting system initialized")