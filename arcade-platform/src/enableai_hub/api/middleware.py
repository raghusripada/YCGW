from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseCallNext
from starlette.types import ASGIApp
import json # For parsing request body if necessary

# Tool Executor and User Context will be imported from their respective modules
from enableai_hub.tools.executor import ToolExecutor, ToolCallResult
from enableai_hub.auth.context import get_user_context
from enableai_hub.core.database import AsyncSessionFactory # For DB session in middleware
from enableai_hub.auth.user_manager import get_user_by_email # For user resolution
# LiteLLM for making calls
import litellm
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession # For type hint

# Define Pydantic models for chat completion request and response parts
# These could also live in a dedicated api/models.py or schemas.py file
from pydantic import BaseModel, Field

class ToolCallFunction(BaseModel):
    name: str
    arguments: str # JSON string of arguments

class ToolCall(BaseModel):
    id: str
    type: str = "function" # Typically "function"
    function: ToolCallFunction

class Message(BaseModel):
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None # For tool role messages

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    tools: Optional[List[Dict[str, Any]]] = None # Simplified for now
    tool_choice: Optional[Any] = None # Can be "auto", "none", or specific function
    user: Optional[Any] = None # To pass user identifier
    # Add other standard OpenAI params like stream, temperature, max_tokens etc. if needed by middleware logic
    stream: Optional[bool] = False

class Choice(BaseModel):
    index: int
    message: Message
    finish_reason: Optional[str] = None

class Usage(BaseModel): # Based on LiteLLM's Usage object
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel): # Simplified LiteLLM ModelResponse structure
    id: Optional[str] = None
    choices: List[Choice]
    created: Optional[int] = None
    model: Optional[str] = None
    object: Optional[str] = "chat.completion" # or "chat.completion.chunk" for streaming
    system_fingerprint: Optional[str] = None
    usage: Optional[Usage] = None
    # Custom fields if any for LiteLLM or your platform
    # error: Optional[Dict[str, Any]] = None # If there was an error


class EnableAIToolMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, tool_executor: ToolExecutor):
        super().__init__(app)
        self.tool_executor = tool_executor

    async def dispatch(self, request: Request, call_next: RequestResponseCallNext):
        # Only intercept /v1/chat/completions POST requests
        if request.method != "POST" or not request.url.path.endswith("/v1/chat/completions"):
            return await call_next(request)

        try:
            # Read the body once and store it. This is important as request.body() can only be read once.
            raw_body = await request.body()
            # Use Pydantic model for validation and easy access
            # We need to decode raw_body from bytes to str then parse with json
            try:
                payload_dict = json.loads(raw_body.decode())
                chat_request = ChatCompletionRequest(**payload_dict)
            except json.JSONDecodeError:
                return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})
            except Exception as e: # Pydantic ValidationError
                 return JSONResponse(status_code=400, content={"error": f"Invalid request body: {e}"})

        except Exception as e:
            # Handle cases where reading body fails for other reasons
            return JSONResponse(status_code=400, content={"error": f"Could not read request body: {e}"})

        # Check if tool calling is requested and a user identifier is present
        # The 'user' field is a common way to pass user identifiers in OpenAI-compatible requests
        if chat_request.tools and chat_request.user:
            print("[EnableAIToolMiddleware] Tool calling request identified.")
            async with AsyncSessionFactory() as session:
                try:
                    return await self.handle_tool_calling_request(session, chat_request, payload_dict)
                except Exception as e:
                    # Ensure any exception during tool handling still results in a proper error response
                    # This is a safety net; specific errors should be caught within handle_tool_calling_request
                    print(f"[EnableAIToolMiddleware] Unhandled error during handle_tool_calling_request: {e}")
                    import traceback; traceback.print_exc();
                    raise HTTPException(status_code=500, detail="Internal server error during tool processing.")
        else:
            # If not a tool calling request, or no user, proxy as normal
            # Solution: The middleware will ALWAYS handle the LiteLLM call for this endpoint.
            # If not tool calling, it does a simple proxy.

            print("[EnableAIToolMiddleware] Standard request, proxying to LiteLLM directly.")
            try:
                # Pass the validated Pydantic model's dict representation
                llm_request_data = chat_request.model_dump(exclude_unset=True)
                response = await litellm.acompletion(**llm_request_data)
                # Assuming response is LiteLLM's ModelResponse, convert to dict for JSONResponse
                return JSONResponse(content=response.model_dump())
            except Exception as e:
                # Handle LiteLLM errors
                # This duplicates error handling from proxy.py, ideally centralize it
                print(f"[EnableAIToolMiddleware] Error during direct LiteLLM call: {e}")
                # Consider more specific error mapping based on LiteLLM exceptions
                raise HTTPException(status_code=500, detail=str(e))


    async def handle_tool_calling_request(self, db_session: AsyncSession, chat_request: ChatCompletionRequest, original_payload: Dict[str, Any]):
        print(f"[EnableAIToolMiddleware] Handling tool calling for user identifier: {chat_request.user}")

        if not chat_request.user:
            # This case should ideally be caught by earlier checks if user field is mandatory for tools
            raise HTTPException(status_code=400, detail="User identifier missing in request for tool calling.")

        try:
            user_identifier_str = str(chat_request.user) # Assume it's an email for now

            # Resolve the user identifier to a platform DBUser object
            platform_user = await get_user_by_email(db_session, user_identifier_str)

            if not platform_user:
                # If user is not found by the identifier provided
                raise HTTPException(
                    status_code=403, # Or 404, depending on desired semantics
                    detail=f"User '{user_identifier_str}' not found or not authorized for tool usage."
                )

            print(f"[EnableAIToolMiddleware] Platform user resolved: {platform_user.id} ({platform_user.email})")

            # Now platform_user is a valid DBUser object
            # Pass required_providers=None to let get_user_context use its default logic (e.g. "google")
            user_context = await get_user_context(platform_user, db_session, required_providers=None)

            initial_llm_payload = chat_request.model_dump(exclude_unset=True)
            llm_response = await litellm.acompletion(**initial_llm_payload)

            first_choice = llm_response.choices[0] if llm_response.choices else None
            if not first_choice or not first_choice.message or not first_choice.message.tool_calls:
                return JSONResponse(content=llm_response.model_dump())

            # Assistant's response message that contains the tool calls
            assistant_message_with_tool_calls = Message(
                role="assistant",
                content=first_choice.message.content, # May be None
                tool_calls=first_choice.message.tool_calls
            )

            tool_calls_from_llm = first_choice.message.tool_calls
            tool_results: List[ToolCallResult] = []
            for tool_call_obj in tool_calls_from_llm:
                tool_name = tool_call_obj.function.name
                tool_arguments_str = tool_call_obj.function.arguments
                tool_call_id = tool_call_obj.id
                try:
                    tool_params = json.loads(tool_arguments_str)
                except json.JSONDecodeError:
                    result = ToolCallResult(
                        tool_call_id=tool_call_id, name=tool_name, status="error",
                        content=json.dumps({"error": "Invalid JSON arguments provided by LLM."}),
                        error_message="Invalid JSON arguments."
                    )
                    tool_results.append(result)
                    continue
                result = await self.tool_executor.execute(
                    db_session=db_session, # Pass the session here
                    tool_call_id=tool_call_id, tool_name=tool_name,
                    user_context=user_context, parameters=tool_params
                )
                tool_results.append(result)

            messages_for_final_call = list(chat_request.messages)
            messages_for_final_call.append(assistant_message_with_tool_calls) # Add assistant's response

            return await self.generate_final_response(messages_for_final_call, tool_results, original_payload)

        except litellm.exceptions.APIError as e:
            # This specific error handling for LiteLLM should be fine
            raise HTTPException(status_code=e.status_code or 500, detail=str(e))
        except HTTPException: # Re-raise HTTPExceptions directly
            raise
        except Exception as e:
            # General error handling
            import traceback
            traceback.print_exc()
            # Ensure this is not too verbose for production if not in debug mode
            raise HTTPException(status_code=500, detail=f"An unexpected error occurred while handling tool call: {str(e)}")


    async def generate_final_response(
        self,
        messages_with_assistant_response: List[Message],
        tool_results: List[ToolCallResult],
        original_request_payload: Dict[str, Any]
    ) -> JSONResponse:
        """
        Generates the final LLM response after tool calls have been executed.
        1. Appends tool results as 'tool' role messages to the history.
        2. Makes a second LiteLLM call with the augmented message history.
        3. Returns the final LLM response.
        """
        print("[EnableAIToolMiddleware] Generating final response with tool results.")

        updated_messages = list(messages_with_assistant_response)

        for tool_result in tool_results:
            updated_messages.append(Message(
                role="tool",
                tool_call_id=tool_result.tool_call_id,
                name=tool_result.name,
                content=tool_result.content
            ))

        print(f"[EnableAIToolMiddleware] Messages for final LLM call: {json.dumps([m.model_dump(exclude_none=True) for m in updated_messages], indent=2)}")

        final_llm_payload = original_request_payload.copy()
        final_llm_payload["messages"] = [msg.model_dump(exclude_none=True) for msg in updated_messages]

        final_llm_payload.pop("tools", None)
        final_llm_payload.pop("tool_choice", None)

        print(f"[EnableAIToolMiddleware] Final LLM call payload: {json.dumps(final_llm_payload, indent=2)}")

        try:
            final_llm_response = await litellm.acompletion(**final_llm_payload)
            print(f"[EnableAIToolMiddleware] Final LLM response: {final_llm_response.model_dump_json(indent=2)}")

            return JSONResponse(content=final_llm_response.model_dump())

        except litellm.exceptions.APIError as e:
            print(f"[EnableAIToolMiddleware] LiteLLM APIError during final call: {e}")
            raise HTTPException(status_code=e.status_code or 500, detail=str(e))
        except Exception as e:
            print(f"[EnableAIToolMiddleware] Unexpected error in generate_final_response: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"An unexpected error occurred during final response generation: {str(e)}")
