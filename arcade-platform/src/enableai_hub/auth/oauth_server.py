from authlib.integrations.starlette_oauth2 import AuthorizationServer
from authlib.oauth2.rfc6749.grants import AuthorizationCodeGrant as _AuthorizationCodeGrant
from authlib.oauth2.rfc6749.grants import RefreshTokenGrant as _RefreshTokenGrant
from authlib.oauth2.rfc7636 import CodeChallenge as _CodeChallenge
from authlib.oauth2.rfc6749 import OAuth2Request # For type hinting if needed

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional, Dict, List, Any
from datetime import datetime
from fastapi import Request as FastAPIRequest # To distinguish from Authlib's request

from enableai_hub.core.database import get_db_session
from enableai_hub.auth.models import User, OAuth2Client, OAuth2Token, OAuth2AuthorizationCode
from enableai_hub.core.config import AppSettings

app_settings = AppSettings()

# Helper function to get db_session from Authlib's OAuth2Request or FastAPIRequest
def _get_db_session_from_request(request: Any) -> AsyncSession:
    if hasattr(request, 'framework_request') and hasattr(request.framework_request, 'state') and hasattr(request.framework_request.state, 'db_session'):
        # This is Authlib's OAuth2Request wrapping a Starlette/FastAPI request
        return request.framework_request.state.db_session
    elif hasattr(request, 'state') and hasattr(request.state, 'db_session'):
        # This is a direct Starlette/FastAPI request
        return request.state.db_session
    raise ValueError("Database session not found in request state.")

# Query/Save methods now expect 'request' as a parameter from which to get the db_session
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
    db_session = _get_db_session_from_request(request) # request here is the framework request from lambda
    # authlib_req_data here is Authlib's OAuth2Request object passed by the grant.
    auth_code = OAuth2AuthorizationCode(
        code=code,
        client_id=authlib_req_data.client.get_client_id(), # Use authlib_req_data.client
        user_id=authlib_req_data.user.id, # Use authlib_req_data.user
        redirect_uri=authlib_req_data.redirect_uri,
        scope=authlib_req_data.scope,
        auth_time=int(datetime.utcnow().timestamp()),
        code_challenge=authlib_req_data.code_challenge,
        code_challenge_method=authlib_req_data.code_challenge_method
    )
    db_session.add(auth_code)
    return auth_code

async def authenticate_user_for_grant_from_request(authlib_req: OAuth2Request, username: Optional[str] = None, password: Optional[str] = None) -> Optional[User]:
    db_session = _get_db_session_from_request(authlib_req.framework_request) # Get from framework_request

    # If form data is available on Authlib's request object (it should be for this grant context)
    form_data = getattr(authlib_req, 'form', None)
    if form_data:
        username = username or form_data.get("username")
        password = password or form_data.get("password")

    if not username or not password:
        return None

    stmt = select(User).where(User.email == username)
    result = await db_session.execute(stmt)
    user = result.scalars().first()
    if user and user.is_active and user.hashed_password == f"hashed_{password}_placeholder":
        return user
    return None

# --- Authorization Server Setup ---
oauth2_server = AuthorizationServer(
    query_client=query_client_from_request,
    save_token=save_token_from_request,
)

def register_oauth_grants(server_instance: AuthorizationServer):
    # Lambdas adapt the signatures for grant-specific methods to ensure they receive
    # the correct request object (Authlib's OAuth2Request) from which we can extract
    # the framework_request and then the db_session.

    server_instance.register_grant(
        _AuthorizationCodeGrant,
        extensions=[
            _CodeChallenge(required=True),
        ],
        update_authorization_code_data={
            'query_authorization_code': lambda request, code, client: query_authorization_code_from_request(request.framework_request, code, client),
            'save_authorization_code': lambda request, code, authlib_req_data: save_authorization_code_from_request(request.framework_request, code, authlib_req_data),
            'delete_authorization_code': lambda request, authorization_code: delete_authorization_code_from_request(request.framework_request, authorization_code),
            'authenticate_user': lambda request_obj_from_grant: authenticate_user_for_grant_from_request(request_obj_from_grant)
        }
    )
    # server_instance.register_grant(_RefreshTokenGrant) # Placeholder

    # Optional: Register JWT token generator
    # from authlib.oauth2.rfc6749.tokens import JWTAccessTokenGenerator
    # server_instance.register_token_generator(...)

# Call this function from main.py at startup to configure the global oauth2_server instance.
# Example: register_oauth_grants(oauth2_server)
