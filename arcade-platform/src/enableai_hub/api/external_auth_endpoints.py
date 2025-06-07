from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient as HTTPXClient
import secrets
from urllib.parse import urlencode
from typing import Optional, Dict, Any

from enableai_hub.core.database import get_db_session
from enableai_hub.core.config import AppSettings
from enableai_hub.auth.models import User
from enableai_hub.auth.external_auth_manager import store_external_token
from enableai_hub.auth.dependencies import get_current_active_platform_user # New import

# Removed:
# async def get_current_platform_user_stub(...): ...

router = APIRouter(
    prefix="/api/v1/external-auth",
    tags=["External OAuth"],
)

csrf_state_store: Dict[str, str] = {}

@router.get("/{provider_name}/login")
async def external_auth_login(
    provider_name: str,
    request: Request,
    current_user: User = Depends(get_current_active_platform_user), # USE THE NEW DEPENDENCY
    settings: AppSettings = Depends(lambda: AppSettings())
):
    provider_config = settings.auth.providers.get(provider_name.lower())
    if not provider_config or not provider_config.auth_url or not provider_config.client_id or not provider_config.platform_redirect_uri:
        raise HTTPException(status_code=404, detail=f"Configuration for provider '{provider_name}' not found or incomplete.")

    state = secrets.token_urlsafe(32)
    csrf_state_store[f"{provider_name}_{current_user.id}"] = state

    params = {
        "client_id": provider_config.client_id,
        "response_type": "code",
        "scope": " ".join(provider_config.scopes),
        "redirect_uri": str(provider_config.platform_redirect_uri),
        "state": state,
    }
    if provider_config.extra_params:
        params.update(provider_config.extra_params)

    authorization_url = f"{provider_config.auth_url}?{urlencode(params)}"
    return RedirectResponse(url=authorization_url)


@router.get("/{provider_name}/callback")
async def external_auth_callback(
    provider_name: str,
    request: Request,
    code: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_platform_user), # USE THE NEW DEPENDENCY
    settings: AppSettings = Depends(lambda: AppSettings())
):
    if error:
        return HTMLResponse(content=f"<h1>OAuth Error</h1><p>Provider: {provider_name}</p><p>Error: {error}</p><p>Description: {error_description or 'N/A'}</p>", status_code=400)

    stored_state = csrf_state_store.pop(f"{provider_name}_{current_user.id}", None)
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

    async with HTTPXClient() as client:
        try:
            response = await client.post(str(provider_config.token_url), data=token_payload)
            response.raise_for_status()
            token_data = response.json()
        except Exception as e:
            print(f"Error exchanging code for token with {provider_name}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to exchange authorization code with {provider_name}.")

    await store_external_token(
        db_session=db,
        user_id=current_user.id,
        provider_name=provider_name.lower(),
        access_token=token_data["access_token"],
        expires_in=token_data.get("expires_in"),
        scopes=token_data.get("scope", "").split(" ") if token_data.get("scope") else provider_config.scopes,
        refresh_token=token_data.get("refresh_token")
    )

    return HTMLResponse(content=f"<h1>Successfully authorized with {provider_name}!</h1><p>Tokens stored for user {current_user.email}.</p>"
                                "<p>You can close this window.</p>")
