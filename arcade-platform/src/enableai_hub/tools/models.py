import uuid
from sqlalchemy import Column, String, Boolean, DateTime, func, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from enableai_hub.core.database import Base
from datetime import datetime

class ToolDefinition(Base):
    __tablename__ = "tool_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, index=True) # Human-readable name
    description = Column(String, nullable=True)

    parameters_schema = Column(JSON, nullable=True) # e.g., OpenAPI Specification for parameters

    # OAuth related fields - these relate to *our platform's* OAuth server if tools are protected by it.
    # For external service auth needed by the tool itself, see auth_provider_name.
    auth_required = Column(Boolean, default=False) # Does calling this tool via our platform require platform auth?
    auth_scopes = Column(ARRAY(String), nullable=True, default=list) # Platform OAuth scopes required

    execution_timeout_seconds = Column(Integer, default=30)
    version = Column(String, nullable=False, default="1.0.0")

    # Invocation details:
    # For an MCP tool, this might store:
    # {
    #   "type": "mcp", // Invocation type
    #   "mcp_target_url": "http://some-mcp-tool-service.example.com/invoke",
    #   "mcp_method_name": "specific_mcp_function_to_call_on_tool",
    #   // other mcp specific config, like version or protocol details
    # }
    # For other types like a Python function:
    # {
    #   "type": "python",
    #   "module": "some.python.module",
    #   "function": "function_name"
    # }
    invocation_details = Column(JSON, nullable=True)

    # NEW FIELD: Specifies the name of the external auth provider (e.g., "google", "github")
    # whose token is required by the tool to operate.
    # If null or empty, the tool does not directly require an external OAuth token via the platform.
    auth_provider_name = Column(String(100), nullable=True, index=True)

    is_active = Column(Boolean, default=True) # To enable/disable tools

    created_at = Column(DateTime(timezone=True), server_default=func.now(), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), default=datetime.utcnow)

    # from sqlalchemy import UniqueConstraint
    # __table_args__ = (
    #     UniqueConstraint('name', 'version', name='uq_tool_name_version'),
    # ) # Example if name+version should be unique

    def __repr__(self):
        return f"<ToolDefinition(id={self.id}, name='{self.name}', version='{self.version}')>"
