from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlencode # For redirect query params

from enableai_hub.core.database import get_db_session
from enableai_hub.auth.oauth_server import oauth2_server
from enableai_hub.auth.models import User
from enableai_hub.auth.user_manager import get_user_by_email # Using this for the stub
# Re-using authenticate_user_for_grant from oauth_server.py for form processing
from enableai_hub.auth.oauth_server import authenticate_user_for_grant

from typing import Optional

router = APIRouter(
    tags=["OAuth2"],
    prefix="/oauth"
)

async def get_current_user_for_oauth_stub(
    request: Request,
    db: AsyncSession = Depends(get_db_session)
) -> Optional[User]:
    """
    Stub: attempts to get user from session or a test query param.
    This simulates a user being already logged in.
    """
    # 1. Check session (if Starlette session middleware is added later)
    # user_id_from_session = request.session.get("user_id")
    # if user_id_from_session:
    #     from enableai_hub.auth.user_manager import get_user # Assuming get_user by ID exists
    #     user = await get_user(db, user_id_from_session)
    #     if user: return user

    # 2. For testing: check a query parameter (less secure, for dev only)
    test_user_email_qp = request.query_params.get("test_user_email_qp")
    if test_user_email_qp:
        user = await get_user_by_email(db, test_user_email_qp) # Use imported get_user_by_email
        if user:
            print(f"[OAuth Stub] Granting access via query param for test user: {user.email}")
            return user
    return None


@router.api_route("/authorize", methods=["GET", "POST"], response_class=HTMLResponse)
async def authorize(
    request: Request,
    db: AsyncSession = Depends(get_db_session)
):
    user = await get_current_user_for_oauth_stub(request, db)

    if request.method == "GET":
        if not user:
            # Display login/consent form
            form_action_url = f"/oauth/authorize?{str(request.query_params)}"
            return HTMLResponse(content=f'''
                <html><head><title>OAuth Authorization</title></head><body>
                    <h1>Login to Authorize</h1>
                    <p>Client is requesting access. Please login.</p>
                    <form method="post" action="{form_action_url}">
                        Email: <input type="email" name="username" required value="test@example.com"><br>
                        Password: <input type="password" name="password" required value="password"><br>
                        <p><em>(Use test@example.com / password with placeholder user data)</em></p>
                        <input type="checkbox" name="confirm_consent" value="yes" checked> Confirm consent (stubbed)<br>
                        <button type="submit">Login & Authorize</button>
                    </form>
                </body></html>
            ''')

        try:
            # Authlib methods need access to request.state.db_session or similar context
            # if they are to use the DI-provided session.
            # For Starlette integration, Authlib wraps the request.
            # Ensure the `oauth2_server` methods are called with a request that Authlib can process.
            # The request object passed here is the FastAPI request.
            # Authlib's Starlette integration handles this.
            return await oauth2_server.create_authorization_response(request, grant_user=user)
        except Exception as e:
            # import traceback; traceback.print_exc() # For debugging
            raise HTTPException(status_code=400, detail=f"OAuth2 Authorization Error: {str(e)}")

    elif request.method == "POST":
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        confirm_consent = form.get("confirm_consent")

        authenticated_user = await authenticate_user_for_grant(db, username=username, password=password)

        if not authenticated_user:
            return HTMLResponse(content=f'''<h1>Login Failed</h1><p>Invalid username or password.</p>
                                        <p><a href="/oauth/authorize?{str(request.query_params)}">Try again</a></p>''',
                                status_code=401)

        if not confirm_consent:
            return HTMLResponse(content=f'''<h1>Consent Required</h1><p>You must confirm consent to proceed.</p>
                                        <p><a href="/oauth/authorize?{str(request.query_params)}">Try again</a></p>''',
                                status_code=400)

        try:
            return await oauth2_server.create_authorization_response(request, grant_user=authenticated_user)
        except Exception as e:
            # import traceback; traceback.print_exc() # For debugging
            raise HTTPException(status_code=400, detail=f"OAuth2 Authorization Error after login: {str(e)}")

    return HTMLResponse(content="<h1>Method Not Allowed</h1>", status_code=405)


@router.post("/token")
async def issue_token(request: Request):
    """OAuth2 Token Endpoint."""
    # The FastAPI `request` object is passed. Authlib's Starlette integration
    # uses this to create its internal request representation and handles
    # calling the registered grant methods (which in turn call our DB functions).
    # The `get_db_session` dependency on the endpoint is crucial if Authlib's
    # methods need to access `request.state.db_session` or if our query methods
    # are structured as dependencies themselves.
    # For now, we assume Authlib's Starlette integration correctly utilizes the session
    # managed by FastAPI's `Depends(get_db_session)` on the endpoint.
    return await oauth2_server.create_token_response(request)
