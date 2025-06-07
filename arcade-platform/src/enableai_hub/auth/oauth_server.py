from authlib.integrations.starlette_oauth2 import AuthorizationServer
from authlib.oauth2.rfc6749.grants import AuthorizationCodeGrant as _AuthorizationCodeGrant
from authlib.oauth2.rfc6749.grants import RefreshTokenGrant as _RefreshTokenGrant
from authlib.oauth2.rfc7636 import CodeChallenge as _CodeChallenge
from authlib.oauth2.rfc6749 import OAuth2Request

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional, Dict, List, Any
from datetime import datetime
from fastapi import Request as FastAPIRequest

from enableai_hub.core.database import get_db_session
from enableai_hub.auth.models import User, OAuth2Client, OAuth2Token, OAuth2AuthorizationCode
from enableai_hub.core.config import AppSettings
from enableai_hub.auth.user_manager import verify_password # Import verify_password

app_settings = AppSettings()

def _get_db_session_from_request(request: Any) -> AsyncSession:
    if hasattr(request, 'framework_request') and hasattr(request.framework_request, 'state') and hasattr(request.framework_request.state, 'db_session'):
        return request.framework_request.state.db_session
    elif hasattr(request, 'state') and hasattr(request.state, 'db_session'):
        return request.state.db_session
    raise ValueError("Database session not found in request state.")

async def query_client_from_request(request: Any, client_id: str) -> Optional[OAuth2Client]:
    db_session = _get_db_session_from_request(request)
    stmt = select(OAuth2Client).where(OAuth2Client.client_id == client_id)
    result = await db_session.execute(stmt)
    return result.scalars().first()

async def save_token_from_request(request: Any, token_data: Dict) -> OAuth2Token:
    db_session = _get_db_session_from_request(request)
    user_obj = getattr(request, 'user', None)
    if not user_obj or not isinstance(user_obj, User):
        raise ValueError("User context not found in request for save_token")

    client_obj = getattr(request, 'client', None)
    if not client_obj or not isinstance(client_obj, OAuth2Client):
        raise ValueError("Client context not found in request for save_token")

    token = OAuth2Token(
        user_id=user_obj.id,
        client_id=client_obj.client_id,
        token_type=token_data.get("token_type", "Bearer"),
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        scope=token_data.get("scope", ""),
        issued_at=token_data["issued_at"],
        expires_in=token_data["expires_in"],
    )
    db_session.add(token)
    return token

async def query_authorization_code_from_request(request: Any, code: str, client: OAuth2Client) -> Optional[OAuth2AuthorizationCode]:
    db_session = _get_db_session_from_request(request)
    stmt = select(OAuth2AuthorizationCode).where(
        OAuth2AuthorizationCode.code == code,
        OAuth2AuthorizationCode.client_id == client.client_id
    )
    result = await db_session.execute(stmt)
    auth_code = result.scalars().first()
    if auth_code and not auth_code.is_expired():
        return auth_code
    return None

async def delete_authorization_code_from_request(request: Any, authorization_code: OAuth2AuthorizationCode) -> None:
    db_session = _get_db_session_from_request(request)
    await db_session.delete(authorization_code)

async def save_authorization_code_from_request(request: Any, code: str, authlib_req_data: OAuth2Request) -> OAuth2AuthorizationCode:
    db_session = _get_db_session_from_request(request)
    auth_code = OAuth2AuthorizationCode(
        code=code,
        client_id=authlib_req_data.client.get_client_id(),
        user_id=authlib_req_data.user.id,
        redirect_uri=authlib_req_data.redirect_uri,
        scope=authlib_req_data.scope,
        auth_time=int(datetime.utcnow().timestamp()),
        code_challenge=authlib_req_data.code_challenge,
        code_challenge_method=authlib_req_data.code_challenge_method
    )
    db_session.add(auth_code)
    return auth_code

async def authenticate_user_for_grant_from_request(authlib_req: Any, username: Optional[str] = None, password: Optional[str] = None) -> Optional[User]:
    db_session_source = getattr(authlib_req, 'framework_request', authlib_req)
    db_session = _get_db_session_from_request(db_session_source)

    form_data = getattr(authlib_req, 'form', None) # Authlib's OAuth2Request may have .form
    if form_data:
        username = username or form_data.get("username")
        password = password or form_data.get("password")
    # If authlib_req is a direct FastAPI/Starlette Request (e.g. from /authorize POST)
    elif isinstance(db_session_source, FastAPIRequest) and not (username and password):
        try:
            # This path is taken if grant.authenticate_user is called with framework_request
            # and form data hasn't been parsed by Authlib into authlib_req.form yet.
            # This might be the case if called directly from our /authorize POST endpoint.
            async_form_data = await db_session_source.form()
            username = username or async_form_data.get("username")
            password = password or async_form_data.get("password")
        except Exception:
            pass

    if not username or not password:
        return None

    stmt = select(User).where(User.email == username)
    result = await db_session.execute(stmt)
    user = result.scalars().first()

    if user and user.is_active and verify_password(password, user.hashed_password): # Use verify_password
        return user
    return None

oauth2_server = AuthorizationServer(
    query_client=query_client_from_request,
    save_token=save_token_from_request,
)

def register_oauth_grants(server_instance: AuthorizationServer):
    # The lambda for authenticate_user needs to correctly adapt.
    # Authlib's AuthorizationCodeGrant.authenticate_user is called with (self, form)
    # where `self` is the grant instance and `form` is the form data.
    # The grant instance has `grant.request` which is Authlib's OAuth2Request.

    server_instance.register_grant(
        _AuthorizationCodeGrant,
        extensions=[
            _CodeChallenge(required=True),
        ],
        update_authorization_code_data={
            'query_authorization_code': lambda request, code, client: query_authorization_code_from_request(request.framework_request, code, client),
            'save_authorization_code': lambda request, code, authlib_req_data: save_authorization_code_from_request(request.framework_request, code, authlib_req_data),
            'delete_authorization_code': lambda request, authorization_code: delete_authorization_code_from_request(request.framework_request, authorization_code),
            'authenticate_user': lambda grant, form_data: authenticate_user_for_grant_from_request(grant.request, username=form_data.get("username"), password=form_data.get("password"))
        }
    )
