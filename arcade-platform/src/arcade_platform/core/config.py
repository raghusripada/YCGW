from pydantic import BaseModel, Field, HttpUrl, SecretStr
from typing import Dict, List, Optional, Union
from enum import Enum

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class DatabaseSettings(BaseModel):
    url: str = "postgresql+asyncpg://user:pass@localhost:5432/arcade"
    pool_size: int = Field(default=10, gt=0)
    echo: bool = False # For SQLAlchemy logging

class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379/0"
    # Example: token_ttl for storing auth tokens
    token_ttl_seconds: int = Field(default=3600, gt=0)

class ServiceSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: LogLevel = LogLevel.INFO

class OAuthProviderClientSettings(BaseModel):
    client_id: Optional[str] = None
    client_secret: Optional[SecretStr] = None
    scopes: List[str] = []
    # authorization_url: Optional[HttpUrl] = None # Could be added if needed directly
    # token_url: Optional[HttpUrl] = None # Could be added if needed directly

class AuthSettings(BaseModel):
    # Settings for the platform's own OAuth 2.0 server
    jwt_secret_key: SecretStr = Field(default="your-strong-secret-key-for-jwt-please-change", min_length=32)
    jwt_algorithm: str = "HS256"
    # access_token_expire_minutes: int = 30 # Already present below, ensuring one definition
    # refresh_token_expire_days: int = 90 # Example for refresh token

    # OAuth Server specific settings
    oauth_server_issuer_uri: HttpUrl = "http://localhost:8000" # Example, should match deployment
    oauth_server_access_token_expire_seconds: int = Field(default=3600, gt=0) # 1 hour
    oauth_server_refresh_token_expire_seconds: int = Field(default=3600 * 24 * 90, gt=0) # 90 days

    # For JWT access tokens, if used directly by Authlib (some grants might issue opaque tokens by default)
    # oauth_server_jwt_audience: Optional[str] = "arcade-platform-api"
    # oauth_server_jwt_jwks_uri: Optional[HttpUrl] = None # If using JWKS endpoint for public keys

    # Configuration for external OAuth providers the platform will connect TO
    # (e.g., for tools to connect to GitHub, Google) - This part is already present
    providers: Dict[str, OAuthProviderClientSettings] = {
        "github": OAuthProviderClientSettings(scopes=["repo", "user:email"]),
        "google": OAuthProviderClientSettings(scopes=["https://www.googleapis.com/auth/gmail.send"])
    }

    # Added access_token_expire_minutes from previous feedback if it was missed
    access_token_expire_minutes: int = Field(default=30, gt=0)

class LiteLLMSettings(BaseModel):
    # This could be a path to a YAML file, or the settings could be embedded here
    config_path: str = "litellm_config.yaml"
    # Example: default_model for routing if not specified in request
    default_model: Optional[str] = None

class CelerySettings(BaseModel):
    broker_url: str = "redis://localhost:6379/1"
    result_backend: str = "redis://localhost:6379/2"
    # task_concurrency: Optional[int] = None # To be set by worker config

class AppSettings(BaseModel):
    app_name: str = "ArcadePlatform"
    debug: bool = False

    database: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()

    # Main API service settings
    api_service: ServiceSettings = ServiceSettings(port=8000)

    auth: AuthSettings = AuthSettings()
    litellm: LiteLLMSettings = LiteLLMSettings()
    celery: CelerySettings = CelerySettings()

    # Placeholder for where to load/save the main platform.yaml or similar
    # platform_config_path: str = "platform.yaml"

    class Config:
        env_file = ".env" # Example for loading from .env file
        env_file_encoding = "utf-8"
        # For nested Pydantic models when using environment variables:
        # env_nested_delimiter = '__'

# Global instance for easy access, can be loaded/initialized at startup
# settings = AppSettings()
# print(settings.database.url)
# print(settings.auth.providers["github"].client_id)
