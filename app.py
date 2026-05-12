import streamlit as st
import asyncio
import json
import os
from dotenv import load_dotenv
from groq import Groq
from fastmcp import Client
import sentry_sdk

# Load environment variables (like GROQ_API_KEY from .env)
load_dotenv()

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),

    # Performance monitoring
    traces_sample_rate=1.0,
)
# Check if GROQ_API_KEY is available
if not os.getenv("GROQ_API_KEY"):
    st.error("GROQ_API_KEY is missing. Please add it to your .env file.")
    st.stop()



# Initialize Groq Client
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """You are an employee management assistant. You help users manage employees using the available tools.
When listing employees, present the results in a clean readable format.
When creating or deleting employees, confirm the action to the user."""

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

async def run_query(messages):
    """Connects to MCP, executes tools in a loop, and returns final assistant message."""
    async with Client("server.py") as client:
        # Discover available MCP tools
        tools = await client.list_tools()
        groq_tools = mcp_tools_to_groq_format(tools)

        try:
        # Get response from Groq
            response = groq_client.chat.completions.create(
                model= "llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
                tools=groq_tools,
                tool_choice="auto"
            )
            assistant_message = response.choices[0].message

        except Exception as e:
            sentry_sdk.capture_exception(e)
            print("Error in tool execution:", e)
            raise 
             

        
        while assistant_message.tool_calls:
            # We need to add the assistant's tool call message to the context
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

            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                
                with st.chat_message("tool", avatar="🛠️"):
                    st.write(f"Calling backend tool: `{tool_name}` with arguments: {tool_args}")
                
                # Execute the tool on the MCP server
                result = await client.call_tool(tool_name, tool_args)
                
                # Append tool result back to Groq
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result)
                })

            # Get next response from Groq after tool results
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
                tools=groq_tools,
                tool_choice="auto"
            )
            assistant_message = response.choices[0].message

        messages.append({"role": "assistant", "content": assistant_message.content})
        return assistant_message.content, messages

# Streamlit UI Configuration
st.set_page_config(page_title="Employee Manager AI", page_icon="👨‍💼")
st.title("👨‍💼 Employee Manager AI")
st.caption("Manage your company's employees through natural language!")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    if message["role"] == "user":
        with st.chat_message("user"):
            st.markdown(message["content"])
    elif message["role"] == "assistant" and "content" in message and message["content"]:
        with st.chat_message("assistant", avatar="🤖"):
            st.markdown(message["content"])

# React to user input
if prompt := st.chat_input("E.g., Create an employee named John who is a Designer"):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.spinner("AI is thinking..."):
        # Run async function in the synchronous Streamlit environment
        final_content, updated_messages = asyncio.run(run_query(list(st.session_state.messages)))
        st.session_state.messages = updated_messages

        with st.chat_message("assistant", avatar="🤖"):
            st.markdown(final_content)
