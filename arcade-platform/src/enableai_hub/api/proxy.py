from fastapi import APIRouter, Request, HTTPException, Body
from fastapi.responses import JSONResponse
import litellm
import os # For environment variables if not using Pydantic settings for this part

# It's good practice to load the config path from settings eventually
# from enableai_hub.core.config import settings
LITELLM_CONFIG_PATH = "litellm_config.yaml"
# Ensure LiteLLM can find the config. This might be set on app startup too.
# litellm.config_path = LITELLM_CONFIG_PATH # Set config path for LiteLLM
# Alternatively, LiteLLM might pick it up if it's in the root or specific env var is set.
# For robustness, explicitly load and pass config if needed, or ensure litellm.config_path is set.

router = APIRouter(
    tags=["LLM Proxy"],
)

# This is a simplified version. Error handling, request validation,
# and async streaming should be enhanced for production.
@router.post("/chat/completions", summary="Proxy chat completions to LiteLLM")
async def chat_completions_proxy(
    request: Request,
    payload: dict = Body(...) # Use Body to get the raw JSON payload
):
    """
    Proxies chat completion requests to various LLM providers using LiteLLM.
    The request body should match the OpenAI chat completions format.
    Make sure `litellm_config.yaml` is present and API keys are in environment variables.
    Example payload:
    {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "Hello, how are you?"}],
        "max_tokens": 50,
        "stream": false
    }
    """
    try:
        # LiteLLM's acompletion function expects keyword arguments from the payload.
        # Ensure that essential keys like 'model' and 'messages' are present.
        if "model" not in payload or "messages" not in payload:
            raise HTTPException(status_code=400, detail="Missing 'model' or 'messages' in request payload")

        # Set config path if not already set globally or via environment variables
        # This ensures LiteLLM uses our specified configuration.
        # LiteLLM typically looks for `config.yaml` or `litellm_config.yaml` in the current directory
        # or specific environment variables. Explicitly setting it can be more reliable.
        # litellm.config_path = LITELLM_CONFIG_PATH # Uncomment if needed, or handle in main app startup

        # For this basic version, assume API keys are in environment variables as per litellm_config.yaml
        # e.g., OPENAI_API_KEY, ANTHROPIC_API_KEY

        response = await litellm.acompletion(
            **payload
            # api_key=os.getenv("OPENAI_API_KEY") # Example if you need to pass key explicitly
        )

        # LiteLLM returns a ModelResponse object. Convert to dict for JSON response.
        # If streaming is enabled in payload, response would be an AsyncStreamingChunkIterator.
        # This basic endpoint does not yet handle streaming responses.
        if payload.get("stream"):
            # TODO: Implement streaming response handling
            raise HTTPException(status_code=501, detail="Streaming responses not yet implemented in this basic proxy.")

        return response.dict() # Convert ModelResponse to dict

    except litellm.exceptions.APIConnectionError as e:
        raise HTTPException(status_code=503, detail=f"LiteLLM API Connection Error: {e}")
    except litellm.exceptions.RateLimitError as e:
        raise HTTPException(status_code=429, detail=f"LiteLLM Rate Limit Error: {e}")
    except litellm.exceptions.AuthenticationError as e:
        raise HTTPException(status_code=401, detail=f"LiteLLM Authentication Error: {e}. Ensure API keys are set correctly.")
    except litellm.exceptions.NotFoundError as e:
        raise HTTPException(status_code=404, detail=f"LiteLLM Model Not Found Error: {e}")
    except litellm.exceptions.BadRequestError as e:
        raise HTTPException(status_code=400, detail=f"LiteLLM Bad Request Error: {e}")
    except Exception as e:
        # Catch-all for other LiteLLM errors or unexpected issues
        litellm.utils.print_verbose(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


from typing import List
from fastapi import Depends # Ensure Depends is imported
from enableai_hub.auth.models import User as SQLUser, UserResponse # Import UserResponse
# Assuming UserCreate schema is accessible for response model - not needed for this endpoint
from enableai_hub.auth.user_manager import get_users # service function
from enableai_hub.core.database import get_db_session # DB Session dependency
from sqlalchemy.ext.asyncio import AsyncSession

@router.get("/test-db-users", summary="Test DB: List Users", response_model=List[UserResponse])
async def test_list_users(
    db: AsyncSession = Depends(get_db_session), # Use the DB session dependency
    skip: int = 0,
    limit: int = 10
):
    """
    Test endpoint to list users from the database using the session dependency.
    The SQLUser model should have `model_config = ConfigDict(from_attributes=True)`
    for FastAPI to automatically convert it for the response.
    """
    try:
        users_crud = await get_users(db_session=db, skip=skip, limit=limit)
        return users_crud
    except Exception as e:
        # Log the exception e
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
