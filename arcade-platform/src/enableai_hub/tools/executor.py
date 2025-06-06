from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List # Added List
import json
import httpx # For making HTTP calls to MCP tools
import uuid # For UUID conversion and usage

# Assuming UserContext and ExternalTokenInfo are defined in auth.context
from enableai_hub.auth.context import UserContext #, ExternalTokenInfo (used as type hint)
# from enableai_hub.tools.models import ToolDefinition as DBToolDefinition # SQLAlchemy model - Not directly used here, ToolRegistry returns it
from enableai_hub.tools.registry import ToolRegistry # To fetch tool definitions
from sqlalchemy.ext.asyncio import AsyncSession # For type hinting db_session

# ToolCallResult model (already defined)
class ToolCallResult(BaseModel):
    """Represents the result of a single tool call."""
    tool_call_id: str
    name: str
    content: str
    status: str = Field(default="success", pattern="^(success|error)$")
    error_message: Optional[str] = None

    # Pydantic V2 config
    model_config = {"from_attributes": True}


class ToolExecutor:
    """
    Executes tools, including making MCP calls to external tool servers.
    """
    def __init__(self):
        self.tool_registry = ToolRegistry()

    async def execute(
        self,
        db_session: AsyncSession,
        tool_call_id: str,
        tool_name: str, # This is the ID from the LLM tool_call, assumed to be ToolDefinition.id (UUID string)
        user_context: UserContext,
        parameters: Dict[str, Any]
    ) -> ToolCallResult:
        """
        Executes a tool. If it's an MCP tool, makes an HTTP call.
        Handles fetching tool definition and required external auth tokens.
        """
        print(f"[ToolExecutor] Attempting to execute tool: {tool_name} (Call ID: {tool_call_id})")
        print(f"[ToolExecutor] Parameters: {parameters}")
        print(f"[ToolExecutor] User Context ID: {user_context.user_id}")

        # 1. Fetch Tool Definition from database
        try:
            # Assuming tool_name from LLM corresponds to the ToolDefinition's UUID id
            tool_definition_id = uuid.UUID(tool_name)
            tool_definition = await self.tool_registry.get_tool_definition(db_session, tool_definition_id)
        except ValueError: # Invalid UUID format for tool_name
             print(f"[ToolExecutor] Error: tool_name '{tool_name}' is not a valid UUID.")
             return ToolCallResult(
                tool_call_id=tool_call_id, name=tool_name, status="error",
                content=json.dumps({"error": f"Tool name '{tool_name}' is not a valid ID format."}),
                error_message="Invalid tool ID format."
            )
        except Exception as e:
            print(f"[ToolExecutor] Error fetching tool definition for '{tool_name}': {e}")
            return ToolCallResult(
                tool_call_id=tool_call_id, name=tool_name, status="error",
                content=json.dumps({"error": f"Tool definition for '{tool_name}' not found or error fetching."}),
                error_message=f"Tool definition error: {e}"
            )

        if not tool_definition:
            print(f"[ToolExecutor] Tool definition not found for ID: {tool_name}")
            return ToolCallResult(
                tool_call_id=tool_call_id, name=tool_name, status="error",
                content=json.dumps({"error": f"Tool with ID '{tool_name}' not found in registry."}),
                error_message="Tool not found in registry."
            )

        # Use the actual name from the definition for logging and potentially in results if needed
        defined_tool_name = tool_definition.name
        print(f"[ToolExecutor] Found tool definition: {defined_tool_name} v{tool_definition.version} (ID: {tool_definition.id})")

        # 2. Handle External Authentication Token
        external_access_token: Optional[str] = None
        if tool_definition.auth_provider_name:
            print(f"[ToolExecutor] Tool requires auth with provider: {tool_definition.auth_provider_name}")
            token_info = user_context.external_tokens.get(tool_definition.auth_provider_name)
            if not token_info or not token_info.access_token:
                msg = f"Missing or invalid external token for provider '{tool_definition.auth_provider_name}' for user '{user_context.user_id}'."
                print(f"[ToolExecutor] {msg}")
                return ToolCallResult(
                    tool_call_id=tool_call_id, name=defined_tool_name, status="error", # Use defined_tool_name
                    content=json.dumps({"error": msg, "auth_provider": tool_definition.auth_provider_name, "required_scopes": tool_definition.auth_scopes}),
                    error_message=msg
                )
            external_access_token = token_info.access_token
            print(f"[ToolExecutor] Using token for provider: {tool_definition.auth_provider_name}")

        # 3. Invoke the tool based on invocation_details (Basic MCP over HTTP POST for now)
        invocation_config = tool_definition.invocation_details
        if not invocation_config or invocation_config.get("type") != "mcp":
            msg = f"Tool '{defined_tool_name}' has missing or unsupported invocation type in definition. Expected 'mcp'."
            print(f"[ToolExecutor] {msg} Invocation details found: {invocation_config}")
            return ToolCallResult(
                tool_call_id=tool_call_id, name=defined_tool_name, status="error",
                content=json.dumps({"error": msg}), error_message=msg
            )

        mcp_target_url = invocation_config.get("mcp_target_url")
        mcp_method_name = invocation_config.get("mcp_method_name")

        if not mcp_target_url or not mcp_method_name:
            msg = f"Tool '{defined_tool_name}' MCP invocation details (mcp_target_url, mcp_method_name) are missing."
            print(f"[ToolExecutor] {msg}")
            return ToolCallResult(
                tool_call_id=tool_call_id, name=defined_tool_name, status="error",
                content=json.dumps({"error": msg}), error_message=msg
            )

        mcp_payload = {
            "method": mcp_method_name,
            "params": parameters,
        }
        if external_access_token:
            # How the token is sent depends on MCP tool's expectation.
            # Could be in payload, or as a header. Assuming payload for this example.
            mcp_payload["auth_token"] = external_access_token

        headers = {"Content-Type": "application/json"}
        # Example: If MCP tool expects Bearer token in header:
        # if external_access_token:
        #    headers["Authorization"] = f"Bearer {external_access_token}"

        print(f"[ToolExecutor] Calling MCP tool '{defined_tool_name}' at {mcp_target_url} with method {mcp_method_name}")
        try:
            async with httpx.AsyncClient(timeout=tool_definition.execution_timeout_seconds) as client:
                response = await client.post(mcp_target_url, json=mcp_payload, headers=headers)
                response.raise_for_status()

                tool_response_content = response.text
                try:
                    json.loads(tool_response_content)
                except json.JSONDecodeError:
                    pass # Content is string, may or may not be JSON.

                print(f"[ToolExecutor] MCP tool call successful. Response status: {response.status_code}")
                return ToolCallResult(
                    tool_call_id=tool_call_id,
                    name=tool_name, # Return the ID that LLM used for the call
                    status="success",
                    content=tool_response_content
                )
        except httpx.TimeoutException:
            msg = f"MCP tool '{defined_tool_name}' call timed out after {tool_definition.execution_timeout_seconds}s."
            print(f"[ToolExecutor] {msg}")
            return ToolCallResult(
                tool_call_id=tool_call_id, name=tool_name, status="error",
                content=json.dumps({"error": "Tool execution timed out."}), error_message=msg
            )
        except httpx.RequestError as e:
            msg = f"Error calling MCP tool '{defined_tool_name}' at {mcp_target_url}: {e.__class__.__name__} - {e}"
            print(f"[ToolExecutor] {msg}")
            return ToolCallResult(
                tool_call_id=tool_call_id, name=tool_name, status="error",
                content=json.dumps({"error": f"Network error calling tool: {e.__class__.__name__}"}),
                error_message=str(e)
            )
        except httpx.HTTPStatusError as e:
            msg = f"MCP tool '{defined_tool_name}' returned error status {e.response.status_code}: {e.response.text}"
            print(f"[ToolExecutor] {msg}")
            return ToolCallResult(
                tool_call_id=tool_call_id, name=tool_name, status="error",
                content=e.response.text,
                error_message=f"Tool returned error: {e.response.status_code}"
            )
        except Exception as e:
            msg = f"Unexpected error during MCP tool '{defined_tool_name}' execution: {e.__class__.__name__} - {e}"
            print(f"[ToolExecutor] {msg}")
            import traceback; traceback.print_exc();
            return ToolCallResult(
                tool_call_id=tool_call_id, name=tool_name, status="error",
                content=json.dumps({"error": "An unexpected error occurred during tool execution."}),
                error_message=str(e)
            )
