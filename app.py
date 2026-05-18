import streamlit as st
import asyncio
import json
import os
import pandas as pd
import concurrent.futures
import sqlite3

from dotenv import load_dotenv
from groq import Groq
from fastmcp import Client
import sentry_sdk
import openlit

load_dotenv()
openlit.init(disable_metrics=True)

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    traces_sample_rate=1.0,
)

if not os.getenv("GROQ_API_KEY"):
    st.error("GROQ_API_KEY is missing. Please add it to your .env file.")
    st.stop()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# =========================================
# MCP SERVER URL
# Run `python server.py` in a separate terminal first
# =========================================

MCP_SERVER_URL = "http://localhost:8000/sse"

# =========================================
# DATABASE PATH — must match DATABASE_URL in database.py
# =========================================

DB_PATH = "./test.db"

# =========================================
# ASYNC RUNNER
# Runs coroutines in an isolated thread so
# Streamlit's event loop is never touched.
# =========================================

def run_async(coro):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()

# =========================================
# RBAC
# =========================================

ROLE_PERMISSIONS = {
    "admin": [
        "create_employee", "delete_employee", "update_employee",
        "list_employees", "get_table_schema",
        "execute_read_query", "execute_write_query",
    ],
    "hr": [
        "create_employee", "update_employee", "list_employees",
        "get_table_schema", "execute_read_query", "execute_write_query",
    ],
    "viewer": [
        "list_employees", "get_table_schema", "execute_read_query",
    ],
}

def has_permission(role, tool_name):
    return tool_name in ROLE_PERMISSIONS.get(role, [])

# =========================================
# SYSTEM PROMPTS
# =========================================

SYSTEM_PROMPT = """
You are an employee management assistant.
Help users manage employees using the available tools.
- ONLY use tools allowed for the current role.
- If user asks for unauthorized action, explain politely.
- Present employee lists in a clean readable format.
- Confirm create/delete/update actions clearly.
"""

NL_SQL_SYSTEM_PROMPT = """You are a SQLite SQL expert.
Given a database schema and a natural language request, write a precise SQLite SQL statement.
Rules:
- Return ONLY the raw SQL — no markdown, no backticks, no explanation.
- Use proper SQLite syntax.
- Never generate DROP, CREATE, ALTER, or TRUNCATE statements.
- Prefer explicit column names over SELECT *.
"""

# =========================================
# HELPERS
# =========================================

def mcp_tools_to_groq_format(tools):
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema,
            },
        }
        for t in tools
    ]

def extract_text(result) -> str:
    try:
        return result.content[0].text
    except (AttributeError, IndexError):
        pass
    return str(result) if not isinstance(result, str) else result

# =========================================
# SQL — direct SQLite (no MCP, no subprocess)
# =========================================

def db_get_schema() -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = cursor.fetchall()
        if not tables:
            conn.close()
            return "No tables found."
        parts = []
        for (table_name,) in tables:
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            col_defs = []
            for col in columns:
                defn = f"  {col[1]} {col[2]}"
                if col[5]: defn += "  PRIMARY KEY"
                if col[3]: defn += "  NOT NULL"
                col_defs.append(defn)
            parts.append(
                f"CREATE TABLE {table_name} (\n" + ",\n".join(col_defs) + "\n);"
            )
        conn.close()
        return "\n\n".join(parts)
    except sqlite3.Error as e:
        return f"Schema error: {e}"


def db_execute_read(sql: str) -> dict:
    sql = sql.strip()
    if not sql.upper().startswith("SELECT"):
        return {"error": "Only SELECT queries are allowed."}
    for kw in ["DROP ", "DELETE ", "INSERT ", "UPDATE ", "ALTER ", "CREATE "]:
        if kw in sql.upper():
            return {"error": f"Forbidden keyword: {kw.strip()}"}
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql)
        columns = [d[0] for d in cursor.description] if cursor.description else []
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return {"columns": columns, "rows": rows, "count": len(rows)}
    except sqlite3.Error as e:
        return {"error": str(e)}


def db_execute_write(sql: str) -> dict:
    sql = sql.strip()
    first_word = sql.upper().split()[0] if sql else ""
    if first_word not in ("INSERT", "UPDATE", "DELETE"):
        return {"error": "Only INSERT, UPDATE, DELETE are allowed."}
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return {"success": True, "operation": first_word, "rows_affected": affected}
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
            conn.close()
        return {"error": str(e)}


def generate_sql(nl_query: str, schema: str, role: str) -> str:
    read_only = (
        "\nIMPORTANT: Read-only user — generate ONLY a SELECT query."
        if role == "viewer" else ""
    )
    prompt = (
        f"Database schema:\n{schema}\n\n"
        f'Request: "{nl_query}"{read_only}\n\nSQL:'
    )
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": NL_SQL_SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.1,
    )
    sql = response.choices[0].message.content.strip()
    return sql.replace("```sql", "").replace("```", "").strip()

# =========================================
# CHAT — uses MCP over HTTP
# NOTE: all st.session_state values are passed
# as plain arguments — never accessed inside
# the async function running in a worker thread.
# =========================================

async def run_query(messages, current_role):
    async with Client(MCP_SERVER_URL) as client:
        tools = await client.list_tools()
        groq_tools = mcp_tools_to_groq_format(tools)

        role_prompt = (
            f"\nCurrent user role: {current_role}\n"
            f"Allowed tools: {ROLE_PERMISSIONS[current_role]}\n"
            "Never use tools outside these permissions.\n"
        )

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

            for tc in assistant_message.tool_calls:
                tool_name = tc.function.name
                tool_args = json.loads(tc.function.arguments)

                # Note: we cannot use st.chat_message here (worker thread)
                # Tool call info is included in the final message instead
                print(f"[Tool] {tool_name} → {tool_args}")

                if not has_permission(current_role, tool_name):
                    result_text = (
                        f"❌ ACCESS DENIED — "
                        f"`{current_role}` cannot use `{tool_name}`"
                    )
                    sentry_sdk.capture_message(
                        f"Unauthorized | Role: {current_role} | Tool: {tool_name}"
                    )
                else:
                    try:
                        raw = await client.call_tool(tool_name, tool_args)
                        result_text = extract_text(raw)
                    except Exception as e:
                        sentry_sdk.capture_exception(e)
                        result_text = f"❌ Tool failed: {e}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
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

        messages.append({"role": "assistant", "content": assistant_message.content})
        return assistant_message.content, messages

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

# ── Session state (must come before any widget) ───────────────────────────────

for key, val in {
    "messages": [],
    "user_role": "viewer",
    "db_schema": None,
    "generated_sql": "",
    "sql_result": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ── Sidebar ───────────────────────────────────────────────────────────────────

st.sidebar.title("🔐 Access Control")

selected_role = st.sidebar.selectbox(
    "Select User Role",
    ["admin", "hr", "viewer"],
    index=["admin", "hr", "viewer"].index(st.session_state.user_role),
)

if selected_role != st.session_state.user_role:
    st.session_state.generated_sql = ""
    st.session_state.sql_result = None

st.session_state.user_role = selected_role

st.sidebar.markdown("---")
st.sidebar.subheader("✅ Allowed Permissions")
for p in ROLE_PERMISSIONS[selected_role]:
    st.sidebar.success(p)

st.sidebar.markdown("---")
st.sidebar.subheader("🖥️ MCP Server")
st.sidebar.code("python server.py", language="bash")
st.sidebar.caption("Run in a separate terminal before using the Chat tab.")

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_chat, tab_sql = st.tabs(["💬 Chat", "🗄️ SQL Assistant"])

# ──────────────────────────────────────────
# TAB 1 — CHAT
# ──────────────────────────────────────────

with tab_chat:

    for msg in st.session_state.messages:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.markdown(msg["content"])
        elif msg["role"] == "assistant" and msg.get("content"):
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(msg["content"])

    if prompt := st.chat_input("Example: List all employees"):

        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Read session state values BEFORE entering the worker thread
        messages_snapshot = list(st.session_state.messages)
        role_snapshot     = st.session_state.user_role

        with st.spinner("AI is thinking..."):
            try:
                final_content, updated = run_async(
                    run_query(messages_snapshot, role_snapshot)
                )
                st.session_state.messages = updated
                with st.chat_message("assistant", avatar="🤖"):
                    st.markdown(final_content)

            except Exception as e:
                sentry_sdk.capture_exception(e)
                st.error(f"Application Error: {e}")

# ──────────────────────────────────────────
# TAB 2 — SQL ASSISTANT (direct DB, no MCP)
# ──────────────────────────────────────────

with tab_sql:

    st.subheader("🗄️ Natural Language SQL")
    st.caption("Ask questions or make changes using plain English.")

    role = st.session_state.user_role

    if role == "viewer":
        st.info(
            "👁️ **Read-only access** — only SELECT queries allowed.",
            icon="ℹ️",
        )
    else:
        st.success(
            f"✏️ **{role.upper()} access** — read and write queries enabled.",
            icon="✅",
        )

    st.markdown("---")

    # Schema panel
    s_col, b_col = st.columns([5, 1])
    with s_col:
        expander = st.expander(
            "📋 Database Schema"
            + (" (loaded)" if st.session_state.db_schema else ""),
            expanded=False,
        )
    with b_col:
        if st.button("🔄 Load", use_container_width=True):
            st.session_state.db_schema = db_get_schema()

    if st.session_state.db_schema:
        with expander:
            st.code(st.session_state.db_schema, language="sql")
    else:
        with expander:
            st.caption("Click **🔄 Load** to fetch the schema.")

    st.markdown("---")

    # Natural language input
    nl_query = st.text_input(
        "Describe what you want in plain English",
        placeholder="e.g. Show all employees hired after 2022",
        key="nl_sql_input",
    )

    if st.button("⚡ Generate SQL", disabled=not nl_query.strip()):
        with st.spinner("Generating SQL..."):
            try:
                if not st.session_state.db_schema:
                    st.session_state.db_schema = db_get_schema()
                sql = generate_sql(nl_query, st.session_state.db_schema, role)
                st.session_state.generated_sql = sql
                st.session_state.sql_result = None
            except Exception as e:
                sentry_sdk.capture_exception(e)
                st.error(f"SQL generation failed: {e}")

    # SQL editor
    if st.session_state.generated_sql:

        st.markdown("**✏️ Generated SQL** — review and edit before executing:")

        edited_sql = st.text_area(
            "sql_editor",
            value=st.session_state.generated_sql,
            height=130,
            label_visibility="collapsed",
            key="sql_editor",
        )

        first_word = (
            edited_sql.strip().upper().split()[0] if edited_sql.strip() else ""
        )
        is_write = first_word in ("INSERT", "UPDATE", "DELETE")

        if is_write and not has_permission(role, "execute_write_query"):
            st.warning(
                f"⚠️ Role **{role}** cannot run `{first_word}` queries.",
                icon="🚫",
            )
            sentry_sdk.capture_message(
                f"Blocked write SQL | Role: {role} | Op: {first_word}"
            )
        else:
            if is_write:
                st.warning(
                    f"⚠️ This **{first_word}** query will modify data.",
                    icon="⚠️",
                )
                exec_label = f"⚠️ Execute {first_word}"
            else:
                exec_label = "▶️ Execute Query"

            if st.button(exec_label):
                result = (
                    db_execute_write(edited_sql)
                    if is_write
                    else db_execute_read(edited_sql)
                )
                st.session_state.sql_result = result

    # Results
    if st.session_state.sql_result:

        st.markdown("---")
        result = st.session_state.sql_result

        if "error" in result:
            st.error(f"❌ **Query Error:** {result['error']}")

        elif "rows" in result:
            st.success(f"✅ {result.get('count', 0)} row(s) returned")
            if result["rows"]:
                df = pd.DataFrame(result["rows"])
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.download_button(
                    "⬇️ Download as CSV",
                    data=df.to_csv(index=False).encode("utf-8"),
                    file_name="results.csv",
                    mime="text/csv",
                )
            else:
                st.info("No rows matched.")

        elif "rows_affected" in result:
            st.success(
                f"✅ **{result.get('operation')}** successful — "
                f"{result.get('rows_affected', 0)} row(s) affected."
            )

        else:
            st.text(result.get("raw", str(result)))