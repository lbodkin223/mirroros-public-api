"""
User authentication models for MirrorOS Public API.
SQLAlchemy models for PostgreSQL database.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.dialects.postgresql import UUID
from database import db

class User(db.Model):
    """
    User model for authentication and subscription management.
    
    Attributes:
        id: Unique user identifier (UUID)
        email: User's email address (unique)
        password_hash: Hashed password
        full_name: User's full name
        tier: Subscription tier (free, pro, enterprise)
        is_active: Whether the user account is active
        is_verified: Whether the user's email is verified
        created_at: Account creation timestamp
        updated_at: Last update timestamp
        last_login_at: Last login timestamp
    """
    
    __tablename__ = 'users'
    
    # Primary key
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Authentication fields
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Profile fields
    full_name = db.Column(db.String(255), nullable=True)
    
    # Account status
    tier = db.Column(db.String(20), default='free', nullable=False)  # free, pro, enterprise
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    
    # Usage tracking
    predictions_used_today = db.Column(db.Integer, default=0, nullable=False)
    last_reset_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    
    # Timestamps
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)
    
    # Relationships
    subscription = db.relationship('Subscription', back_populates='user', uselist=False)
    prediction_requests = db.relationship('PredictionRequest', back_populates='user')
    
    def __init__(self, email: str, password: str, full_name: Optional[str] = None):
        """
        Initialize a new user.
        
        Args:
            email: User's email address
            password: Plain text password (will be hashed)
            full_name: Optional full name
        """
        self.email = email.lower().strip()
        self.set_password(password)
        self.full_name = full_name.strip() if full_name else None
    
    def set_password(self, password: str) -> None:
        """
        Hash and set the user's password.
        
        Args:
            password: Plain text password to hash
        """
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password: str) -> bool:
        """
        Check if the provided password matches the stored hash.
        
        Args:
            password: Plain text password to check
            
        Returns:
            True if password matches, False otherwise
        """
        return check_password_hash(self.password_hash, password)
    
    def update_last_login(self) -> None:
        """Update the last login timestamp."""
        self.last_login_at = datetime.now(timezone.utc)
        db.session.commit()
    
    def get_tier_limits(self) -> Dict[str, int]:
        """
        Get usage limits based on user's subscription tier.
        
        Returns:
            Dictionary with usage limits for the user's tier
        """
        limits = {
            'free': {
                'predictions_per_day': 3,
                'max_requests_per_hour': 10,
            },
            'pro': {
                'predictions_per_day': 50,
                'max_requests_per_hour': 100,
            },
            'enterprise': {
                'predictions_per_day': -1,  # unlimited
                'max_requests_per_hour': -1,  # unlimited
            }
        }
        return limits.get(self.tier, limits['free'])
    
    def can_make_prediction(self) -> bool:
        """
        Check if user can make a prediction based on their tier limits.
        
        Returns:
            True if user can make a prediction, False otherwise
        """
        # Reset daily counter if needed
        today = datetime.now(timezone.utc).date()
        if self.last_reset_date != today:
            self.predictions_used_today = 0
            self.last_reset_date = today
            db.session.commit()
        
        limits = self.get_tier_limits()
        daily_limit = limits['predictions_per_day']
        
        # Unlimited tier
        if daily_limit == -1:
            return True
        
        return self.predictions_used_today < daily_limit
    
    def increment_prediction_usage(self) -> None:
        """Increment the prediction usage counter."""
        self.predictions_used_today += 1
        self.updated_at = datetime.now(timezone.utc)
        db.session.commit()
    
    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """
        Convert user object to dictionary for JSON serialization.
        
        Args:
            include_sensitive: Whether to include sensitive fields
            
        Returns:
            Dictionary representation of the user
        """
        data = {
            'id': str(self.id),
            'email': self.email,
            'full_name': self.full_name,
            'tier': self.tier,
            'is_active': self.is_active,
            'is_verified': self.is_verified,
            'predictions_used_today': self.predictions_used_today,
            'tier_limits': self.get_tier_limits(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
        }
        
        if include_sensitive:
            data['password_hash'] = self.password_hash
        
        return data
    
    def __repr__(self) -> str:
        return f'<User {self.email}>'


class Subscription(db.Model):
    """
    Subscription model for tracking user payments and tiers.
    
    Attributes:
        id: Unique subscription identifier
        user_id: Foreign key to user
        stripe_subscription_id: Stripe subscription ID (if applicable)
        apple_transaction_id: Apple transaction ID (if applicable)
        tier: Current subscription tier
        status: Subscription status (active, canceled, past_due, etc.)
        current_period_start: Start of current billing period
        current_period_end: End of current billing period
        created_at: Subscription creation timestamp
        updated_at: Last update timestamp
    """
    
    __tablename__ = 'subscriptions'
    
    # Primary key
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False, unique=True)
    
    # Payment provider identifiers
    stripe_subscription_id = db.Column(db.String(255), nullable=True, unique=True)
    apple_transaction_id = db.Column(db.String(255), nullable=True)
    
    # Subscription details
    tier = db.Column(db.String(20), nullable=False)  # free, pro, enterprise
    status = db.Column(db.String(20), default='active', nullable=False)  # active, canceled, past_due, etc.
    
    # Billing period
    current_period_start = db.Column(db.DateTime(timezone=True), nullable=True)
    current_period_end = db.Column(db.DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = db.relationship('User', back_populates='subscription')
    
    def is_active(self) -> bool:
        """
        Check if the subscription is currently active.
        
        Returns:
            True if subscription is active, False otherwise
        """
        if self.status != 'active':
            return False
        
        if self.current_period_end:
            return datetime.now(timezone.utc) < self.current_period_end
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert subscription to dictionary for JSON serialization.
        
        Returns:
            Dictionary representation of the subscription
        """
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'tier': self.tier,
            'status': self.status,
            'is_active': self.is_active(),
            'current_period_start': self.current_period_start.isoformat() if self.current_period_start else None,
            'current_period_end': self.current_period_end.isoformat() if self.current_period_end else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self) -> str:
        return f'<Subscription {self.tier} for user {self.user_id}>'


class PredictionRequest(db.Model):
    """
    Model for logging prediction requests and responses.
    Used for analytics and debugging without storing proprietary data.
    
    Attributes:
        id: Unique request identifier
        user_id: Foreign key to user
        request_data_hash: Hash of request data (for deduplication)
        success: Whether the request was successful
        error_code: Error code if request failed
        response_time_ms: Response time in milliseconds
        created_at: Request timestamp
    """
    
    __tablename__ = 'prediction_requests'
    
    # Primary key
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    
    # Request metadata (no sensitive data)
    request_data_hash = db.Column(db.String(64), nullable=False)  # SHA-256 hash
    success = db.Column(db.Boolean, nullable=False)
    error_code = db.Column(db.String(50), nullable=True)
    response_time_ms = db.Column(db.Integer, nullable=True)
    
    # Timestamp
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = db.relationship('User', back_populates='prediction_requests')
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert prediction request to dictionary for JSON serialization.
        
        Returns:
            Dictionary representation of the prediction request
        """
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'success': self.success,
            'error_code': self.error_code,
            'response_time_ms': self.response_time_ms,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self) -> str:
        return f'<PredictionRequest {self.id} - {"success" if self.success else "failed"}>'


class Whitelist(db.Model):
    """
    Whitelist model for email-based access control.
    
    Attributes:
        id: Unique whitelist entry identifier
        email: Email address to whitelist
        invite_code: Optional invite code for registration
        invited_by: User who created this whitelist entry
        notes: Optional notes about the whitelist entry
        is_used: Whether this whitelist entry has been used
        used_at: When this entry was used
        used_by: User who used this whitelist entry
        created_at: Entry creation timestamp
        expires_at: Optional expiration timestamp
    """
    
    __tablename__ = 'whitelist'
    
    # Primary key
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Email to whitelist
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    
    # Optional invite code
    invite_code = db.Column(db.String(50), unique=True, nullable=True, index=True)
    
    # Who invited this email
    invited_by = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=True)
    
    # Optional notes
    notes = db.Column(db.Text, nullable=True)
    
    # Status tracking
    is_used = db.Column(db.Boolean, default=False, nullable=False, index=True)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)
    used_by = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    
    # Relationships
    inviter = db.relationship('User', foreign_keys=[invited_by], backref='sent_invites')
    user_who_used = db.relationship('User', foreign_keys=[used_by], backref='used_invites')
    
    def __init__(self, email: str, invite_code: Optional[str] = None, 
                 invited_by: Optional[uuid.UUID] = None, notes: Optional[str] = None,
                 expires_at: Optional[datetime] = None):
        """
        Initialize a new whitelist entry.
        
        Args:
            email: Email address to whitelist
            invite_code: Optional invite code
            invited_by: User who created this entry
            notes: Optional notes
            expires_at: Optional expiration date
        """
        self.email = email.lower().strip()
        self.invite_code = invite_code
        self.invited_by = invited_by
        self.notes = notes.strip() if notes else None
        self.expires_at = expires_at
    
    def is_valid(self) -> bool:
        """
        Check if this whitelist entry is valid (not used and not expired).
        
        Returns:
            True if valid, False otherwise
        """
        # Check if already used
        if self.is_used:
            return False
        
        # Check if expired
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        
        return True
    
    def mark_as_used(self, user_id: uuid.UUID) -> None:
        """
        Mark this whitelist entry as used.
        
        Args:
            user_id: ID of the user who used this entry
        """
        self.is_used = True
        self.used_at = datetime.now(timezone.utc)
        self.used_by = user_id
        db.session.commit()
    
    @classmethod
    def is_email_whitelisted(cls, email: str) -> bool:
        """
        Check if an email address is whitelisted and valid.
        
        Args:
            email: Email address to check
            
        Returns:
            True if email is whitelisted and valid, False otherwise
        """
        entry = cls.query.filter_by(email=email.lower().strip()).first()
        return entry is not None and entry.is_valid()
    
    @classmethod
    def use_whitelist_entry(cls, email: str, user_id: uuid.UUID) -> bool:
        """
        Use a whitelist entry for an email address.
        
        Args:
            email: Email address
            user_id: ID of the user using the entry
            
        Returns:
            True if entry was found and used, False otherwise
        """
        entry = cls.query.filter_by(email=email.lower().strip()).first()
        if entry and entry.is_valid():
            entry.mark_as_used(user_id)
            return True
        return False
    
    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """
        Convert whitelist entry to dictionary for JSON serialization.
        
        Args:
            include_sensitive: Whether to include sensitive fields like invite codes
            
        Returns:
            Dictionary representation of the whitelist entry
        """
        data = {
            'id': str(self.id),
            'email': self.email,
            'is_used': self.is_used,
            'used_at': self.used_at.isoformat() if self.used_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_valid': self.is_valid(),
        }
        
        if include_sensitive:
            data.update({
                'invite_code': self.invite_code,
                'notes': self.notes,
                'invited_by': str(self.invited_by) if self.invited_by else None,
                'used_by': str(self.used_by) if self.used_by else None,
            })
        
        return data
    
    def __repr__(self) -> str:
        status = "used" if self.is_used else "valid" if self.is_valid() else "expired"
        return f'<Whitelist {self.email} ({status})>'