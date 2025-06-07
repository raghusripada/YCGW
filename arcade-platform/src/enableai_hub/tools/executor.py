from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import json
import httpx
import uuid

from enableai_hub.auth.context import UserContext
from enableai_hub.tools.registry import ToolRegistry
from sqlalchemy.ext.asyncio import AsyncSession

class ToolCallResult(BaseModel):
    tool_call_id: str
    name: str
    content: str
    status: str = Field(default="success", pattern="^(success|error)$")
    error_message: Optional[str] = None
    model_config = {"from_attributes": True}


class ToolExecutor:
    def __init__(self):
        self.tool_registry = ToolRegistry()

    async def execute(
        self,
        db_session: AsyncSession,
        tool_call_id: str,
        tool_name: str,
        user_context: UserContext,
        parameters: Dict[str, Any]
    ) -> ToolCallResult:
        print(f"[ToolExecutor] Attempting to execute tool by name: '{tool_name}' (Call ID: {tool_call_id})")
        print(f"[ToolExecutor] Parameters: {parameters}")
        print(f"[ToolExecutor] User Context ID: {user_context.user_id}")

        assumed_version = "1.0.0"
        try:
            tool_definition = await self.tool_registry.get_tool_definition_by_name_version(
                db_session, name=tool_name, version=assumed_version
            )
        except Exception as e:
            print(f"[ToolExecutor] Error fetching tool definition for '{tool_name}' v'{assumed_version}': {e}")
            return ToolCallResult(
                tool_call_id=tool_call_id, name=tool_name, status="error",
                content=json.dumps({"error": f"Error fetching tool definition for '{tool_name}' v'{assumed_version}'."}),
                error_message=f"Tool definition error: {e}"
            )

        if not tool_definition:
            msg = f"Tool '{tool_name}' version '{assumed_version}' not found in registry."
            print(f"[ToolExecutor] {msg}")
            return ToolCallResult(
                tool_call_id=tool_call_id, name=tool_name, status="error",
                content=json.dumps({"error": msg}),
                error_message=msg
            )

        defined_tool_name_from_db = tool_definition.name
        print(f"[ToolExecutor] Found tool definition: {defined_tool_name_from_db} v{tool_definition.version} (ID: {tool_definition.id})")

        external_access_token: Optional[str] = None
        if tool_definition.auth_provider_name:
            provider_name_lower = tool_definition.auth_provider_name.lower()
            print(f"[ToolExecutor] Tool '{defined_tool_name_from_db}' requires auth with provider: {provider_name_lower}")
            token_info = user_context.external_tokens.get(provider_name_lower)

            if not token_info or not token_info.access_token:
                msg = f"Missing or invalid external token for provider '{provider_name_lower}' for user '{user_context.user_id}' (tool: '{defined_tool_name_from_db}')."
                print(f"[ToolExecutor] {msg}")
                return ToolCallResult(
                    tool_call_id=tool_call_id, name=tool_name, status="error",
                    content=json.dumps({"error": msg, "auth_provider": provider_name_lower}),
                    error_message=msg
                )

            if tool_definition.required_external_scopes:
                granted_scopes = set(token_info.scopes if token_info.scopes else [])
                required_scopes_set = set(tool_definition.required_external_scopes)

                if not required_scopes_set.issubset(granted_scopes):
                    missing_scopes = list(required_scopes_set - granted_scopes)
                    msg = (f"Insufficient scopes for tool '{defined_tool_name_from_db}'. "
                           f"Required: {list(required_scopes_set)}, Granted: {list(granted_scopes)}, Missing: {missing_scopes} "
                           f"for provider '{provider_name_lower}'.")
                    print(f"[ToolExecutor] {msg}")
                    return ToolCallResult(
                        tool_call_id=tool_call_id, name=tool_name, status="error",
                        content=json.dumps({"error": "Insufficient scopes.", "details": msg}),
                        error_message="Insufficient scopes for tool operation."
                    )
                print(f"[ToolExecutor] Sufficient scopes granted for tool '{defined_tool_name_from_db}'.")

            external_access_token = token_info.access_token
            print(f"[ToolExecutor] Using token for provider: {provider_name_lower}")

        invocation_config = tool_definition.invocation_details
        if not invocation_config or invocation_config.get("type") != "mcp":
            msg = f"Tool '{defined_tool_name_from_db}' has missing or unsupported invocation type in definition. Expected 'mcp'."
            print(f"[ToolExecutor] {msg} Invocation details found: {invocation_config}")
            return ToolCallResult(
                tool_call_id=tool_call_id, name=tool_name, status="error",
                content=json.dumps({"error": msg}), error_message=msg
            )

        mcp_target_url = invocation_config.get("mcp_target_url")
        mcp_method_name = invocation_config.get("mcp_method_name")

        if not mcp_target_url or not mcp_method_name:
            msg = f"Tool '{defined_tool_name_from_db}' MCP invocation details (mcp_target_url, mcp_method_name) are missing."
            print(f"[ToolExecutor] {msg}")
            return ToolCallResult(
                tool_call_id=tool_call_id, name=tool_name, status="error",
                content=json.dumps({"error": msg}), error_message=msg
            )

        mcp_payload = {
            "method": mcp_method_name,
            "params": parameters,
        }
        if external_access_token:
            mcp_payload["auth_token"] = external_access_token

        headers = {"Content-Type": "application/json"}

        print(f"[ToolExecutor] Calling MCP tool '{defined_tool_name_from_db}' at {mcp_target_url} with method {mcp_method_name}")
        try:
            async with httpx.AsyncClient(timeout=tool_definition.execution_timeout_seconds) as client:
                response = await client.post(mcp_target_url, json=mcp_payload, headers=headers)
                response.raise_for_status()

                tool_response_content = response.text
                try:
                    json.loads(tool_response_content)
                except json.JSONDecodeError:
                    pass

                print(f"[ToolExecutor] MCP tool call successful. Response status: {response.status_code}")
                return ToolCallResult(
                    tool_call_id=tool_call_id,
                    name=tool_name,
                    status="success",
                    content=tool_response_content
                )
        except httpx.TimeoutException:
            msg = f"MCP tool '{defined_tool_name_from_db}' call timed out after {tool_definition.execution_timeout_seconds}s."
            print(f"[ToolExecutor] {msg}")
            return ToolCallResult(
                tool_call_id=tool_call_id, name=tool_name, status="error",
                content=json.dumps({"error": "Tool execution timed out."}), error_message=msg
            )
        except httpx.RequestError as e:
            msg = f"Error calling MCP tool '{defined_tool_name_from_db}' at {mcp_target_url}: {e.__class__.__name__} - {e}"
            print(f"[ToolExecutor] {msg}")
            return ToolCallResult(
                tool_call_id=tool_call_id, name=tool_name, status="error",
                content=json.dumps({"error": f"Network error calling tool: {e.__class__.__name__}"}),
                error_message=str(e)
            )
        except httpx.HTTPStatusError as e:
            msg = f"MCP tool '{defined_tool_name_from_db}' returned error status {e.response.status_code}: {e.response.text}"
            print(f"[ToolExecutor] {msg}")
            return ToolCallResult(
                tool_call_id=tool_call_id, name=tool_name, status="error",
                content=e.response.text,
                error_message=f"Tool returned error: {e.response.status_code}"
            )
        except Exception as e:
            msg = f"Unexpected error during MCP tool '{defined_tool_name_from_db}' execution: {e.__class__.__name__} - {e}"
            print(f"[ToolExecutor] {msg}")
            import traceback; traceback.print_exc();
            return ToolCallResult(
                tool_call_id=tool_call_id, name=tool_name, status="error",
                content=json.dumps({"error": "An unexpected error occurred during tool execution."}),
                error_message=str(e)
            )
