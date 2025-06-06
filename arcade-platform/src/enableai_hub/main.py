from fastapi import FastAPI, Request # Added Request for on_event
from fastapi.responses import JSONResponse # Added for on_event
from contextlib import asynccontextmanager # For lifespan context manager (FastAPI >= 0.90.0)

from enableai_hub.api.proxy import router as proxy_router
from enableai_hub.api.auth_endpoints import router as auth_router # Import OAuth2 router
from enableai_hub.core.database import create_tables, drop_tables, engine as db_engine # For dev lifecycle & closing engine
from enableai_hub.core.config import AppSettings # Import AppSettings
import litellm
import os

# Import Middleware and ToolExecutor (already present)
from enableai_hub.api.middleware import EnableAIToolMiddleware
from enableai_hub.tools.executor import ToolExecutor

# Import OAuth2 server components
from enableai_hub.auth.oauth_server import oauth2_server, register_oauth_grants

# Load application settings
# It's good practice to have a single, globally accessible settings instance,
# or pass it around. For now, instantiating it here.
settings = AppSettings()


# Lifespan context manager for startup and shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup events
    print("Running startup events...")

    # Configure LiteLLM (already present, moved into lifespan)
    if os.path.exists(settings.litellm.config_path): # Use settings for config path
        litellm.config_path = os.path.abspath(settings.litellm.config_path)
        litellm.set_verbose = True
        print(f"LiteLLM config path set to: {litellm.config_path}")
    else:
        print(f"Warning: LiteLLM config file '{settings.litellm.config_path}' not found. LiteLLM may not function correctly.")

    # Register OAuth2 grants with the server instance
    # This needs to be done once the server object is created.
    # The `oauth2_server` instance is globally defined in `oauth_server.py`.
    # `register_oauth_grants` configures this global instance.
    register_oauth_grants(oauth2_server) # Pass the global server instance
    print("OAuth2 grants registered.")

    # Optional: Database table creation (for development, use Alembic in prod)
    # await drop_tables() # Optional: Clean slate on every startup (dev only)
    # print("Tables dropped (if they existed).")
    # await create_tables() # Creates tables based on SQLAlchemy models
    # print("Tables created based on current models (if they didn't exist). Use Alembic for migrations.")

    print("Startup events complete.")

    yield # Application runs here

    # Shutdown events
    print("Running shutdown events...")
    await db_engine.dispose() # Properly close the database engine connection pool
    print("Database engine disposed.")
    print("Shutdown events complete.")


app = FastAPI(
    title=settings.app_name, # Use from settings
    version="0.1.0", # Consider moving to settings or pyproject.toml as single source
    description="An LLM tool calling platform enabling AI agents to securely execute real-world actions.",
    lifespan=lifespan # Use the lifespan context manager
)

# Initialize ToolExecutor (stubbed version for now)
tool_executor_instance = ToolExecutor()

# Add Middleware
app.add_middleware(
    EnableAIToolMiddleware,
    tool_executor=tool_executor_instance
)

# Include API routers
app.include_router(proxy_router, prefix="/v1", tags=["v1 - LLM Proxy"]) # Updated tag
app.include_router(auth_router, tags=["OAuth2 Authentication"]) # Mount OAuth2 router (prefix is in auth_router itself)


@app.get("/health", summary="Health Check", tags=["Management"])
async def health_check():
    """Perform a health check and return service status."""
    return {"status": "ok", "message": f"{settings.app_name} is running!"}

# Example of how to handle Authlib's OAuth2Error globally (optional)
# from authlib.oauth2.rfc6749 import OAuth2Error
# @app.exception_handler(OAuth2Error)
# async def oauth2_error_handler(request: Request, exc: OAuth2Error):
#     return JSONResponse(
#         status_code=exc.status_code, # Or use exc.get_status_code()
#         content=exc.get_error_body(), # Or use exc.get_body()
#         headers=exc.get_headers()
#     )
