import os
from dotenv import load_dotenv
from fastmcp import FastMCP
from database import session, Employee

load_dotenv()
import sqlite3
import json 
mcp = FastMCP("employee-manager")


@mcp.tool()
def create_employee(name: str, role: str):
    """Create a new employee with a name and role."""
    db = session()
    employee = Employee(name=name, role=role)
    db.add(employee)
    db.commit()
    db.close()
    return "Employee created successfully"


@mcp.tool()
def list_employees():
    """List all employees."""
    db = session()
    employees = db.query(Employee).all()
    db.close()
    return [str(e) for e in employees]


@mcp.tool()
def delete_employee(id: int):
    """Delete an employee by their ID."""
    db = session()
    employee = db.query(Employee).filter(Employee.id == id).first()
    if not employee:
        return "Employee not found"
    db.delete(employee)
    db.commit()
    db.close()
    return "Employee deleted successfully"


@mcp.tool()
def update_employee(id: int, name: str = None, role: str = None):
    """Update an employee's name or role by their ID."""
    db = session()
    employee = db.query(Employee).filter(Employee.id == id).first()
    if not employee:
        raise Exception("Employee not found")
    if name:
        employee.name = name
    if role:
        employee.role = role
    db.commit()
    db.close()
    return f"Employee {id} updated successfully"


@mcp.tool()
def change_id(id: int, new_id: int):
    """Change an employee's ID."""
    db = session()
    employee = db.query(Employee).filter(Employee.id == id).first()
    if not employee:
        return "Employee not found"
    employee.id = new_id
    db.commit()
    db.close()
    return f"Employee {id} id changed to {new_id}"


@mcp.tool()
def delete_employee_by_name(name: str):
    """Delete an employee by their name."""
    db = session()
    employee = db.query(Employee).filter(Employee.name == name).first()
    if not employee:
        return "Employee not found"
    db.delete(employee)
    db.commit()
    db.close()
    return f"Employee {name} deleted successfully"


@mcp.tool()
def search_employee_by_name(name: str):
    """Search for an employee by name."""
    db = session()
    employee = db.query(Employee).filter(Employee.name == name).first()
    db.close()
    return str(employee) if employee else "Employee not found"


@mcp.tool()
def search_employee_by_id(id: int):
    """Search for an employee by ID."""
    db = session()
    employee = db.query(Employee).filter(Employee.id == id).first()
    db.close()
    return str(employee) if employee else "Employee not found"


@mcp.tool()
def search_employee_by_role(role: str):
    """Search for all employees with a given role."""
    db = session()
    employees = db.query(Employee).filter(Employee.role == role).all()
    db.close()
    return [str(e) for e in employees]

# =========================================
# ADD THESE IMPORTS TO THE TOP OF server.py
# =========================================
# import sqlite3
# import json

# =========================================
# SET YOUR DATABASE PATH
# =========================================

DB_PATH = "./test.db"  # adjust to match your actual SQLite file path


# =========================================
# PASTE THESE 3 TOOLS INTO server.py
# (alongside your existing @mcp.tool() functions)
# =========================================


@mcp.tool()
def get_table_schema() -> str:
    """
    Returns the full SQLite database schema (all tables and columns).
    Use this before generating SQL queries to understand the data structure.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = cursor.fetchall()

        if not tables:
            conn.close()
            return "No tables found in the database."

        schema_parts = []

        for (table_name,) in tables:
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            # Each col: (cid, name, type, notnull, dflt_value, pk)
            col_defs = []
            for col in columns:
                parts = [f"  {col[1]} {col[2]}"]
                if col[5]:   # is primary key
                    parts.append("PRIMARY KEY")
                if col[3]:   # not null
                    parts.append("NOT NULL")
                col_defs.append(" ".join(parts))

            schema_parts.append(
                f"CREATE TABLE {table_name} (\n"
                + ",\n".join(col_defs)
                + "\n);"
            )

        conn.close()
        return "\n\n".join(schema_parts)

    except sqlite3.Error as e:
        return f"Schema fetch error: {str(e)}"


@mcp.tool()
def execute_read_query(sql: str) -> str:
    """
    Execute a read-only SELECT SQL query against the employee database.
    Returns results as a JSON object with 'columns', 'rows', and 'count'.
    Only SELECT statements are permitted.
    """
    sql_clean = sql.strip()

    if not sql_clean.upper().startswith("SELECT"):
        return json.dumps({
            "error": "Only SELECT queries are allowed for read operations."
        })

    # Block any dangerous patterns even inside SELECT
    dangerous = ["DROP ", "DELETE ", "INSERT ", "UPDATE ", "ALTER ", "CREATE "]
    sql_upper = sql_clean.upper()
    for keyword in dangerous:
        if keyword in sql_upper:
            return json.dumps({
                "error": f"Forbidden keyword detected: {keyword.strip()}"
            })

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql_clean)

        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return json.dumps({
            "columns": columns,
            "rows": rows,
            "count": len(rows)
        })

    except sqlite3.Error as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def execute_write_query(sql: str) -> str:
    """
    Execute a write SQL query (INSERT, UPDATE, or DELETE) against the employee database.
    Returns a JSON object with 'success', 'operation', and 'rows_affected'.
    Only INSERT, UPDATE, and DELETE statements are permitted.
    """
    sql_clean = sql.strip()
    first_word = sql_clean.upper().split()[0] if sql_clean else ""

    allowed_ops = ("INSERT", "UPDATE", "DELETE")
    if first_word not in allowed_ops:
        return json.dumps({
            "error": f"Only {', '.join(allowed_ops)} operations are allowed."
        })

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(sql_clean)
        conn.commit()
        rows_affected = cursor.rowcount
        conn.close()

        return json.dumps({
            "success": True,
            "operation": first_word,
            "rows_affected": rows_affected
        })

    except sqlite3.Error as e:
        if conn:
            conn.rollback()
            conn.close()
        return json.dumps({"error": str(e)})

if __name__ == "__main__":
    mcp.run()