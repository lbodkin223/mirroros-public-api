"""
HMAC request signing for secure communication with private prediction server.
Implements request signing and verification for API security.
"""

import hashlib
import hmac
import json
import time
from typing import Dict, Any, Optional


class RequestSigner:
    """
    Handles HMAC-SHA256 signing of API requests for secure communication.
    """
    
    def __init__(self, secret_key: str):
        """
        Initialize request signer with secret key.
        
        Args:
            secret_key: Shared secret for HMAC signing
        """
        if not secret_key:
            raise ValueError("Secret key cannot be empty")
        
        self.secret_key = secret_key.encode('utf-8')
    
    def _create_string_to_sign(self, method: str, path: str, body: Dict[str, Any], 
                              timestamp: Optional[int] = None) -> str:
        """
        Create canonical string to sign from request components.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path
            body: Request body as dictionary
            timestamp: Unix timestamp (uses current time if not provided)
            
        Returns:
            Canonical string to sign
        """
        if timestamp is None:
            timestamp = int(time.time())
        
        # Create canonical request format
        canonical_request = f"{method.upper()}\n{path}\n{timestamp}\n{json.dumps(body, sort_keys=True)}"
        
        return canonical_request
    
    def sign_request(self, method: str, path: str, body: Dict[str, Any], 
                    timestamp: Optional[int] = None) -> str:
        """
        Sign a request using HMAC-SHA256.
        
        Args:
            method: HTTP method
            path: Request path
            body: Request body as dictionary
            timestamp: Unix timestamp (uses current time if not provided)
            
        Returns:
            HMAC signature as hex string
        """
        string_to_sign = self._create_string_to_sign(method, path, body, timestamp)
        
        signature = hmac.new(
            self.secret_key,
            string_to_sign.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def verify_signature(self, method: str, path: str, body: Dict[str, Any], 
                        signature: str, timestamp: int, tolerance_seconds: int = 300) -> bool:
        """
        Verify a request signature.
        
        Args:
            method: HTTP method
            path: Request path
            body: Request body as dictionary
            signature: HMAC signature to verify
            timestamp: Request timestamp
            tolerance_seconds: Maximum age of request in seconds
            
        Returns:
            True if signature is valid and within time tolerance
        """
        # Check timestamp tolerance (prevent replay attacks)
        current_time = int(time.time())
        if abs(current_time - timestamp) > tolerance_seconds:
            return False
        
        # Verify signature
        expected_signature = self.sign_request(method, path, body, timestamp)
        
        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(signature, expected_signature)


# Convenience functions for global use
_global_signer = None


def initialize_signer(secret_key: str) -> None:
    """
    Initialize global request signer.
    
    Args:
        secret_key: Shared secret for HMAC signing
    """
    global _global_signer
    _global_signer = RequestSigner(secret_key)


def sign_request(method: str, path: str, body: Dict[str, Any], 
                timestamp: Optional[int] = None) -> str:
    """
    Sign a request using the global signer.
    
    Args:
        method: HTTP method
        path: Request path
        body: Request body as dictionary
        timestamp: Unix timestamp (uses current time if not provided)
        
    Returns:
        HMAC signature as hex string
        
    Raises:
        RuntimeError: If global signer not initialized
    """
    if _global_signer is None:
        raise RuntimeError("Request signer not initialized. Call initialize_signer() first.")
    
    return _global_signer.sign_request(method, path, body, timestamp)


def verify_signature(method: str, path: str, body: Dict[str, Any], 
                    signature: str, timestamp: int, tolerance_seconds: int = 300) -> bool:
    """
    Verify a request signature using the global signer.
    
    Args:
        method: HTTP method
        path: Request path
        body: Request body as dictionary
        signature: HMAC signature to verify
        timestamp: Request timestamp
        tolerance_seconds: Maximum age of request in seconds
        
    Returns:
        True if signature is valid and within time tolerance
        
    Raises:
        RuntimeError: If global signer not initialized
    """
    if _global_signer is None:
        raise RuntimeError("Request signer not initialized. Call initialize_signer() first.")
    
    return _global_signer.verify_signature(method, path, body, signature, timestamp, tolerance_seconds)


class SignatureValidator:
    """
    Middleware for validating incoming request signatures.
    """
    
    def __init__(self, signer: RequestSigner):
        """
        Initialize signature validator.
        
        Args:
            signer: RequestSigner instance
        """
        self.signer = signer
    
    def validate_request(self, method: str, path: str, body: Dict[str, Any], 
                        headers: Dict[str, str]) -> bool:
        """
        Validate an incoming request signature.
        
        Args:
            method: HTTP method
            path: Request path
            body: Request body as dictionary
            headers: Request headers
            
        Returns:
            True if signature is valid
        """
        signature = headers.get('X-Signature')
        timestamp_str = headers.get('X-Timestamp')
        
        if not signature or not timestamp_str:
            return False
        
        try:
            timestamp = int(timestamp_str)
        except ValueError:
            return False
        
        return self.signer.verify_signature(method, path, body, signature, timestamp)


def create_signed_headers(method: str, path: str, body: Dict[str, Any], 
                         secret_key: str, additional_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Create headers with HMAC signature for a request.
    
    Args:
        method: HTTP method
        path: Request path
        body: Request body as dictionary
        secret_key: Shared secret for signing
        additional_headers: Additional headers to include
        
    Returns:
        Dictionary of headers including signature and timestamp
    """
    signer = RequestSigner(secret_key)
    timestamp = int(time.time())
    signature = signer.sign_request(method, path, body, timestamp)
    
    headers = {
        'X-Signature': signature,
        'X-Timestamp': str(timestamp),
        'Content-Type': 'application/json'
    }
    
    if additional_headers:
        headers.update(additional_headers)
    
    return headers


def validate_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Validate webhook signature (for external webhooks like Stripe).
    
    Args:
        payload: Raw request payload as bytes
        signature: Signature from webhook headers
        secret: Webhook secret
        
    Returns:
        True if signature is valid
    """
    try:
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        # Handle different signature formats
        if signature.startswith('sha256='):
            signature = signature[7:]  # Remove 'sha256=' prefix
        
        return hmac.compare_digest(signature, expected_signature)
        
    except Exception:
        return False