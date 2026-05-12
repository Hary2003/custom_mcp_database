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

if __name__ == "__main__":
    mcp.run()