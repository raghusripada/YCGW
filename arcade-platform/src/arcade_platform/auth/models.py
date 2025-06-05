import uuid
from sqlalchemy import Column, String, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID # For PostgreSQL specific UUID type
from sqlalchemy.orm import relationship
from arcade_platform.core.database import Base # Import Base from your database setup
from datetime import datetime
from pydantic import ConfigDict # Import ConfigDict

class User(Base):
    __tablename__ = "users"

    # Pydantic v2 config for ORM mode (from_attributes)
    # This allows FastAPI to convert it for responses directly
    model_config = ConfigDict(from_attributes=True)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False) # Store hashed passwords, not plain text

    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), default=datetime.utcnow)

    # Example of a relationship, if you had other related models:
    # items = relationship("Item", back_populates="owner")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}')>"
