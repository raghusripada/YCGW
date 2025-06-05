from fastapi import FastAPI
from arcade_platform.api.proxy import router as proxy_router
from arcade_platform.core.database import create_tables, drop_tables # For dev lifecycle
import litellm
import os

# Import Middleware and ToolExecutor
from arcade_platform.api.middleware import ArcadeToolMiddleware
from arcade_platform.tools.executor import ToolExecutor

# from arcade_platform.core.config import AppSettings # Will be used later for loading settings
# settings = AppSettings()

app = FastAPI(
    title="Arcade Platform",
    version="0.1.0",
    description="An LLM tool calling platform enabling AI agents to securely execute real-world actions."
    # root_path=settings.api_service.root_path # If using a root path proxy
)

# Initialize ToolExecutor (stubbed version for now)
tool_executor_instance = ToolExecutor()

# Add Middleware
# The middleware should be added before routers if it needs to process all requests to those routes.
# Order matters for middleware.
app.add_middleware(
    ArcadeToolMiddleware,
    tool_executor=tool_executor_instance # Pass the executor instance
)

# Set LiteLLM config path at startup (already present from previous steps)
if os.path.exists("litellm_config.yaml"):
    litellm.config_path = os.path.abspath("litellm_config.yaml")
    litellm.set_verbose = True
    print(f"LiteLLM config path set to: {litellm.config_path}")
else:
    print("Warning: litellm_config.yaml not found. LiteLLM may not function correctly.")

# Include API routers AFTER middleware that might process their requests
app.include_router(proxy_router, prefix="/v1", tags=["v1"])

@app.get("/health", summary="Health Check", tags=["Management"])
async def health_check():
    """Perform a health check and return service status."""
    return {"status": "ok", "message": "Arcade Platform is running!"}

# Optional: Add startup/shutdown events for DB table creation/deletion (for development)
# These should NOT be used in production if using Alembic for schema management.
# @app.on_event("startup")
# async def startup_event():
#     print("Running startup events...")
#     # await drop_tables() # Optional: Clean slate on every startup (dev only)
#     # print("Tables dropped (if they existed).")
#     # await create_tables()
#     # print("Tables created.")
#     print("Startup events complete.")

# @app.on_event("shutdown")
# async def shutdown_event():
#     print("Running shutdown events...")
#     # Perform any cleanup here
#     print("Shutdown events complete.")
