import streamlit as st
import asyncio
import json
import os
from dotenv import load_dotenv
from groq import Groq
from fastmcp import Client
import sentry_sdk
import openlit

# Load environment variables
load_dotenv()

# Initialize OpenLIT
openlit.init()
print("OpenLIT initialized")

# Initialize Sentry
sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    traces_sample_rate=1.0,
)

# Check API Key
if not os.getenv("GROQ_API_KEY"):
    st.error("GROQ_API_KEY is missing. Please add it to your .env file.")
    st.stop()

# Initialize Groq Client
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# =========================================
# ROLE BASED ACCESS CONTROL (RBAC)
# =========================================

ROLE_PERMISSIONS = {
    "admin": [
        "create_employee",
        "delete_employee",
        "update_employee",
        "list_employees"
    ],
    "hr": [
        "create_employee",
        "update_employee",
        "list_employees"
    ],
    "viewer": [
        "list_employees"
    ]
}

def has_permission(role, tool_name):
    allowed_tools = ROLE_PERMISSIONS.get(role, [])
    return tool_name in allowed_tools

# =========================================
# SYSTEM PROMPT
# =========================================

SYSTEM_PROMPT = """
You are an employee management assistant.

You help users manage employees using the available tools.

Rules:
- ONLY use tools allowed for the current role.
- Never attempt restricted tools.
- If user asks for unauthorized action, explain politely.

When listing employees:
- Present results in clean readable format.

When creating/deleting/updating employees:
- Confirm the action clearly.
"""

# =========================================
# HELPER FUNCTION
# =========================================

def mcp_tools_to_groq_format(tools):
    """Convert MCP tool definitions to Groq/OpenAI function calling format."""
    
    groq_tools = []

    for tool in tools:
        groq_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema
            }
        })

    return groq_tools

# =========================================
# MAIN AI FUNCTION
# =========================================

async def run_query(messages):

    async with Client("server.py") as client:

        # Discover MCP tools
        tools = await client.list_tools()
        groq_tools = mcp_tools_to_groq_format(tools)

        current_role = st.session_state.user_role

        role_prompt = f"""

Current user role: {current_role}

Allowed tools:
{ROLE_PERMISSIONS[current_role]}

Important:
- Never use tools outside these permissions.
"""

        try:
            # First AI Response
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT + role_prompt
                    }
                ] + messages,
                tools=groq_tools,
                tool_choice="auto"
            )

            assistant_message = response.choices[0].message

        except Exception as e:
            sentry_sdk.capture_exception(e)
            print("Error in initial AI response:", e)
            raise

        # =========================================
        # TOOL EXECUTION LOOP
        # =========================================

        while assistant_message.tool_calls:

            # Save assistant tool calls
            messages.append({
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in assistant_message.tool_calls
                ]
            })

            # Execute each tool
            for tool_call in assistant_message.tool_calls:

                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                with st.chat_message("tool", avatar="🛠️"):
                    st.write(
                        f"Attempting tool: `{tool_name}` "
                        f"with args: {tool_args}"
                    )

                # =========================================
                # RBAC CHECK
                # =========================================

                user_role = st.session_state.user_role

                if not has_permission(user_role, tool_name):

                    result = (
                        f"❌ ACCESS DENIED\n\n"
                        f"Role `{user_role}` "
                        f"cannot access `{tool_name}`"
                    )

                    # Log unauthorized access
                    sentry_sdk.capture_message(
                        f"Unauthorized access attempt | "
                        f"Role: {user_role} | Tool: {tool_name}"
                    )

                else:
                    try:
                        # Execute MCP Tool
                        result = await client.call_tool(
                            tool_name,
                            tool_args
                        )

                    except Exception as e:

                        sentry_sdk.capture_exception(e)

                        result = (
                            f"❌ Tool execution failed:\n\n{str(e)}"
                        )

                # Append tool result
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result)
                })

            # =========================================
            # SECOND AI RESPONSE
            # =========================================

            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT + role_prompt
                    }
                ] + messages,
                tools=groq_tools,
                tool_choice="auto"
            )

            assistant_message = response.choices[0].message

        # Save final assistant response
        messages.append({
            "role": "assistant",
            "content": assistant_message.content
        })

        return assistant_message.content, messages

# =========================================
# STREAMLIT UI
# =========================================

st.set_page_config(
    page_title="Employee Manager AI",
    page_icon="👨‍💼",
    layout="wide"
)

st.title("👨‍💼 Employee Manager AI")
st.caption("Manage employees with AI + MCP + RBAC")

# =========================================
# SESSION STATE
# =========================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "user_role" not in st.session_state:
    st.session_state.user_role = "viewer"

# =========================================
# SIDEBAR
# =========================================

st.sidebar.title("🔐 Access Control")

selected_role = st.sidebar.selectbox(
    "Select User Role",
    ["admin", "hr", "viewer"],
    index=2
)

st.session_state.user_role = selected_role

st.sidebar.markdown("---")

st.sidebar.subheader("Allowed Permissions")

for permission in ROLE_PERMISSIONS[selected_role]:
    st.sidebar.success(permission)

# =========================================
# DISPLAY CHAT HISTORY
# =========================================

for message in st.session_state.messages:

    if message["role"] == "user":

        with st.chat_message("user"):
            st.markdown(message["content"])

    elif (
        message["role"] == "assistant"
        and "content" in message
        and message["content"]
    ):

        with st.chat_message("assistant", avatar="🤖"):
            st.markdown(message["content"])

# =========================================
# USER INPUT
# =========================================

if prompt := st.chat_input(
    "Example: Create employee John as Designer"
):

    # Show user message
    st.chat_message("user").markdown(prompt)

    # Save message
    st.session_state.messages.append({
        "role": "user",
        "content": prompt
    })

    with st.spinner("AI is thinking..."):

        try:
            # Run async AI function
            final_content, updated_messages = asyncio.run(
                run_query(
                    list(st.session_state.messages)
                )
            )

            # Update session
            st.session_state.messages = updated_messages

            # Show AI response
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(final_content)

        except Exception as e:

            sentry_sdk.capture_exception(e)

            st.error(f"Application Error: {str(e)}")