from pydantic import BaseModel, Field, HttpUrl, SecretStr, field_validator
from typing import Dict, List, Optional, Union, Any # Added Any

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class DatabaseSettings(BaseModel):
    url: str = "postgresql+asyncpg://user:pass@localhost:5432/arcade"
    pool_size: int = Field(default=10, gt=0)
    echo: bool = False

class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379/0"
    token_ttl_seconds: int = Field(default=3600, gt=0)

class ServiceSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: LogLevel = LogLevel.INFO

class OAuthProviderClientSettings(BaseModel): # Updated for external provider config
    client_id: Optional[str] = None
    client_secret: Optional[SecretStr] = None
    scopes: List[str] = Field(default_factory=list)

    auth_url: Optional[HttpUrl] = None
    token_url: Optional[HttpUrl] = None
    userinfo_url: Optional[HttpUrl] = None # Optional: to fetch user info after token

    platform_redirect_uri: Optional[HttpUrl] = None
    extra_params: Dict[str, Any] = Field(default_factory=dict)


class AuthSettings(BaseModel):
    jwt_secret_key: SecretStr = Field(default="your-strong-secret-key-for-jwt-please-change", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, gt=0)
    oauth_server_issuer_uri: HttpUrl = "http://localhost:8000"
    oauth_server_access_token_expire_seconds: int = Field(default=3600, gt=0)
    oauth_server_refresh_token_expire_seconds: int = Field(default=3600 * 24 * 90, gt=0)

    providers: Dict[str, OAuthProviderClientSettings] = Field(default_factory=lambda: {
        "google": OAuthProviderClientSettings(
            client_id="YOUR_GOOGLE_CLIENT_ID_ENV_VAR",
            client_secret="YOUR_GOOGLE_CLIENT_SECRET_ENV_VAR",
            scopes=["openid", "email", "profile", "https://www.googleapis.com/auth/drive.readonly"],
            auth_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
            platform_redirect_uri="http://localhost:8000/api/v1/external-auth/google/callback" # Example
        ),
        # "github": OAuthProviderClientSettings(...) # Example placeholder
    })

class LiteLLMSettings(BaseModel):
    config_path: str = "litellm_config.yaml"
    default_model: Optional[str] = None

class CelerySettings(BaseModel):
    broker_url: str = "redis://localhost:6379/1"
    result_backend: str = "redis://localhost:6379/2"

class AppSettings(BaseModel):
    app_name: str = "ArcadePlatform"
    debug: bool = False

    database: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    api_service: ServiceSettings = ServiceSettings(port=8000)
    auth: AuthSettings = AuthSettings()
    litellm: LiteLLMSettings = LiteLLMSettings()
    celery: CelerySettings = CelerySettings()

    external_token_fernet_key: SecretStr = Field(default="OVERRIDE_THIS_WITH_A_REAL_FERNET_KEY_IN_ENV", min_length=44)

    # @field_validator('external_token_fernet_key')
    # def validate_fernet_key(cls, v: SecretStr):
    #     if len(v.get_secret_value()) * 3 // 4 - v.get_secret_value().count('=') != 32:
    #         raise ValueError("Fernet key must be 32 url-safe base64-encoded bytes.")
    #     return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = '__'

# settings = AppSettings()
