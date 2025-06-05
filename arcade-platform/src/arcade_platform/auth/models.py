import uuid
from sqlalchemy import Column, String, Boolean, DateTime, func, Text, ForeignKey, Integer # Add Text, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, ARRAY # Ensure ARRAY is imported
from sqlalchemy.orm import relationship
from arcade_platform.core.database import Base # Import Base from your database setup
from datetime import datetime
from pydantic import ConfigDict # For User model config
from typing import List # For type hinting in helper methods

class User(Base):
    __tablename__ = "users"
    model_config = ConfigDict(from_attributes=True) # Ensure this is present for Pydantic v2 ORM mode

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), default=datetime.utcnow)

    # Relationship to OAuth2Token (one user can have many tokens)
    tokens = relationship("OAuth2Token", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}')>"


# New OAuth2 Models based on Authlib examples for SQLAlchemy
class OAuth2Client(Base):
    __tablename__ = "oauth2_clients"

    id = Column(Integer, primary_key=True) # Auto-incrementing ID for internal use
    client_id = Column(String(48), unique=True, index=True, nullable=False)
    client_secret = Column(String(120), nullable=False) # Store hashed secrets in production

    client_name = Column(String(100), nullable=True)
    redirect_uris = Column(Text, nullable=False)
    default_redirect_uri = Column(Text, nullable=True)
    scope = Column(Text, nullable=False, default="")

    response_types = Column(Text, nullable=True, default="code")
    grant_types = Column(Text, nullable=True, default="authorization_code refresh_token")
    token_endpoint_auth_method = Column(String(120), default="client_secret_basic")

    def get_client_id(self):
        return self.client_id

    def get_default_redirect_uri(self):
        return self.default_redirect_uri

    def get_allowed_scopes(self, scopes_text: str) -> List[str]:
        if not scopes_text:
            return []
        return scopes_text.split(" ")

    def check_redirect_uri(self, redirect_uri: str) -> bool:
        if not self.redirect_uris: return False
        return redirect_uri in self.redirect_uris.split(" ")

    def check_grant_type(self, grant_type: str) -> bool:
        if not self.grant_types: return False
        return grant_type in self.grant_types.split(" ")

    def check_response_type(self, response_type: str) -> bool:
        if not self.response_types: return False
        return response_type in self.response_types.split(" ")

    def check_client_secret(self, client_secret: str) -> bool:
        return client_secret == self.client_secret

    def check_endpoint_auth_method(self, method: str, endpoint: str) -> bool:
        if endpoint == 'token':
            return self.token_endpoint_auth_method == method
        return True


class OAuth2AuthorizationCode(Base):
    __tablename__ = "oauth2_authorization_codes"

    id = Column(Integer, primary_key=True)
    code = Column(String(120), unique=True, nullable=False)
    client_id = Column(String(48), nullable=False)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    user = relationship("User")

    redirect_uri = Column(Text, nullable=True)
    response_type = Column(Text, nullable=True)
    scope = Column(Text, nullable=True)
    auth_time = Column(Integer, nullable=False, default=lambda: int(datetime.utcnow().timestamp()))

    code_challenge = Column(String(128), nullable=True)
    code_challenge_method = Column(String(48), nullable=True)

    def is_expired(self) -> bool:
        return self.auth_time + (10 * 60) < int(datetime.utcnow().timestamp())

    def get_redirect_uri(self):
        return self.redirect_uri

    def get_scope(self):
        return self.scope or ""

    def get_auth_time(self):
        return self.auth_time


class OAuth2Token(Base):
    __tablename__ = "oauth2_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    user = relationship("User", back_populates="tokens")

    client_id = Column(String(48), nullable=False)
    token_type = Column(String(40), nullable=True)
    access_token = Column(String(255), unique=True, nullable=False)
    refresh_token = Column(String(255), unique=True, index=True, nullable=True)
    scope = Column(Text, nullable=True, default="")

    issued_at = Column(Integer, nullable=False, default=lambda: int(datetime.utcnow().timestamp()))
    access_token_revoked_at = Column(Integer, nullable=False, default=0)
    refresh_token_revoked_at = Column(Integer, nullable=False, default=0)
    expires_in = Column(Integer, nullable=False, default=0)

    def get_scope(self):
        return self.scope or ""

    def get_issued_at(self):
        return self.issued_at

    def get_expires_in(self):
        return self.expires_in

    def get_expires_at(self):
        return self.issued_at + self.expires_in

    def is_access_token_expired(self) -> bool:
        if not self.access_token_revoked_at:
            return self.issued_at + self.expires_in < int(datetime.utcnow().timestamp())
        return True

    def is_refresh_token_expired(self) -> bool:
        return self.refresh_token_revoked_at != 0
