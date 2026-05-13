from fastmcp import FastMCP
from database import session
from database import Employee

mcp = FastMCP("test")

@mcp.tool()
def create_employee(name: str, role:str):
    db = session()
    employees = Employee(name=name,role=role)
    db.add(employees)
    db.commit()
    db.close()
    return "Employee created successfully"

@mcp.tool()
def list_employees():
    db = session()
    employees = db.query(Employee).all()
    db.close()
    return employees

@mcp.tool()
def delete_employee(id: int):
    db = session()
    employee = db.query(Employee).filter(Employee.id == id).first()
    if not employee:
        return "Employee not found"
    db.delete(employee)
    db.commit()
    db.close()
    return "Employee deleted successfully"


@mcp.tool()
def update_employee(id: int, name: str=None, role:str=None):
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
    db = session()
    employee = db.query(Employee).filter(Employee.id == id).first()
    if not employee:
        return "Employee not found"
    employee.id = new_id
    db.commit()
    db.close()
    return f"Employee {id} id changed to {new_id}"

if __name__ == "__main__":
    mcp.run()