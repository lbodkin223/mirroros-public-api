"""
Monitoring and observability configuration for MirrorOS Public API.
Integrates with Sentry, DataDog, and other monitoring services.
"""

import os
import logging
from typing import Dict, Any
from flask import Flask, request, g
import time

logger = logging.getLogger(__name__)

class MonitoringConfig:
    """Configuration for monitoring and observability."""
    
    def __init__(self, app: Flask = None):
        """
        Initialize monitoring configuration.
        
        Args:
            app: Flask application instance
        """
        self.app = app
        self.sentry_sdk = None
        self.datadog = None
        
        if app:
            self.init_app(app)
    
    def init_app(self, app: Flask):
        """
        Initialize monitoring with Flask app.
        
        Args:
            app: Flask application instance
        """
        self.app = app
        
        # Initialize Sentry for error tracking
        self._init_sentry(app)
        
        # Initialize DataDog for metrics
        self._init_datadog(app)
        
        # Initialize custom metrics
        self._init_custom_metrics(app)
        
        # Setup request tracking
        self._setup_request_tracking(app)
        
        logger.info("Monitoring system initialized")
    
    def _init_sentry(self, app: Flask):
        """Initialize Sentry error tracking."""
        sentry_dsn = app.config.get('SENTRY_DSN')
        
        if not sentry_dsn:
            logger.info("SENTRY_DSN not configured, skipping Sentry initialization")
            return
        
        try:
            import sentry_sdk
            from sentry_sdk.integrations.flask import FlaskIntegration
            from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
            from sentry_sdk.integrations.redis import RedisIntegration
            
            # Configure Sentry
            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=[
                    FlaskIntegration(
                        transaction_style='endpoint'
                    ),
                    SqlalchemyIntegration(),
                    RedisIntegration(),
                ],
                traces_sample_rate=0.1,  # 10% of transactions
                send_default_pii=False,  # Don't send PII
                environment=app.config.get('ENVIRONMENT', 'development'),
                release=app.config.get('VERSION', 'unknown'),
                before_send=self._filter_sentry_events,
            )
            
            self.sentry_sdk = sentry_sdk
            logger.info("Sentry error tracking initialized")
            
        except ImportError:
            logger.warning("sentry-sdk not installed, error tracking disabled")
        except Exception as e:
            logger.error(f"Failed to initialize Sentry: {e}")
    
    def _filter_sentry_events(self, event: Dict[str, Any], hint: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter and sanitize Sentry events.
        
        Args:
            event: Sentry event data
            hint: Sentry hint data
            
        Returns:
            Filtered event data or None to drop the event
        """
        # Don't send health check errors
        if 'request' in event and event['request'].get('url', '').endswith('/health'):
            return None
        
        # Don't send rate limit errors (they're expected)
        if 'exception' in event:
            for exception in event['exception']['values']:
                if 'rate_limit' in exception.get('type', '').lower():
                    return None
        
        # Sanitize sensitive data
        if 'request' in event:
            # Remove authorization headers
            headers = event['request'].get('headers', {})
            if 'Authorization' in headers:
                headers['Authorization'] = '[Filtered]'
            
            # Remove sensitive form data
            data = event['request'].get('data')
            if isinstance(data, dict):
                for key in ['password', 'token', 'secret']:
                    if key in data:
                        data[key] = '[Filtered]'
        
        return event
    
    def _init_datadog(self, app: Flask):
        """Initialize DataDog metrics and APM."""
        datadog_api_key = app.config.get('DATADOG_API_KEY')
        
        if not datadog_api_key:
            logger.info("DATADOG_API_KEY not configured, skipping DataDog initialization")
            return
        
        try:
            from datadog import initialize, statsd
            
            # Initialize DataDog
            options = {
                'api_key': datadog_api_key,
                'app_key': app.config.get('DATADOG_APP_KEY'),
            }
            
            initialize(**options)
            self.datadog = statsd
            
            logger.info("DataDog metrics initialized")
            
        except ImportError:
            logger.warning("datadog not installed, metrics disabled")
        except Exception as e:
            logger.error(f"Failed to initialize DataDog: {e}")
    
    def _init_custom_metrics(self, app: Flask):
        """Initialize custom metrics collection."""
        # Store metrics in app context for easy access
        app.config['METRICS'] = {
            'requests_total': 0,
            'requests_by_status': {},
            'response_times': [],
            'prediction_requests': 0,
            'auth_requests': 0,
            'errors_total': 0,
        }
    
    def _setup_request_tracking(self, app: Flask):
        """Setup request/response tracking middleware."""
        
        @app.before_request
        def track_request_start():
            """Track request start time and metadata."""
            g.start_time = time.time()
            g.request_id = self._generate_request_id()
            
            # Increment request counter
            app.config['METRICS']['requests_total'] += 1
            
            # Track by endpoint
            endpoint = request.endpoint or 'unknown'
            if endpoint.startswith('auth.'):
                app.config['METRICS']['auth_requests'] += 1
            elif 'predict' in endpoint:
                app.config['METRICS']['prediction_requests'] += 1
            
            # Send to DataDog if available
            if self.datadog:
                self.datadog.increment('mirroros.requests.total', tags=[
                    f'endpoint:{endpoint}',
                    f'method:{request.method}'
                ])
        
        @app.after_request
        def track_request_end(response):
            """Track request completion and metrics."""
            if hasattr(g, 'start_time'):
                # Calculate response time
                response_time = time.time() - g.start_time
                app.config['METRICS']['response_times'].append(response_time)
                
                # Track by status code
                status_code = response.status_code
                status_key = f"{status_code//100}xx"
                app.config['METRICS']['requests_by_status'][status_key] = \
                    app.config['METRICS']['requests_by_status'].get(status_key, 0) + 1
                
                # Track errors
                if status_code >= 400:
                    app.config['METRICS']['errors_total'] += 1
                
                # Add request ID to response headers
                if hasattr(g, 'request_id'):
                    response.headers['X-Request-ID'] = g.request_id
                
                # Send to DataDog if available
                if self.datadog:
                    self.datadog.timing('mirroros.response_time', response_time * 1000, tags=[
                        f'endpoint:{request.endpoint or "unknown"}',
                        f'status:{status_code}',
                        f'method:{request.method}'
                    ])
                    
                    self.datadog.increment('mirroros.responses.total', tags=[
                        f'status:{status_code}',
                        f'endpoint:{request.endpoint or "unknown"}'
                    ])
            
            return response
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def track_custom_metric(self, metric_name: str, value: float = 1, tags: list = None):
        """
        Track custom metric.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            tags: Optional tags for the metric
        """
        tags = tags or []
        
        # Send to DataDog if available
        if self.datadog:
            self.datadog.increment(f'mirroros.{metric_name}', value, tags=tags)
        
        # Log for debugging
        logger.debug(f"Metric: {metric_name} = {value}, tags: {tags}")
    
    def track_user_action(self, action: str, user_id: str = None, metadata: Dict[str, Any] = None):
        """
        Track user action for analytics.
        
        Args:
            action: Action name (e.g., 'prediction_made', 'user_registered')
            user_id: User identifier (optional)
            metadata: Additional metadata
        """
        tags = [f'action:{action}']
        
        if user_id:
            # Hash user ID for privacy
            import hashlib
            user_hash = hashlib.sha256(user_id.encode()).hexdigest()[:8]
            tags.append(f'user_hash:{user_hash}')
        
        if metadata:
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    tags.append(f'{key}:{value}')
        
        self.track_custom_metric('user_actions', tags=tags)
    
    def get_health_metrics(self) -> Dict[str, Any]:
        """
        Get current health metrics.
        
        Returns:
            Dictionary of health metrics
        """
        metrics = self.app.config.get('METRICS', {})
        
        # Calculate average response time
        response_times = metrics.get('response_times', [])
        avg_response_time = sum(response_times[-100:]) / len(response_times[-100:]) if response_times else 0
        
        # Calculate error rate
        total_requests = metrics.get('requests_total', 0)
        total_errors = metrics.get('errors_total', 0)
        error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'requests_total': total_requests,
            'requests_by_status': metrics.get('requests_by_status', {}),
            'avg_response_time_ms': round(avg_response_time * 1000, 2),
            'error_rate_percent': round(error_rate, 2),
            'prediction_requests': metrics.get('prediction_requests', 0),
            'auth_requests': metrics.get('auth_requests', 0),
            'uptime_seconds': time.time() - self.app.config.get('START_TIME', time.time())
        }

# Global monitoring instance
monitoring = MonitoringConfig()

def init_monitoring(app: Flask):
    """
    Initialize monitoring with Flask app.
    
    Args:
        app: Flask application instance
    """
    # Store app start time
    app.config['START_TIME'] = time.time()
    
    # Initialize monitoring
    monitoring.init_app(app)
    
    # Add health endpoint with metrics
    @app.route('/health')
    def health():
        """Enhanced health check with metrics."""
        health_metrics = monitoring.get_health_metrics()
        
        # Determine health status
        status = 'healthy'
        if health_metrics['error_rate_percent'] > 10:
            status = 'degraded'
        if health_metrics['avg_response_time_ms'] > 5000:
            status = 'slow'
        
        return {
            'status': status,
            'service': 'mirroros-public-api',
            'version': app.config.get('VERSION', 'unknown'),
            'environment': app.config.get('ENVIRONMENT', 'unknown'),
            'metrics': health_metrics
        }
    
    # Add metrics endpoint
    @app.route('/metrics')
    def metrics():
        """Prometheus-style metrics endpoint."""
        metrics_data = monitoring.get_health_metrics()
        
        # Convert to Prometheus format
        lines = []
        lines.append(f"# HELP mirroros_requests_total Total number of requests")
        lines.append(f"# TYPE mirroros_requests_total counter")
        lines.append(f"mirroros_requests_total {metrics_data['requests_total']}")
        
        lines.append(f"# HELP mirroros_response_time_ms Average response time in milliseconds")
        lines.append(f"# TYPE mirroros_response_time_ms gauge")
        lines.append(f"mirroros_response_time_ms {metrics_data['avg_response_time_ms']}")
        
        lines.append(f"# HELP mirroros_error_rate_percent Error rate percentage")
        lines.append(f"# TYPE mirroros_error_rate_percent gauge")
        lines.append(f"mirroros_error_rate_percent {metrics_data['error_rate_percent']}")
        
        return '\n'.join(lines), 200, {'Content-Type': 'text/plain'}

def track_prediction_request(user_tier: str, success: bool, response_time_ms: int):
    """
    Track prediction request metrics.
    
    Args:
        user_tier: User subscription tier
        success: Whether the request was successful
        response_time_ms: Response time in milliseconds
    """
    tags = [
        f'tier:{user_tier}',
        f'success:{success}'
    ]
    
    monitoring.track_custom_metric('prediction_requests', tags=tags)
    monitoring.track_custom_metric('prediction_response_time', response_time_ms, tags=tags)

def track_payment_event(event_type: str, amount_cents: int = None, success: bool = True):
    """
    Track payment-related events.
    
    Args:
        event_type: Type of payment event
        amount_cents: Payment amount in cents
        success: Whether the payment was successful
    """
    tags = [
        f'event_type:{event_type}',
        f'success:{success}'
    ]
    
    monitoring.track_custom_metric('payment_events', tags=tags)
    
    if amount_cents:
        monitoring.track_custom_metric('payment_amount_cents', amount_cents, tags=tags)