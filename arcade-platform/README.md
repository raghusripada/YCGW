# EnableAI Hub

EnableAI Hub is an LLM tool calling platform enabling AI agents to securely execute real-world actions through user-authorized tools and external services.

## Features

EnableAI Hub provides a robust platform for integrating Large Language Models (LLMs) with external tools and services in a secure and manageable way. Key features include:

*   **OpenAI-Compatible API**: Exposes a `/v1/chat/completions` endpoint, allowing easy integration with existing agent frameworks and OpenAI SDKs.
*   **Multi-Provider LLM Support (via LiteLLM)**: Seamlessly connect to various LLM providers (e.g., OpenAI, Anthropic, and others supported by LiteLLM) using a unified API. Configuration via `litellm_config.yaml`.
*   **Tool Calling Orchestration**: Implements the OpenAI-compatible function/tool calling flow:
    *   Initial LLM call to determine tool usage.
    *   Extraction of tool calls and parameters.
    *   Execution of tools via a `ToolExecutor` (currently with basic MCP client logic).
    *   Secondary LLM call with tool results to generate a final response.
*   **Flexible Tool Definition & Registry**:
    *   Tools are defined and stored in a PostgreSQL database (`ToolDefinition` model).
    *   Supports specifying invocation details (e.g., for MCP tools) and required external authentication.
*   **Platform OAuth 2.0 Server**:
    *   Includes a foundational OAuth 2.0 Authorization Server (`authlib`-based) to protect the platform's own APIs (endpoints for `/oauth/authorize` and `/oauth/token`).
    *   Stores OAuth client details, authorization codes, and tokens in the database.
*   **External Service Authentication (OAuth Client)**:
    *   Enables users to authorize EnableAI Hub to access their accounts on external services (e.g., Google).
    *   Handles the OAuth 2.0 client flow (redirect to provider, callback handling, code-for-token exchange).
    *   **Secure Token Storage**: External service access and refresh tokens are encrypted (AES using Fernet) before being stored in the database (`UserExternalToken` model).
*   **Contextual External Token Management**:
    *   `UserContext` is enriched with active, decrypted external service tokens relevant to the user.
    *   `ToolExecutor` can use these tokens to make authenticated calls to tools that require them.
*   **Basic MCP Client Logic**: The `ToolExecutor` includes foundational logic to act as an HTTP-based client to external MCP (Model Context Protocol) tools.
*   **Database Backend**: Uses PostgreSQL with SQLAlchemy (async) for persistent storage of users, tool definitions, platform OAuth data, and external service tokens.
*   **Database Migrations**: Alembic handles database schema migrations, making schema evolution manageable.
*   **Configuration Management**: Application settings are managed via Pydantic's `AppSettings` and can be overridden by environment variables or a `.env` file.
*   **Asynchronous Architecture**: Built with FastAPI and `asyncio` for high performance.

## Architecture Overview

EnableAI Hub is built as an asynchronous FastAPI application that acts as a central gateway and orchestration layer for LLM tool usage.

Key components include:

*   **FastAPI Application**: The core of the platform, providing all API endpoints.
    *   **`EnableAIToolMiddleware`**: Intercepts `/v1/chat/completions` requests to manage the tool-calling workflow. It orchestrates the two-step LLM call process (initial call to determine tool use, second call after tool execution with results).
*   **LiteLLM Integration**: Used by the middleware to communicate with various configured LLM providers, allowing flexibility in model choice.
*   **`ToolRegistry` (Service + DB Model)**: Stores definitions of available tools in the PostgreSQL database (`ToolDefinition` model), including how they are invoked (e.g., MCP tool details) and if they require external authentication.
*   **`ToolExecutor` (Service)**: Responsible for the actual execution of tools.
    *   Fetches tool definitions from the `ToolRegistry`.
    *   Retrieves necessary external service tokens from the `UserContext`.
    *   Currently implements basic HTTP client logic to communicate with external MCP (Model Context Protocol) tools.
*   **User & Authentication Management**:
    *   **`User` Model (DB)**: Stores platform user information.
    *   **`UserContext` (Pydantic Model)**: In-memory representation of the current user's details, permissions (stubbed), and active external service tokens.
    *   **Platform OAuth 2.0 Server (`authlib`-based)**: Secures the platform's own APIs, managing clients, authorization codes, and tokens (stored in DB).
    *   **External OAuth Client Module**:
        *   Manages OAuth 2.0 flows (initiation, callback) with external service providers (e.g., Google).
        *   `UserExternalToken` Model (DB): Securely stores encrypted access and refresh tokens for these external services, linked to platform users.
        *   `external_auth_manager.py`: Provides services for token encryption, storage, and retrieval.
*   **Database (PostgreSQL with SQLAlchemy & Alembic)**: Serves as the persistent store for all platform data (users, tool definitions, platform OAuth data, external tokens). Alembic manages schema migrations.
*   **External MCP Tools (Conceptual)**: These are envisioned as independent services that the `ToolExecutor` calls. They encapsulate the logic for interacting with specific third-party APIs (like Google Drive), using the user-specific tokens provided by EnableAI Hub.

**High-Level Flow for Tool Use:**

1.  An **Agent Framework** (acting as an OpenAI client) sends a chat completion request (with `tools` and `user` ID) to EnableAI Hub's `/v1/chat/completions` endpoint.
2.  `EnableAIToolMiddleware` intercepts and makes an initial call to an **LLM (via LiteLLM)**.
3.  If the LLM decides to use a tool, the middleware:
    a.  Retrieves the **`UserContext`** (including any necessary decrypted external service tokens for that user).
    b.  Instructs the **`ToolExecutor`** to run the specified tool with given parameters and user context.
4.  The `ToolExecutor`:
    a.  Looks up the **`ToolDefinition`** from the database.
    b.  If external auth is needed, uses the token from `UserContext`.
    c.  Calls the **External MCP Tool** (e.g., over HTTP).
5.  The External MCP Tool performs its task (e.g., calls Google Drive API) and returns a result to the `ToolExecutor`.
6.  The `ToolExecutor` returns a structured `ToolCallResult` to the middleware.
7.  The middleware sends the tool result back to the **LLM (via LiteLLM)** along with the conversation history.
8.  The LLM generates a final response.
9.  EnableAI Hub returns this final response to the Agent Framework.

## Prerequisites

Before you begin, ensure you have the following installed on your system:

*   **Python**: Version 3.9 or higher.
*   **Poetry**: For Python dependency management and package building. (See [Poetry installation guide](https://python-poetry.org/docs/#installation)).
*   **PostgreSQL**: A running PostgreSQL server instance (version 12+ recommended). You will need the database connection URL (including username, password, host, port, and database name).
*   **(Optional) Redis**: A running Redis server instance if you plan to use features like LiteLLM caching or Celery for background tasks (Celery not yet fully implemented).
*   **Git**: For cloning the repository.
*   **(For Tool Development/Testing)** API keys for any LLM providers you wish to use (e.g., OpenAI, Anthropic), configured in `litellm_config.yaml` or via environment variables.
*   **(For External OAuth Tool Testing)** Client ID and Client Secret from external OAuth providers (e.g., Google) if you want to test tools that require them. These are configured in your `.env` file.

## Installation

1.  **Clone the Repository**:
    ```bash
    git clone <your_repository_url_here> # Replace with your actual Git repository URL
    cd enableai-hub
    ```

2.  **Install Dependencies**:
    Use Poetry to install the project dependencies:
    ```bash
    poetry install
    ```
    This will create a virtual environment (if one doesn't exist for the project) and install all packages defined in `pyproject.toml` and `poetry.lock`.

3.  **Setup Configuration**:
    *   Copy the example environment file (if one is provided, e.g., `.env.example`) to `.env`, or create a new `.env` file in the project root (`enableai-hub/`).
    *   Update the `.env` file with your specific configurations. See the "Configuration" section below for details on key variables.

4.  **Database Setup**:
    *   Ensure your PostgreSQL server is running and you have created a database for EnableAI Hub (e.g., `enableai_hub_db`).
    *   Update the `DATABASE_URL` in your `.env` file to point to this database.
    *   **Run Database Migrations**: Apply all database schema migrations using Alembic:
        ```bash
        poetry run alembic upgrade head
        ```
        This will create all necessary tables in your database.

## Configuration

EnableAI Hub is configured using environment variables, which can be conveniently managed using a `.env` file in the project root. The application loads these settings via Pydantic's `AppSettings` (defined in `src/enableai_hub/core/config.py`).

**Key Environment Variables (to be set in your `.env` file):**

*   `DATABASE_URL`: The connection string for your PostgreSQL database.
    *   Example: `DATABASE_URL="postgresql+asyncpg://your_user:your_password@localhost:5432/enableai_hub_db"`
*   `EXTERNAL_TOKEN_FERNET_KEY`: A secret key for encrypting and decrypting external OAuth tokens stored in the database. **This key must be kept secret and secure.**
    *   Generate a new key using Python:
        ```python
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        print(key)
        ```
    *   Example: `EXTERNAL_TOKEN_FERNET_KEY="your_generated_fernet_key_here_minimum_44_chars_base64"`
*   `JWT_SECRET_KEY`: A secret key for signing JWTs issued by EnableAI Hub's own OAuth 2.0 server. **This key must be kept secret and secure.**
    *   Example: `JWT_SECRET_KEY="your_very_strong_jwt_secret_key_at_least_32_chars"`

*   **LLM Provider API Keys**: These are typically referenced in `litellm_config.yaml` using `os.environ/...`.
    *   Example: `OPENAI_API_KEY="sk-..."`
    *   Example: `ANTHROPIC_API_KEY="sk-ant-..."`
    *   (Add others as configured in your `litellm_config.yaml`)

*   **External OAuth Provider Credentials (for EnableAI Hub to act as a client)**:
    *   These are configured using nested environment variables due to `AppSettings.Config.env_nested_delimiter = '__'`.
    *   **For Google Example**:
        *   `AUTH__PROVIDERS__GOOGLE__CLIENT_ID="your_google_client_id.apps.googleusercontent.com"`
        *   `AUTH__PROVIDERS__GOOGLE__CLIENT_SECRET="your_google_client_secret_from_gcp_console"`
        *   `AUTH__PROVIDERS__GOOGLE__PLATFORM_REDIRECT_URI="http://localhost:8000/api/v1/external-auth/google/callback"` (Ensure this matches what you registered with Google and the value in `core/config.py` if not overriding).
    *   (Add similar variables for other providers like GitHub if you configure them).

*   **(Optional) Redis URL**:
    *   Example: `REDIS_URL="redis://localhost:6379/0"`

Refer to `src/enableai_hub/core/config.py` for all available application settings and their default values. Environment variables will override defaults.

## Running the Application

Once you have completed the installation and configuration steps:

1.  **Ensure your database server (PostgreSQL) is running.**
2.  **(Optional) Ensure your Redis server is running** if you intend to use features that depend on it.
3.  **Navigate to the project root directory** (`enableai-hub/`).
4.  **Start the FastAPI application using Uvicorn (via Poetry)**:
    ```bash
    poetry run uvicorn enableai_hub.main:app --reload --host 0.0.0.0 --port 8000
    ```
    *   `--reload`: Enables auto-reload on code changes (for development). Remove this for production.
    *   `--host 0.0.0.0`: Makes the server accessible on your network. Use `localhost` to restrict to local machine.
    *   `--port 8000`: Specifies the port. Change if needed.

5.  The application should now be running and accessible at `http://localhost:8000` (or your configured host/port).
    *   You can check the health endpoint: `http://localhost:8000/health`.
    *   Interactive API documentation (Swagger UI) will be available at `http://localhost:8000/docs`.
    *   Alternative API documentation (ReDoc) will be available at `http://localhost:8000/redoc`.

## Key API Endpoints

EnableAI Hub provides the following key API endpoints:

*   **`POST /v1/chat/completions`**:
    *   OpenAI-compatible endpoint for sending chat messages to LLMs and invoking tools.
    *   Requires a JSON body with `model`, `messages`, and optionally `tools`, `tool_choice`, and `user` identifier.
    *   Handled by `EnableAIToolMiddleware` for tool orchestration.
*   **Platform OAuth 2.0 Endpoints (for securing EnableAI Hub itself)**:
    *   `GET /oauth/authorize`: Initiates the authorization flow for client applications wanting to access EnableAI Hub APIs on behalf of a user. Presents a login/consent form (currently basic).
    *   `POST /oauth/authorize`: Handles the submission of the login/consent form.
    *   `POST /oauth/token`: Issues access tokens (and refresh tokens) to authorized clients.
*   **External Service OAuth Client Endpoints (for linking user accounts to services like Google)**:
    *   `GET /api/v1/external-auth/{provider_name}/login`: Initiates the OAuth 2.0 flow to connect a user's account with an external provider (e.g., `google`). Redirects to the provider.
    *   `GET /api/v1/external-auth/{provider_name}/callback`: Handles the callback from the external provider after user authorization, exchanges the code for tokens, and securely stores them.
*   **`GET /health`**: A simple health check endpoint.

For detailed request/response schemas, please refer to the auto-generated OpenAPI documentation at the `/docs` endpoint when the application is running.

## Using with Agent Frameworks

Agent frameworks (like LangChain, LlamaIndex, or custom agent applications using the OpenAI Python SDK) can use EnableAI Hub as a drop-in replacement for the OpenAI API for chat completions and tool calling.

1.  **Configure the Agent Framework's OpenAI Client**:
    *   **Base URL**: Set the `base_url` (or equivalent like `openai_api_base`) of the OpenAI client to point to your running EnableAI Hub instance.
        *   Example: `http://localhost:8000/v1` (if EnableAI Hub is running locally on port 8000).
    *   **API Key**:
        *   Currently, EnableAI Hub's `/v1/chat/completions` endpoint does not have its own API key authentication implemented. You can pass a dummy API key to the OpenAI client if it requires one (e.g., `api_key="not-needed-for-enableai-hub"`).
        *   *Future Enhancement*: Implement API key authentication for EnableAI Hub itself, at which point a valid key issued by EnableAI Hub would be required.

2.  **Provide Tool Definitions**:
    *   When making a chat completion request that should be able to use tools, the agent framework must send the `tools` parameter in the request.
    *   The `name` of each function in the `tools` list **must exactly match the unique ID** (or a unique name if your lookup logic supports it) of a `ToolDefinition` registered in EnableAI Hub's database.

3.  **Provide User Identifier**:
    *   For tools that operate on behalf of a user (especially those requiring access to user-specific external service data like Google Drive), the agent framework **must send the `user` parameter** in the chat completion request.
    *   Example: `user="user_unique_id_on_agent_platform"`
    *   EnableAI Hub uses this `user` ID to:
        *   Build the `UserContext`.
        *   Retrieve the correct external service OAuth tokens (e.g., Google tokens) associated with that platform user.

4.  **Handling External Authorization**:
    *   If an agent attempts to use a tool requiring external service authorization (e.g., Google Drive) and the user has not yet authorized EnableAI Hub for that service:
        *   EnableAI Hub's `ToolExecutor` will return an error for that specific tool call (e.g., indicating missing token).
        *   The agent framework or the application controlling it should be prepared to handle such errors.
        *   The application can then guide the user to initiate the authorization flow by redirecting them to the appropriate EnableAI Hub endpoint (e.g., `http://localhost:8000/api/v1/external-auth/google/login`).
        *   Once authorization is complete and EnableAI Hub has stored the token, subsequent tool calls by the agent for that user and service should succeed.

**Example (Conceptual Python with OpenAI SDK)**:

```python
from openai import OpenAI

# Configure client to point to your EnableAI Hub instance
client = OpenAI(
    base_url="http://localhost:8000/v1", # Or your deployed EnableAI Hub URL
    api_key="sk-dummy-key-if-needed" # API key for EnableAI Hub (if/when implemented)
)

# User ID on your platform/agent framework
platform_user_id = "user_123_abc"

# Tool definition known to the agent (name must match ID in EnableAI Hub's ToolRegistry)
# This tool ID would correspond to a tool that needs Google Drive access.
google_drive_tool_id = "google_drive_list_files_from_db_uuid" # Example ID

try:
    response = client.chat.completions.create(
        model="gpt-4o", # Or any model configured in EnableAI Hub's LiteLLM setup
        messages=[
            {"role": "user", "content": "List the first 5 files in my Google Drive."}
        ],
        tools=[{
            "type": "function",
            "function": {
                "name": google_drive_tool_id,
                "description": "Lists files in the user's Google Drive.",
                "parameters": { # JSON schema for parameters
                    "type": "object",
                    "properties": {
                        "folder_id": {"type": "string", "description": "The ID of the folder to list."}
                    }
                }
            }
        }],
        tool_choice="auto",
        user=platform_user_id # Crucial for user-specific context and tokens
    )
    final_response = response.choices[0].message
    if final_response.content:
        print("AI:", final_response.content)
    # If further tool calls were made and handled by EnableAI Hub,
    # this final_response should be the culmination of that process.

except openai.APIError as e:
    print(f"API Error: {e}")
    # Handle error, potentially check if it's an auth needed error for a tool
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
