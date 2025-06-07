import uuid
from typing import Optional, Dict, Any, Sequence
from pydantic import EmailStr, BaseModel as PydanticBaseModel

from sqlalchemy import select, update as sql_update, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from enableai_hub.auth.models import User # SQLAlchemy model
from passlib.context import CryptContext # Import CryptContext

# Initialize password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pydantic model for creating a user (input validation)
class UserCreate(PydanticBaseModel):
    email: EmailStr
    password: str # Plain password from user input, will be hashed
    full_name: Optional[str] = None
    is_active: bool = True # Default value
    is_superuser: bool = False # Default value

# Pydantic model for updating a user (input validation)
class UserUpdate(PydanticBaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    # password: Optional[str] = None # Password updates handled separately usually

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hashes a plain password."""
    return pwd_context.hash(password)

async def get_user(db_session: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    """Retrieve a user by their ID from the database."""
    result = await db_session.execute(select(User).filter(User.id == user_id))
    return result.scalars().first()

async def get_user_by_email(db_session: AsyncSession, email: EmailStr) -> Optional[User]:
    """Retrieve a user by their email address from the database."""
    result = await db_session.execute(select(User).filter(User.email == email))
    return result.scalars().first()

async def create_user(db_session: AsyncSession, user_in: UserCreate) -> User:
    """
    Create a new user in the database with a hashed password.
    """
    existing_user = await get_user_by_email(db_session, user_in.email)
    if existing_user:
        raise ValueError(f"User with email {user_in.email} already exists.")

    hashed_password = get_password_hash(user_in.password) # Hash the password

    db_user = User(
        email=user_in.email,
        hashed_password=hashed_password, # Store the hashed password
        full_name=user_in.full_name,
        is_active=user_in.is_active,
        is_superuser=user_in.is_superuser
    )
    db_session.add(db_user)
    await db_session.flush()
    await db_session.refresh(db_user)
    return db_user

async def update_user(db_session: AsyncSession, user_id: uuid.UUID, user_in: UserUpdate) -> Optional[User]:
    """Update an existing user in the database."""
    db_user = await get_user(db_session, user_id)
    if not db_user:
        return None

    update_data = user_in.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(db_user, field, value)

    db_session.add(db_user)
    await db_session.refresh(db_user)
    return db_user

async def delete_user(db_session: AsyncSession, user_id: uuid.UUID) -> bool:
    """
    Delete a user from the database.
    Returns True if user was deleted, False otherwise.
    """
    db_user = await get_user(db_session, user_id)
    if not db_user:
        return False

    await db_session.delete(db_user)
    return True

async def get_users(
    db_session: AsyncSession, skip: int = 0, limit: int = 100
) -> Sequence[User]:
    """
    Retrieve a list of users with pagination.
    """
    result = await db_session.execute(
        select(User).offset(skip).limit(limit)
    )
    return result.scalars().all()

async def authenticate_platform_user(db_session: AsyncSession, email: str, password: str) -> Optional[User]:
    """Authenticates a platform user by email and password."""
    # EmailStr validation can be done here if email is not pre-validated
    # For example: validated_email = EmailStr(email)
    user = await get_user_by_email(db_session, EmailStr(email))
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
