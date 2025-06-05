import uuid
from sqlalchemy import Column, String, Boolean, DateTime, func, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY # For PostgreSQL specific types
# from sqlalchemy.orm import relationship # If relationships are needed later
from arcade_platform.core.database import Base # Import Base from your database setup
from datetime import datetime

class ToolDefinition(Base):
    __tablename__ = "tool_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # A unique machine-readable name, e.g., "github_create_issue_v1" could also be an ID
    # For simplicity, using UUID as primary key and 'name' for human-readable.
    # If 'name' + 'version' should be unique, add a UniqueConstraint.
    name = Column(String, nullable=False, index=True) # Human-readable name
    description = Column(String, nullable=True)

    # Storing complex, nested parameter schema as JSONB
    # For PostgreSQL, JSONB is generally preferred over JSON for indexing and performance.
    parameters_schema = Column(JSON, nullable=True) # JSONB can be specified with dialect options if needed

    auth_required = Column(Boolean, default=False)
    # Storing list of auth scopes as an array of strings
    auth_scopes = Column(ARRAY(String), nullable=True, default=list)

    execution_timeout_seconds = Column(Integer, default=30)
    version = Column(String, nullable=False, default="1.0.0")

    # Storing invocation details (e.g., module path, function name, API endpoint) as JSONB
    invocation_details = Column(JSON, nullable=True)

    is_active = Column(Boolean, default=True) # To enable/disable tools

    created_at = Column(DateTime(timezone=True), server_default=func.now(), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), default=datetime.utcnow)

    # __table_args__ = (
    #     UniqueConstraint('name', 'version', name='uq_tool_name_version'),
    # ) # Example if name+version should be unique

    def __repr__(self):
        return f"<ToolDefinition(id={self.id}, name='{self.name}', version='{self.version}')>"
