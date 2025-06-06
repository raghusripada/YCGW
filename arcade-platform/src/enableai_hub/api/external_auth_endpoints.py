from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient as HTTPXClient # For making requests to provider's token endpoint
import secrets # For generating 'state' parameter
from urllib.parse import urlencode # For building query strings
from typing import Optional, Dict, Any # Added Any

from enableai_hub.core.database import get_db_session
from enableai_hub.core.config import AppSettings
from enableai_hub.auth.models import User # Assuming User model for current_user
from enableai_hub.auth.external_auth_manager import store_external_token
# We'll need a way to get the current authenticated platform user.
# This is a placeholder dependency. In a real app, this would come from your main auth system
# (e.g., decoding a JWT from Authorization header set by your own OAuth server, or session).
async def get_current_platform_user_stub( # Renamed for clarity vs OAuth user
    request: Request,
    db: AsyncSession = Depends(get_db_session)
) -> User:
    """
    STUB: Returns a mock authenticated platform user.
    Replace with actual authentication logic (e.g., JWT verification).
    For testing, this might fetch a predefined user or expect a specific header.
    """
    # Example: fetch a known user for testing.
    # Ensure this user exists in your DB if you run this.
    # You can create one using user_manager.create_user if needed.
    test_user_email = "test@example.com" # Make sure this user exists for testing
    from enableai_hub.auth.user_manager import get_user_by_email
    user = await get_user_by_email(db, test_user_email)
    if not user:
        # If no test user, this will fail. Consider creating one in a startup script for dev.
        raise HTTPException(status_code=403, detail="Test user not found for external auth stub. Please create 'test@example.com'.")
    # request.session["user_id"] = str(user.id) # Example if using sessions
    return user


router = APIRouter(
    prefix="/api/v1/external-auth", # Common prefix for these routes
    tags=["External OAuth"],
)

# In-memory store for 'state' to prevent CSRF, or use session.
# For simplicity, a global dict. In production, use Redis or a proper session store.
# This is NOT production-ready for state storage.
csrf_state_store: Dict[str, str] = {}


@router.get("/{provider_name}/login")
async def external_auth_login(
    provider_name: str,
    request: Request, # FastAPI request to access session or other details
    current_user: User = Depends(get_current_platform_user_stub), # Depends on your platform's auth
    settings: AppSettings = Depends(lambda: AppSettings()) # Dependency to get settings
):
    """
    Initiates the OAuth 2.0 authorization flow with an external provider.
    Redirects the user to the provider's authorization page.
    """
    provider_config = settings.auth.providers.get(provider_name.lower())
    if not provider_config or not provider_config.auth_url or not provider_config.client_id or not provider_config.platform_redirect_uri:
        raise HTTPException(status_code=404, detail=f"Configuration for provider '{provider_name}' not found or incomplete.")

    # Generate and store 'state' for CSRF protection
    state = secrets.token_urlsafe(32)
    # Store state associated with provider and potentially user, or use session if available
    # request.session[f"{provider_name}_oauth_state"] = state # If using Starlette sessions
    csrf_state_store[f"{provider_name}_{current_user.id}"] = state # Simplified state storage (NOT FOR PROD)

    params = {
        "client_id": provider_config.client_id,
        "response_type": "code",
        "scope": " ".join(provider_config.scopes),
        "redirect_uri": str(provider_config.platform_redirect_uri), # Ensure it's a string
        "state": state,
    }
    # Add any provider-specific extra params
    if provider_config.extra_params:
        params.update(provider_config.extra_params)

    # PKCE could be added here for providers that support/require it.
    # Would involve generating code_verifier, code_challenge, storing verifier, adding challenge to params.

    authorization_url = f"{provider_config.auth_url}?{urlencode(params)}"
    return RedirectResponse(url=authorization_url)


@router.get("/{provider_name}/callback")
async def external_auth_callback(
    provider_name: str,
    request: Request, # For accessing query_params and session (for state)
    code: Optional[str] = Query(None), # Authorization code from provider
    error: Optional[str] = Query(None), # Error from provider (e.g., access_denied)
    error_description: Optional[str] = Query(None),
    state: Optional[str] = Query(None), # State from provider
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_platform_user_stub), # Get current user again, or from session state
    settings: AppSettings = Depends(lambda: AppSettings())
):
    """
    Handles the callback from the external OAuth provider after user authorization.
    Exchanges the authorization code for an access token and stores it.
    """
    if error:
        return HTMLResponse(content=f"<h1>OAuth Error</h1><p>Provider: {provider_name}</p><p>Error: {error}</p><p>Description: {error_description or 'N/A'}</p>", status_code=400)

    # Validate 'state' to prevent CSRF
    # stored_state = request.session.pop(f"{provider_name}_oauth_state", None) # If using Starlette sessions
    stored_state = csrf_state_store.pop(f"{provider_name}_{current_user.id}", None) # Simplified (NOT FOR PROD)
    if not state or not stored_state or state != stored_state:
        raise HTTPException(status_code=400, detail="Invalid 'state' parameter. CSRF attempt suspected or session expired.")

    if not code:
        raise HTTPException(status_code=400, detail="Missing 'code' parameter in callback.")

    provider_config = settings.auth.providers.get(provider_name.lower())
    if not provider_config or not provider_config.token_url or not provider_config.client_id or not provider_config.client_secret or not provider_config.platform_redirect_uri:
        raise HTTPException(status_code=404, detail=f"Configuration for provider '{provider_name}' for token exchange not found or incomplete.")

    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": str(provider_config.platform_redirect_uri),
        "client_id": provider_config.client_id,
        "client_secret": provider_config.client_secret.get_secret_value(),
    }
    # Add PKCE code_verifier if used during /login step.

    async with HTTPXClient() as client:
        try:
            response = await client.post(str(provider_config.token_url), data=token_payload)
            response.raise_for_status() # Raise HTTPStatusError for 4xx/5xx responses
            token_data = response.json()
        except Exception as e:
            # Log error: response.status_code, response.text
            print(f"Error exchanging code for token with {provider_name}: {e}")
            # if hasattr(e, 'response') and e.response is not None: print(f"Response body: {e.response.text}")
            raise HTTPException(status_code=500, detail=f"Failed to exchange authorization code with {provider_name}.")

    # Store the token
    await store_external_token(
        db_session=db,
        user_id=current_user.id, # current_user should be the same user who initiated /login
        provider_name=provider_name.lower(),
        access_token=token_data["access_token"],
        expires_in=token_data.get("expires_in"), # Typically in seconds
        scopes=token_data.get("scope", "").split(" ") if token_data.get("scope") else provider_config.scopes, # Use scopes from token or default
        refresh_token=token_data.get("refresh_token")
    )

    # TODO: Redirect to a user-friendly success page or back to application flow
    return HTMLResponse(content=f"<h1>Successfully authorized with {provider_name}!</h1><p>Tokens stored for user {current_user.email}.</p>"
                                "<p>You can close this window.</p>")
