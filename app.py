import streamlit as st
import asyncio
import json
import os
import pandas as pd
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
        "list_employees",
        "get_table_schema",
        "execute_read_query",
        "execute_write_query",
    ],
    "hr": [
        "create_employee",
        "update_employee",
        "list_employees",
        "get_table_schema",
        "execute_read_query",
        "execute_write_query",
    ],
    "viewer": [
        "list_employees",
        "get_table_schema",
        "execute_read_query",
    ],
}


def has_permission(role, tool_name):
    allowed_tools = ROLE_PERMISSIONS.get(role, [])
    return tool_name in allowed_tools


# =========================================
# SYSTEM PROMPTS
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

NL_SQL_SYSTEM_PROMPT = """You are a SQLite SQL expert.
Given a database schema and a natural language request, write a precise SQLite SQL statement.

Rules:
- Return ONLY the raw SQL — no markdown fences, no backticks, no explanation.
- Use proper SQLite syntax and quoting.
- Never generate DROP, CREATE, ALTER, or TRUNCATE statements.
- Prefer explicit column names over SELECT *.
"""

# =========================================
# HELPER FUNCTIONS
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
                "parameters": tool.inputSchema,
            },
        })
    return groq_tools


def _extract_text_from_mcp_result(result) -> str:
    """Safely extract a plain string from an MCP tool result."""
    if isinstance(result, str):
        return result
    # FastMCP wraps results in content objects
    if hasattr(result, "__iter__"):
        for item in result:
            if hasattr(item, "text"):
                return item.text
    return str(result)


# =========================================
# CHAT AI FUNCTION (existing)
# =========================================


async def run_query(messages):
    async with Client("server.py") as client:

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
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT + role_prompt}
                ] + messages,
                tools=groq_tools,
                tool_choice="auto",
            )
            assistant_message = response.choices[0].message

        except Exception as e:
            sentry_sdk.capture_exception(e)
            print("Error in initial AI response:", e)
            raise

        while assistant_message.tool_calls:

            messages.append({
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in assistant_message.tool_calls
                ],
            })

            for tool_call in assistant_message.tool_calls:

                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                with st.chat_message("tool", avatar="🛠️"):
                    st.write(
                        f"Attempting tool: `{tool_name}` with args: {tool_args}"
                    )

                user_role = st.session_state.user_role

                if not has_permission(user_role, tool_name):
                    result = (
                        f"❌ ACCESS DENIED\n\n"
                        f"Role `{user_role}` cannot access `{tool_name}`"
                    )
                    sentry_sdk.capture_message(
                        f"Unauthorized access attempt | "
                        f"Role: {user_role} | Tool: {tool_name}"
                    )
                else:
                    try:
                        result = await client.call_tool(tool_name, tool_args)
                    except Exception as e:
                        sentry_sdk.capture_exception(e)
                        result = f"❌ Tool execution failed:\n\n{str(e)}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                })

            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT + role_prompt}
                ] + messages,
                tools=groq_tools,
                tool_choice="auto",
            )
            assistant_message = response.choices[0].message

        messages.append({
            "role": "assistant",
            "content": assistant_message.content,
        })
        return assistant_message.content, messages


# =========================================
# NL → SQL FUNCTIONS
# =========================================


async def fetch_schema() -> str:
    """Fetch the live database schema via MCP."""
    async with Client("server.py") as client:
        result = await client.call_tool("get_table_schema", {})
    try:
        return result.content[0].text
    except (AttributeError, IndexError):
        return str(result)


async def generate_sql_from_nl(nl_query: str, schema: str, role: str) -> str:
    """Use Groq to turn a natural-language query into a SQL statement."""

    read_only_note = (
        "\nIMPORTANT: This user has read-only access — "
        "generate ONLY a SELECT query."
        if role == "viewer"
        else ""
    )

    prompt = (
        f"Database schema:\n{schema}\n\n"
        f'Natural language request: "{nl_query}"{read_only_note}\n\n'
        "SQL:"
    )

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": NL_SQL_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,  # low temperature → more deterministic SQL
    )

    sql = response.choices[0].message.content.strip()
    # Strip accidental markdown fences
    sql = sql.replace("```sql", "").replace("```", "").strip()
    return sql



async def execute_sql_via_mcp(sql: str, is_write: bool) -> dict:
    """Execute a SQL query through the MCP server and return a parsed dict."""
    tool_name = "execute_write_query" if is_write else "execute_read_query"
    async with Client("server.py") as client:
        result = await client.call_tool(tool_name, {"sql": sql})
    try:
        raw = result.content[0].text
    except (AttributeError, IndexError):
        raw = str(result)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}
# =========================================
# STREAMLIT UI
# =========================================

st.set_page_config(
    page_title="Employee Manager AI",
    page_icon="👨‍💼",
    layout="wide",
)

st.title("👨‍💼 Employee Manager AI")
st.caption("Manage employees with AI + MCP + RBAC")

# =========================================
# SESSION STATE
# =========================================

defaults = {
    "messages": [],
    "user_role": "viewer",
    "db_schema": None,
    "generated_sql": "",
    "sql_result": None,
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# =========================================
# SIDEBAR
# =========================================

st.sidebar.title("🔐 Access Control")

selected_role = st.sidebar.selectbox(
    "Select User Role",
    ["admin", "hr", "viewer"],
    index=["admin", "hr", "viewer"].index(st.session_state.user_role),
)

# Reset SQL state on role change
if selected_role != st.session_state.user_role:
    st.session_state.generated_sql = ""
    st.session_state.sql_result = None

st.session_state.user_role = selected_role

st.sidebar.markdown("---")
st.sidebar.subheader("✅ Allowed Permissions")
for permission in ROLE_PERMISSIONS[selected_role]:
    st.sidebar.success(permission)

# =========================================
# TABS
# =========================================

tab_chat, tab_sql = st.tabs(["💬 Chat", "🗄️ SQL Assistant"])

# ──────────────────────────────────────────
# TAB 1 — CHAT (existing functionality)
# ──────────────────────────────────────────

with tab_chat:

    # Display chat history
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

    # User input
    if prompt := st.chat_input("Example: Create employee John as Designer"):

        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.spinner("AI is thinking..."):
            try:
                final_content, updated_messages = asyncio.run(
                    run_query(list(st.session_state.messages))
                )
                st.session_state.messages = updated_messages
                with st.chat_message("assistant", avatar="🤖"):
                    st.markdown(final_content)

            except Exception as e:
                sentry_sdk.capture_exception(e)
                st.error(f"Application Error: {str(e)}")

# ──────────────────────────────────────────
# TAB 2 — NL SQL ASSISTANT
# ──────────────────────────────────────────

with tab_sql:

    st.subheader("🗄️ Natural Language SQL")
    st.caption("Ask questions or make changes using plain English.")

    role = st.session_state.user_role

    # Role info banner
    if role == "viewer":
        st.info(
            "👁️ **Read-only access** — only SELECT queries will be generated and allowed.",
            icon="ℹ️",
        )
    else:
        st.success(
            f"✏️ **{role.upper()} access** — SELECT and write queries (INSERT / UPDATE / DELETE) are enabled.",
            icon="✅",
        )

    st.markdown("---")

    # ── Schema Panel ─────────────────────────────────────────────────────────

    schema_col, btn_col = st.columns([5, 1])

    with schema_col:
        schema_expander = st.expander(
            "📋 Database Schema" + (" (loaded)" if st.session_state.db_schema else ""),
            expanded=False,
        )

    with btn_col:
        if st.button("🔄 Load", use_container_width=True, help="Fetch live schema"):
            with st.spinner("Fetching schema..."):
                try:
                    st.session_state.db_schema = asyncio.run(fetch_schema())
                except Exception as e:
                    sentry_sdk.capture_exception(e)
                    st.error(f"Could not load schema: {e}")

    if st.session_state.db_schema:
        with schema_expander:
            st.code(st.session_state.db_schema, language="sql")
    else:
        with schema_expander:
            st.caption("Click **🔄 Load** to fetch the current schema.")

    st.markdown("---")

    # ── NL Input ─────────────────────────────────────────────────────────────

    nl_query = st.text_input(
        "Describe what you want in plain English",
        placeholder=(
            "e.g. Show all employees in Engineering hired after 2023"
            if role == "viewer"
            else "e.g. Update salary to 90000 for employees in Marketing"
        ),
        key="nl_sql_input",
    )

    generate_btn = st.button(
        "⚡ Generate SQL",
        disabled=not nl_query.strip(),
        use_container_width=False,
    )

    if generate_btn and nl_query.strip():
        with st.spinner("Generating SQL with Groq..."):
            try:
                # Auto-load schema if needed
                if not st.session_state.db_schema:
                    st.session_state.db_schema = asyncio.run(fetch_schema())

                generated = asyncio.run(
                    generate_sql_from_nl(
                        nl_query,
                        st.session_state.db_schema,
                        role,
                    )
                )
                st.session_state.generated_sql = generated
                st.session_state.sql_result = None  # clear previous results

            except Exception as e:
                sentry_sdk.capture_exception(e)
                st.error(f"SQL generation failed: {e}")

    # ── SQL Editor ───────────────────────────────────────────────────────────

    if st.session_state.generated_sql:

        st.markdown("**✏️ Generated SQL** — review and edit before executing:")

        edited_sql = st.text_area(
            "sql_editor",
            value=st.session_state.generated_sql,
            height=130,
            label_visibility="collapsed",
            key="sql_editor",
        )

        # Detect operation type
        first_word = edited_sql.strip().upper().split()[0] if edited_sql.strip() else ""
        is_write = first_word in ("INSERT", "UPDATE", "DELETE")

        # RBAC gate for write queries
        if is_write and not has_permission(role, "execute_write_query"):
            st.warning(
                f"⚠️ Role **{role}** does not have permission to run `{first_word}` queries.",
                icon="🚫",
            )
            sentry_sdk.capture_message(
                f"Blocked write SQL attempt | Role: {role} | Op: {first_word}"
            )

        else:
            # Differentiate button style for destructive operations
            if is_write:
                st.warning(
                    f"⚠️ This is a **{first_word}** query and will modify data.",
                    icon="⚠️",
                )
                exec_label = f"⚠️ Execute {first_word}"
            else:
                exec_label = "▶️ Execute Query"

            if st.button(exec_label, use_container_width=False):
                with st.spinner("Executing..."):
                    try:
                        result = asyncio.run(execute_sql_via_mcp(edited_sql, is_write))
                        st.session_state.sql_result = result
                    except Exception as e:
                        sentry_sdk.capture_exception(e)
                        st.error(f"Execution error: {e}")

    # ── Results ──────────────────────────────────────────────────────────────

    if st.session_state.sql_result:

        st.markdown("---")
        result = st.session_state.sql_result

        if "error" in result:
            st.error(f"❌ **Query Error:** {result['error']}")

        elif "rows" in result:
            # SELECT results → DataFrame
            count = result.get("count", len(result["rows"]))
            st.success(f"✅ {count} row(s) returned")

            if result["rows"]:
                df = pd.DataFrame(result["rows"])
                st.dataframe(df, use_container_width=True, hide_index=True)

                # CSV download
                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="⬇️ Download as CSV",
                    data=csv,
                    file_name="query_results.csv",
                    mime="text/csv",
                )
            else:
                st.info("Query executed successfully — no rows matched.")

        elif "rows_affected" in result:
            # Write operation success
            op = result.get("operation", "Query")
            affected = result.get("rows_affected", 0)
            st.success(f"✅ **{op}** successful — {affected} row(s) affected.")

        else:
            # Fallback: show raw output
            st.text(result.get("raw", str(result)))