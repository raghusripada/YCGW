from pydantic import BaseModel, Field
from typing import List, Any, Optional, Dict # Added Dict
import uuid

from arcade_platform.auth.models import User as DBUser # SQLAlchemy User model
from arcade_platform.auth.external_auth_manager import get_active_external_token # Function to get tokens
from sqlalchemy.ext.asyncio import AsyncSession # For db session type hint
# from arcade_platform.core.database import get_db_session # To fetch session if get_user_context becomes a dependency

# New Pydantic model for representing an external token within UserContext
class ExternalTokenInfo(BaseModel):
    provider_name: str
    access_token: str # Decrypted access token
    scopes: Optional[List[str]] = None
    expires_at: Optional[int] = None # Timestamp

    class Config:
        # Pydantic V2: from_attributes = True
        # Pydantic V1: orm_mode = True
        # This allows Pydantic to create the model from arbitrary objects (like dicts from other functions)
        # if they have matching attribute names.
        from_attributes = True


class UserContext(BaseModel):
    """
    Represents the context of the user for whom a tool is being executed.
    """
    user_id: str
    is_authenticated: bool = False
    permissions: List[str] = Field(default_factory=list)

    external_tokens: Dict[str, ExternalTokenInfo] = Field(default_factory=dict)

    # db_user: Optional[DBUser] = Field(default=None, exclude=True) # For Pydantic V2, use model_config

    class Config:
        # Pydantic V2 config
        model_config = {"from_attributes": True, "arbitrary_types_allowed": True, "exclude": {"db_user"}}
        # For Pydantic V1, orm_mode = True, arbitrary_types_allowed = True. Exclude via __fields__ if needed.


async def get_user_context(
    platform_user: DBUser,
    db_session: AsyncSession,
    # required_providers: Optional[List[str]] = None # Optional: to specify which tokens are needed
) -> UserContext:
    """
    Retrieves user context, including active external tokens for specified providers.
    `platform_user` is the authenticated SQLAlchemy User object from your main platform auth.
    """
    print(f"[get_user_context] Building context for user ID: {platform_user.id}")

    active_external_tokens: Dict[str, ExternalTokenInfo] = {}

    # Example: Fetch token for "google". In a real scenario, `required_providers` might be passed.
    providers_to_check = ["google"] # Could be dynamic based on tool requirements

    for provider_name in providers_to_check:
        token_info_dict = await get_active_external_token(
            db_session=db_session,
            user_id=platform_user.id,
            provider_name=provider_name
        )
        if token_info_dict:
            # Convert dict from get_active_external_token to ExternalTokenInfo Pydantic model
            active_external_tokens[provider_name] = ExternalTokenInfo(**token_info_dict)
            print(f"Fetched active token for provider: {provider_name}")
        else:
            print(f"No active token found for provider: {provider_name}")

    return UserContext(
        user_id=str(platform_user.id),
        is_authenticated=True,
        permissions=["tool:dummy_tool_allowed"], # Replace with actual permissions
        external_tokens=active_external_tokens
        # db_user=platform_user # If you need to pass the raw DBUser object
    )

# The old stub get_user_context(user_identifier: Any) is now replaced by the more specific one above.
