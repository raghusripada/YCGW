from fastapi import FastAPI
from arcade_platform.api.proxy import router as proxy_router
# from arcade_platform.core.config import AppSettings # Will be used later for loading settings
import litellm # Import litellm here
import os

# settings = AppSettings() # Example: Load settings

app = FastAPI(
    title="Arcade Platform",
    version="0.1.0",
    description="An LLM tool calling platform enabling AI agents to securely execute real-world actions."
    # root_path=settings.api_service.root_path # If using a root path proxy
)

# Set LiteLLM config path at startup
# This is one way to ensure LiteLLM knows where to find its configuration.
# Check LiteLLM documentation for the most up-to-date way to set this.
# It might also look for LITELLM_CONFIG_PATH environment variable.
if os.path.exists("litellm_config.yaml"):
    litellm.config_path = os.path.abspath("litellm_config.yaml")
    litellm.set_verbose = True # Often useful during development
    print(f"LiteLLM config path set to: {litellm.config_path}")
else:
    print("Warning: litellm_config.yaml not found. LiteLLM may not function correctly.")


app.include_router(proxy_router, prefix="/v1", tags=["v1"]) # Add tags for grouping in Swagger UI

@app.get("/health", summary="Health Check", tags=["Management"])
async def health_check():
    """Perform a health check and return service status."""
    return {"status": "ok", "message": "Arcade Platform is running!"}
