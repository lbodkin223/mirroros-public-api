"""
Standardized error handling utilities for MirrorOS Public API.
Provides consistent error responses across all endpoints.
"""

import logging
from typing import Dict, Any, Optional, Tuple
from flask import jsonify, current_app
from werkzeug.exceptions import HTTPException
import traceback

# Setup logging
logger = logging.getLogger(__name__)

class APIError(Exception):
    """
    Custom API exception with standardized error format.
    
    Attributes:
        error_code: Machine-readable error code
        message: Human-readable error message
        status_code: HTTP status code
        details: Optional additional error details
    """
    
    def __init__(self, error_code: str, message: str, status_code: int = 400, details: Optional[Dict[str, Any]] = None):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON response."""
        error_dict = {
            'error': self.error_code,
            'message': self.message
        }
        
        if self.details:
            error_dict['details'] = self.details
            
        return error_dict

class ValidationError(APIError):
    """Validation error (400)"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__('validation_error', message, 400, details)

class AuthenticationError(APIError):
    """Authentication error (401)"""
    def __init__(self, message: str = 'Authentication required'):
        super().__init__('authentication_required', message, 401)

class AuthorizationError(APIError):
    """Authorization error (403)"""
    def __init__(self, message: str = 'Insufficient permissions'):
        super().__init__('insufficient_permissions', message, 403)

class NotFoundError(APIError):
    """Resource not found error (404)"""
    def __init__(self, message: str = 'Resource not found'):
        super().__init__('resource_not_found', message, 404)

class ConflictError(APIError):
    """Resource conflict error (409)"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__('resource_conflict', message, 409, details)

class RateLimitError(APIError):
    """Rate limit exceeded error (429)"""
    def __init__(self, message: str = 'Rate limit exceeded', retry_after: Optional[int] = None):
        details = {'retry_after': retry_after} if retry_after else None
        super().__init__('rate_limit_exceeded', message, 429, details)

class PaymentError(APIError):
    """Payment processing error (402)"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__('payment_error', message, 402, details)

class ServiceUnavailableError(APIError):
    """Service unavailable error (503)"""
    def __init__(self, message: str = 'Service temporarily unavailable'):
        super().__init__('service_unavailable', message, 503)

def handle_api_error(error: APIError) -> Tuple[Dict[str, Any], int]:
    """
    Handle custom API errors.
    
    Args:
        error: APIError instance
        
    Returns:
        Tuple of (error_dict, status_code)
    """
    logger.warning(f"API Error {error.status_code}: {error.error_code} - {error.message}")
    return error.to_dict(), error.status_code

def handle_http_exception(error: HTTPException) -> Tuple[Dict[str, Any], int]:
    """
    Handle standard HTTP exceptions.
    
    Args:
        error: HTTPException instance
        
    Returns:
        Tuple of (error_dict, status_code)
    """
    logger.warning(f"HTTP Exception {error.code}: {error.description}")
    
    # Map common HTTP errors to our format
    error_map = {
        400: ('bad_request', 'Bad request'),
        401: ('unauthorized', 'Authentication required'),
        403: ('forbidden', 'Access forbidden'),
        404: ('not_found', 'Resource not found'),
        405: ('method_not_allowed', 'Method not allowed'),
        422: ('unprocessable_entity', 'Unprocessable entity'),
        500: ('internal_error', 'Internal server error'),
        502: ('bad_gateway', 'Bad gateway'),
        503: ('service_unavailable', 'Service unavailable'),
        504: ('gateway_timeout', 'Gateway timeout')
    }
    
    error_code, default_message = error_map.get(error.code, ('unknown_error', 'Unknown error'))
    
    return {
        'error': error_code,
        'message': error.description or default_message
    }, error.code

def handle_generic_exception(error: Exception) -> Tuple[Dict[str, Any], int]:
    """
    Handle unexpected exceptions.
    
    Args:
        error: Exception instance
        
    Returns:
        Tuple of (error_dict, status_code)
    """
    # Log the full traceback for debugging
    logger.error(f"Unexpected error: {str(error)}", exc_info=True)
    
    # Don't expose internal error details in production
    if current_app.config.get('DEBUG', False):
        message = f"Internal error: {str(error)}"
        details = {'traceback': traceback.format_exc()}
    else:
        message = "An unexpected error occurred"
        details = None
    
    error_dict = {
        'error': 'internal_error',
        'message': message
    }
    
    if details:
        error_dict['details'] = details
    
    return error_dict, 500

def handle_stripe_error(error) -> APIError:
    """
    Convert Stripe errors to APIError instances.
    
    Args:
        error: Stripe exception
        
    Returns:
        APIError instance
    """
    # Import stripe dynamically to avoid dependency issues
    try:
        import stripe
    except ImportError:
        return APIError('payment_error', 'Payment processing failed', 500)
    
    if isinstance(error, stripe.error.CardError):
        # Card was declined
        return PaymentError(
            message="Your card was declined",
            details={
                'decline_code': error.decline_code,
                'charge_id': error.json_body.get('error', {}).get('charge')
            }
        )
    elif isinstance(error, stripe.error.RateLimitError):
        return RateLimitError("Too many requests to payment processor")
    elif isinstance(error, stripe.error.InvalidRequestError):
        return ValidationError(
            message="Invalid payment request",
            details={'stripe_error': str(error)}
        )
    elif isinstance(error, stripe.error.AuthenticationError):
        logger.error(f"Stripe authentication error: {str(error)}")
        return ServiceUnavailableError("Payment service authentication failed")
    elif isinstance(error, stripe.error.APIConnectionError):
        return ServiceUnavailableError("Payment service temporarily unavailable")
    elif isinstance(error, stripe.error.StripeError):
        return PaymentError(
            message="Payment processing failed",
            details={'stripe_error': str(error)}
        )
    else:
        return APIError('payment_error', 'Unknown payment error', 500)

def handle_database_error(error) -> APIError:
    """
    Convert database errors to APIError instances.
    
    Args:
        error: Database exception
        
    Returns:
        APIError instance
    """
    # Import SQLAlchemy dynamically
    try:
        from sqlalchemy.exc import IntegrityError, OperationalError, StatementError
    except ImportError:
        return APIError('database_error', 'Database operation failed', 500)
    
    if isinstance(error, IntegrityError):
        # Handle unique constraint violations
        if 'unique constraint' in str(error).lower():
            return ConflictError("Resource already exists")
        elif 'foreign key constraint' in str(error).lower():
            return ValidationError("Invalid reference to related resource")
        else:
            return ValidationError("Data integrity constraint violated")
    elif isinstance(error, OperationalError):
        logger.error(f"Database operational error: {str(error)}")
        return ServiceUnavailableError("Database temporarily unavailable")
    elif isinstance(error, StatementError):
        return ValidationError("Invalid data format")
    else:
        logger.error(f"Unknown database error: {str(error)}")
        return APIError('database_error', 'Database operation failed', 500)

def register_error_handlers(app):
    """
    Register error handlers with Flask application.
    
    Args:
        app: Flask application instance
    """
    
    @app.errorhandler(APIError)
    def handle_api_error_route(error):
        response_data, status_code = handle_api_error(error)
        return jsonify(response_data), status_code
    
    @app.errorhandler(HTTPException)
    def handle_http_exception_route(error):
        response_data, status_code = handle_http_exception(error)
        return jsonify(response_data), status_code
    
    @app.errorhandler(Exception)
    def handle_generic_exception_route(error):
        # Handle specific exception types first
        try:
            import stripe
            if isinstance(error, stripe.error.StripeError):
                api_error = handle_stripe_error(error)
                response_data, status_code = handle_api_error(api_error)
                return jsonify(response_data), status_code
        except ImportError:
            pass
        
        try:
            from sqlalchemy.exc import SQLAlchemyError
            if isinstance(error, SQLAlchemyError):
                api_error = handle_database_error(error)
                response_data, status_code = handle_api_error(api_error)
                return jsonify(response_data), status_code
        except ImportError:
            pass
        
        # Handle generic exceptions
        response_data, status_code = handle_generic_exception(error)
        return jsonify(response_data), status_code

# Context manager for handling errors in routes
class error_handler:
    """
    Context manager for standardized error handling in routes.
    
    Usage:
        with error_handler():
            # Route logic here
            return success_response
    """
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            if isinstance(exc_val, APIError):
                # Re-raise APIError to be handled by Flask error handler
                return False
            
            # Convert other exceptions to APIError
            if hasattr(exc_val, '__module__') and 'stripe' in exc_val.__module__:
                api_error = handle_stripe_error(exc_val)
                raise api_error from exc_val
            
            # Let other exceptions be handled by generic handler
            return False
        
        return True

def validate_json_request(required_fields: list = None, optional_fields: list = None):
    """
    Decorator to validate JSON request data.
    
    Args:
        required_fields: List of required field names
        optional_fields: List of optional field names
        
    Returns:
        Decorator function
    """
    def decorator(f):
        def wrapper(*args, **kwargs):
            from flask import request
            
            data = request.get_json()
            if not data:
                raise ValidationError("Request body must be valid JSON")
            
            # Check required fields
            if required_fields:
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    raise ValidationError(
                        f"Missing required fields: {', '.join(missing_fields)}",
                        details={'missing_fields': missing_fields}
                    )
            
            # Validate field types if specified
            for field, value in data.items():
                if value is None:
                    continue
                
                # Add type validation here if needed
                # Example: if field == 'email' and not isinstance(value, str):
                #     raise ValidationError(f"Field '{field}' must be a string")
            
            return f(*args, **kwargs)
        
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator