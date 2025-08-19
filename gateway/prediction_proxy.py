"""
Prediction proxy for MirrorOS Public API.
Forwards authenticated requests to private prediction server with HMAC signing.
"""

import logging
import time
import hashlib
import json
from typing import Dict, Any, Optional, Tuple
import requests
from flask import Blueprint, request, jsonify, current_app

from database import db
from auth.models import User, PredictionRequest
from auth.middleware import require_auth, get_current_user, check_rate_limit, log_user_activity
from security.request_signer import sign_request, RequestSigner

# Setup logging
logger = logging.getLogger(__name__)

# Create blueprint
prediction_proxy_bp = Blueprint('prediction_proxy', __name__)

def hash_request_data(data: Dict[str, Any]) -> str:
    """
    Create a hash of request data for logging and deduplication.
    
    Args:
        data: Request data dictionary
        
    Returns:
        SHA-256 hash of the request data
    """
    # Remove sensitive fields and create a normalized hash
    safe_data = {
        'goal_length': len(data.get('goal', '')),
        'has_timeframe': bool(data.get('timeframe')),
        'has_context': bool(data.get('context')),
        'options': data.get('options', {})
    }
    
    data_string = json.dumps(safe_data, sort_keys=True)
    return hashlib.sha256(data_string.encode()).hexdigest()

def validate_prediction_request(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate prediction request data.
    
    Args:
        data: Request data to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(data, dict):
        return False, "Request body must be a JSON object"
    
    goal = data.get('goal', '').strip()
    if not goal:
        return False, "Goal description is required"
    
    if len(goal) < 10:
        return False, "Goal description must be at least 10 characters"
    
    if len(goal) > 5000:
        return False, "Goal description must be less than 5000 characters"
    
    # Validate options if provided
    options = data.get('options', {})
    if not isinstance(options, dict):
        return False, "Options must be a JSON object"
    
    # Validate timeframe if provided
    timeframe = data.get('timeframe', '')
    if timeframe and len(timeframe) > 100:
        return False, "Timeframe must be less than 100 characters"
    
    # Validate context if provided
    context = data.get('context', '')
    if context and len(context) > 1000:
        return False, "Context must be less than 1000 characters"
    
    return True, None

def sanitize_request_for_logging(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize request data for safe logging (remove PII).
    
    Args:
        data: Original request data
        
    Returns:
        Sanitized data safe for logging
    """
    return {
        'goal_length': len(data.get('goal', '')),
        'has_timeframe': bool(data.get('timeframe')),
        'has_context': bool(data.get('context')),
        'timeframe_length': len(data.get('timeframe', '')),
        'context_length': len(data.get('context', '')),
        'options': data.get('options', {}),
        'request_hash': hash_request_data(data)
    }

def log_prediction_request(user: User, request_data: Dict[str, Any], success: bool, 
                         error_code: Optional[str] = None, response_time_ms: Optional[int] = None) -> None:
    """
    Log prediction request to database for analytics.
    
    Args:
        user: User who made the request
        request_data: Original request data
        success: Whether the request was successful
        error_code: Error code if request failed
        response_time_ms: Response time in milliseconds
    """
    try:
        prediction_request = PredictionRequest(
            user_id=user.id,
            request_data_hash=hash_request_data(request_data),
            success=success,
            error_code=error_code,
            response_time_ms=response_time_ms
        )
        
        db.session.add(prediction_request)
        db.session.commit()
        
    except Exception as e:
        logger.error(f"Failed to log prediction request: {str(e)}")
        db.session.rollback()

@prediction_proxy_bp.route('/predict', methods=['POST'])
@check_rate_limit
def predict():
    """
    Proxy prediction requests to private server.
    
    Expected JSON:
        {
            "goal": "I want to get a job at OpenAI within 6 months",
            "timeframe": "6 months",  // optional
            "context": "I have 3 years of ML experience",  // optional
            "options": {  // optional
                "enhanced_grounding": true,
                "confidence_level": "high"
            }
        }
    
    Returns:
        200: Prediction result from private server
        400: Validation error
        429: Rate limit exceeded
        500: Server error
        502: Private server error
        503: Private server unavailable
    """
    start_time = time.time()
    user = get_current_user()
    
    try:
        # Get and validate request data
        data = request.get_json()
        
        if not data:
            return jsonify({
                'error': 'invalid_request',
                'message': 'Request body must be valid JSON'
            }), 400
        
        # Validate request data
        is_valid, error_message = validate_prediction_request(data)
        if not is_valid:
            log_prediction_request(user, data, False, 'validation_error')
            return jsonify({
                'error': 'validation_error',
                'message': error_message
            }), 400
        
        # Log user activity
        log_user_activity('prediction_request', sanitize_request_for_logging(data))
        
        # Prepare request for private server
        private_api_url = current_app.config.get('PRIVATE_API_URL')
        private_api_secret = current_app.config.get('PRIVATE_API_SECRET')
        
        if not private_api_url:
            logger.error("PRIVATE_API_URL not configured")
            log_prediction_request(user, data, False, 'configuration_error')
            return jsonify({
                'error': 'service_unavailable',
                'message': 'Prediction service is not available'
            }), 503
        
        # Ensure URL has proper scheme
        if not private_api_url.startswith(('http://', 'https://')):
            private_api_url = f'https://{private_api_url}'
        
        # Add user context to request
        request_payload = {
            'user_id': str(user.id),
            'user_tier': user.tier,
            'request_id': f"req_{int(time.time() * 1000)}",
            'prediction_data': data
        }
        
        # Sign the request if secret is available
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'MirrorOS-Public-API/1.0',
            'X-User-Tier': user.tier,
            'X-Request-ID': request_payload['request_id']
        }
        
        if private_api_secret:
            try:
                signer = RequestSigner(private_api_secret)
                signature = signer.sign_request('POST', '/api/predict', request_payload)
                headers['X-Signature'] = signature
                headers['X-Timestamp'] = str(int(time.time()))
            except Exception as e:
                logger.error(f"Failed to sign request: {str(e)}")
                log_prediction_request(user, data, False, 'signing_error')
                return jsonify({
                    'error': 'internal_error',
                    'message': 'Failed to prepare request'
                }), 500
        
        # Make request to private server
        try:
            response = requests.post(
                f"{private_api_url}/api/predict",
                json=request_payload,
                headers=headers,
                timeout=30  # 30 second timeout
            )
            
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Handle different response codes
            if response.status_code == 200:
                result = response.json()
                
                # Increment user's usage counter
                user.increment_prediction_usage()
                
                # Log successful request
                log_prediction_request(user, data, True, None, response_time_ms)
                
                # Add metadata to response
                if isinstance(result, dict):
                    result['metadata'] = {
                        'user_tier': user.tier,
                        'response_time_ms': response_time_ms,
                        'request_id': request_payload['request_id'],
                        'predictions_remaining_today': max(0, user.get_tier_limits()['predictions_per_day'] - user.predictions_used_today) if user.get_tier_limits()['predictions_per_day'] != -1 else -1
                    }
                
                logger.info(f"Prediction successful for user {user.email} ({response_time_ms}ms)")
                return jsonify(result), 200
            
            elif response.status_code == 400:
                # Client error from private server
                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {'error': 'bad_request'}
                log_prediction_request(user, data, False, 'client_error', response_time_ms)
                
                return jsonify({
                    'error': 'prediction_error',
                    'message': error_data.get('message', 'Invalid prediction request'),
                    'details': error_data.get('details')
                }), 400
            
            elif response.status_code == 429:
                # Rate limit on private server
                log_prediction_request(user, data, False, 'private_rate_limit', response_time_ms)
                
                return jsonify({
                    'error': 'service_busy',
                    'message': 'Prediction service is currently busy. Please try again later.'
                }), 429
            
            else:
                # Server error from private server
                logger.error(f"Private server error: {response.status_code} - {response.text}")
                log_prediction_request(user, data, False, 'server_error', response_time_ms)
                
                return jsonify({
                    'error': 'prediction_failed',
                    'message': 'Prediction service encountered an error'
                }), 502
        
        except requests.exceptions.Timeout:
            response_time_ms = int((time.time() - start_time) * 1000)
            logger.error("Private server request timeout")
            log_prediction_request(user, data, False, 'timeout', response_time_ms)
            
            return jsonify({
                'error': 'request_timeout',
                'message': 'Prediction request timed out. Please try again.'
            }), 504
        
        except requests.exceptions.ConnectionError:
            response_time_ms = int((time.time() - start_time) * 1000)
            logger.error("Cannot connect to private server")
            log_prediction_request(user, data, False, 'connection_error', response_time_ms)
            
            return jsonify({
                'error': 'service_unavailable',
                'message': 'Prediction service is temporarily unavailable'
            }), 503
        
        except requests.exceptions.RequestException as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Request error to private server: {str(e)}")
            log_prediction_request(user, data, False, 'request_error', response_time_ms)
            
            return jsonify({
                'error': 'request_failed',
                'message': 'Failed to process prediction request'
            }), 502
        
    except Exception as e:
        response_time_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Unexpected error in prediction proxy: {str(e)}")
        
        if 'user' in locals() and 'data' in locals():
            log_prediction_request(user, data, False, 'internal_error', response_time_ms)
        
        return jsonify({
            'error': 'internal_error',
            'message': 'An unexpected error occurred'
        }), 500

@prediction_proxy_bp.route('/predict/health', methods=['GET'])
def prediction_health():
    """
    Check health of prediction service.
    
    Returns:
        200: Service is healthy
        503: Service is unavailable
    """
    try:
        private_api_url = current_app.config.get('PRIVATE_API_URL')
        
        if not private_api_url:
            return jsonify({
                'status': 'unhealthy',
                'message': 'Private API URL not configured'
            }), 503
        
        # Ensure URL has proper scheme
        if not private_api_url.startswith(('http://', 'https://')):
            private_api_url = f'https://{private_api_url}'
        
        # Quick health check to private server
        response = requests.get(
            f"{private_api_url}/health",
            timeout=5
        )
        
        if response.status_code == 200:
            return jsonify({
                'status': 'healthy',
                'private_server': 'available',
                'response_time_ms': response.elapsed.total_seconds() * 1000
            }), 200
        else:
            return jsonify({
                'status': 'unhealthy',
                'private_server': 'error',
                'status_code': response.status_code
            }), 503
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'private_server': 'unavailable',
            'error': str(e)
        }), 503

@prediction_proxy_bp.route('/predict/usage', methods=['GET'])
@require_auth
def get_prediction_usage():
    """
    Get user's prediction usage statistics.
    
    Returns:
        200: Usage statistics
        500: Server error
    """
    try:
        user = get_current_user()
        limits = user.get_tier_limits()
        
        # Get recent prediction requests
        recent_requests = PredictionRequest.query.filter_by(
            user_id=user.id
        ).order_by(
            PredictionRequest.created_at.desc()
        ).limit(10).all()
        
        # Calculate success rate
        total_requests = PredictionRequest.query.filter_by(user_id=user.id).count()
        successful_requests = PredictionRequest.query.filter_by(user_id=user.id, success=True).count()
        success_rate = (successful_requests / total_requests * 100) if total_requests > 0 else 0
        
        return jsonify({
            'tier': user.tier,
            'limits': limits,
            'usage': {
                'predictions_used_today': user.predictions_used_today,
                'predictions_remaining_today': max(0, limits['predictions_per_day'] - user.predictions_used_today) if limits['predictions_per_day'] != -1 else -1,
                'total_predictions': total_requests,
                'successful_predictions': successful_requests,
                'success_rate_percent': round(success_rate, 1),
                'can_make_prediction': user.can_make_prediction()
            },
            'recent_requests': [req.to_dict() for req in recent_requests]
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting prediction usage: {str(e)}")
        return jsonify({
            'error': 'usage_fetch_failed',
            'message': 'Failed to fetch usage statistics'
        }), 500