import asyncio
import json
import os
import sentry_sdk

from groq import Groq
from fastmcp import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Sentry
sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),

    # Capture performance traces
    traces_sample_rate=1.0,
)

# Initialize Groq client
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


async def chat_loop():

    # Track entire AI workflow
    with sentry_sdk.start_transaction(
        op="agent.workflow",
        name="Employee Manager Agent"
    ):

        async with Client("server.py") as client:

            # Discover MCP tools
            tools = await client.list_tools()

            groq_tools = mcp_tools_to_groq_format(tools)

            print("=" * 50)
            print("  Employee Manager AI (powered by Groq)")
            print("  Type 'quit' to exit")
            print("=" * 50)

            messages = []

            while True:

                user_input = input("\nYou: ").strip()

                if user_input.lower() in ("quit", "exit"):
                    print("Goodbye!")
                    break

                if not user_input:
                    continue

                messages.append({
                    "role": "user",
                    "content": user_input
                })

                # Monitor LLM call
                with sentry_sdk.start_span(
                    op="llm.call",
                    description="Groq Chat Completion"
                ):

                    response = groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {
                                "role": "system",
                                "content": SYSTEM_PROMPT
                            }
                        ] + messages,
                        tools=groq_tools,
                        tool_choice="auto"
                    )

                assistant_message = response.choices[0].message

                # Tool calling loop
                while assistant_message.tool_calls:

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

                    # Execute MCP tools
                    for tool_call in assistant_message.tool_calls:

                        tool_name = tool_call.function.name

                        tool_args = json.loads(
                            tool_call.function.arguments
                        )

                        print(
                            f"\n[Calling tool: "
                            f"{tool_name}({tool_args})]"
                        )

                        try:

                            # Add MCP context to Sentry
                            sentry_sdk.set_context(
                                "mcp_tool",
                                {
                                    "tool_name": tool_name,
                                    "tool_args": tool_args
                                }
                            )

                            # Track MCP tool execution
                            with sentry_sdk.start_span(
                                op="mcp.tool",
                                description=tool_name
                            ):

                                result = await client.call_tool(
                                    tool_name,
                                    tool_args
                                )

                        except Exception as e:

                            # Send exception to Sentry
                            sentry_sdk.capture_exception(e)

                            result = {
                                "error": str(e)
                            }

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": str(result)
                        })

                    # Ask LLM again after tool execution
                    with sentry_sdk.start_span(
                        op="llm.call",
                        description="Groq Follow-up Completion"
                    ):

                        response = groq_client.chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=[
                                {
                                    "role": "system",
                                    "content": SYSTEM_PROMPT
                                }
                            ] + messages,
                            tools=groq_tools,
                            tool_choice="auto"
                        )

                    assistant_message = response.choices[0].message

                # Final assistant response
                messages.append({
                    "role": "assistant",
                    "content": assistant_message.content
                })

                print(f"\nAssistant: {assistant_message.content}")


if __name__ == "__main__":

    try:
        asyncio.run(chat_loop())

    except Exception as e:

        sentry_sdk.capture_exception(e)

        raise