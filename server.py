import os
from dotenv import load_dotenv
from fastmcp import FastMCP
from database import session, Employee

load_dotenv()

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


if __name__ == "__main__":
    mcp.run()