from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from enum import Enum

class TransportType(str, Enum):
    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"

class ServerConfig(BaseModel):
    name: str
    transport: TransportType
    url: Optional[str] = None
    command: Optional[List[str]] = None
    auth: Optional[Dict[str, str]] = None

class GatewayConfig(BaseModel):
    servers: Dict[str, ServerConfig]
    redis_url: str = "redis://localhost:6379"
    max_connections: int = Field(default=1000, gt=0)
    session_timeout: int = Field(default=3600, gt=0)
