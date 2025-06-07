from pydantic import BaseModel, Field
from typing import List, Any, Optional, Dict
import uuid

from enableai_hub.auth.models import User as DBUser
from enableai_hub.auth.external_auth_manager import get_active_external_token
from sqlalchemy.ext.asyncio import AsyncSession

class ExternalTokenInfo(BaseModel):
    provider_name: str
    access_token: str
    scopes: Optional[List[str]] = None
    expires_at: Optional[int] = None

    class Config:
        from_attributes = True


class UserContext(BaseModel):
    user_id: str
    is_authenticated: bool = False
    permissions: List[str] = Field(default_factory=list)
    external_tokens: Dict[str, ExternalTokenInfo] = Field(default_factory=dict)

    class Config:
        model_config = {"from_attributes": True, "arbitrary_types_allowed": True, "exclude": {"db_user"}}


async def get_user_context(
    platform_user: DBUser,
    db_session: AsyncSession,
    required_providers: Optional[List[str]] = None # New parameter
) -> UserContext:
    """
    Retrieves user context, including active external tokens for specified providers.
    `platform_user` is the authenticated SQLAlchemy User object.
    If `required_providers` is None or empty, it might default to a common set or fetch none.
    """
    print(f"[get_user_context] Building context for user ID: {platform_user.id}. Required providers: {required_providers}")

    active_external_tokens: Dict[str, ExternalTokenInfo] = {}

    providers_to_check = required_providers
    if not providers_to_check: # Handles None or empty list
        # Default behavior if no specific providers are requested:
        providers_to_check = ["google"] # Example default
        print(f"[get_user_context] No specific providers requested, defaulting to: {providers_to_check}")

    if providers_to_check:
        for provider_name in providers_to_check:
            provider_name_lower = provider_name.lower() # Ensure lowercase for consistency
            token_info_dict = await get_active_external_token(
                db_session=db_session,
                user_id=platform_user.id,
                provider_name=provider_name_lower
            )
            if token_info_dict:
                active_external_tokens[provider_name_lower] = ExternalTokenInfo(**token_info_dict)
                print(f"[get_user_context] Fetched active token for provider: {provider_name_lower}")
            else:
                print(f"[get_user_context] No active token found for provider: {provider_name_lower}")

    return UserContext(
        user_id=str(platform_user.id),
        is_authenticated=True,
        permissions=["tool:dummy_tool_allowed"], # Placeholder for actual permissions
        external_tokens=active_external_tokens
    )
