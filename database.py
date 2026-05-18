from sqlalchemy import (
    create_engine, Column, Integer, String,
    Float, Date, ForeignKey, Enum, Text
)
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
import datetime
import enum

DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)
Base = declarative_base()


# =========================================
# ENUMS
# =========================================

class EmploymentStatus(str, enum.Enum):
    active   = "active"
    inactive = "inactive"
    on_leave = "on_leave"

class LeaveType(str, enum.Enum):
    sick      = "sick"
    casual    = "casual"
    annual    = "annual"
    maternity = "maternity"


# =========================================
# MODELS
# =========================================

class Department(Base):
    __tablename__ = "departments"

    id       = Column(Integer, primary_key=True, index=True)
    name     = Column(String(100), unique=True, nullable=False, index=True)
    location = Column(String(100))
    budget   = Column(Float, default=0.0)

    # Relationships
    employees = relationship("Employee", back_populates="department")

    def __repr__(self):
        return f"Department(id={self.id}, name='{self.name}', location='{self.location}')"


class Employee(Base):
    __tablename__ = "employees"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(100), nullable=False, index=True)
    email         = Column(String(150), unique=True, nullable=False)
    role          = Column(String(100), index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    manager_id    = Column(Integer, ForeignKey("employees.id"), nullable=True)
    status        = Column(Enum(EmploymentStatus), default=EmploymentStatus.active)
    hire_date     = Column(Date, default=datetime.date.today)
    phone         = Column(String(20))

    # Relationships
    department    = relationship("Department", back_populates="employees")
    manager       = relationship("Employee", remote_side="Employee.id", backref="reports")
    salaries      = relationship("Salary", back_populates="employee")
    leave_records = relationship("LeaveRecord", back_populates="employee")
    projects      = relationship("ProjectAssignment", back_populates="employee")

    def __repr__(self):
        return f"Employee(id={self.id}, name='{self.name}', role='{self.role}')"


class Salary(Base):
    __tablename__ = "salaries"

    id          = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    amount      = Column(Float, nullable=False)
    currency    = Column(String(10), default="USD")
    effective   = Column(Date, nullable=False)   # date salary took effect
    notes       = Column(Text)

    # Relationships
    employee = relationship("Employee", back_populates="salaries")

    def __repr__(self):
        return f"Salary(employee_id={self.employee_id}, amount={self.amount}, effective='{self.effective}')"


class Project(Base):
    __tablename__ = "projects"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(150), nullable=False, index=True)
    description = Column(Text)
    start_date  = Column(Date)
    end_date    = Column(Date)
    status      = Column(String(50), default="active")   # active / completed / on_hold

    # Relationships
    assignments = relationship("ProjectAssignment", back_populates="project")

    def __repr__(self):
        return f"Project(id={self.id}, name='{self.name}', status='{self.status}')"


class ProjectAssignment(Base):
    """Many-to-many bridge between employees and projects."""
    __tablename__ = "project_assignments"

    id          = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    project_id  = Column(Integer, ForeignKey("projects.id"), nullable=False)
    role        = Column(String(100))   # e.g. Lead, Developer, QA
    joined_on   = Column(Date, default=datetime.date.today)

    # Relationships
    employee = relationship("Employee", back_populates="projects")
    project  = relationship("Project", back_populates="assignments")

    def __repr__(self):
        return f"ProjectAssignment(employee_id={self.employee_id}, project_id={self.project_id})"


class LeaveRecord(Base):
    __tablename__ = "leave_records"

    id          = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    leave_type  = Column(Enum(LeaveType), nullable=False)
    start_date  = Column(Date, nullable=False)
    end_date    = Column(Date, nullable=False)
    approved    = Column(String(10), default="pending")  # pending / approved / rejected
    reason      = Column(Text)

    # Relationships
    employee = relationship("Employee", back_populates="leave_records")

    def __repr__(self):
        return f"LeaveRecord(employee_id={self.employee_id}, type='{self.leave_type}', approved='{self.approved}')"


# =========================================
# CREATE ALL TABLES
# =========================================

Base.metadata.create_all(engine)
print("✅ Tables created successfully")
print("Tables:", Base.metadata.tables.keys())


# =========================================
# SEED DATA
# =========================================

def seed():
    db = Session()

    # Departments
    eng  = Department(name="Engineering",  location="Bangalore", budget=500000)
    hr   = Department(name="HR",           location="Mumbai",    budget=150000)
    mkt  = Department(name="Marketing",    location="Delhi",     budget=200000)
    fin  = Department(name="Finance",      location="Chennai",   budget=180000)
    db.add_all([eng, hr, mkt, fin])
    db.flush()

    # Employees
    alice = Employee(
        name="Alice Menon", email="alice@company.com",
        role="Engineering Manager", department_id=eng.id,
        status=EmploymentStatus.active,
        hire_date=datetime.date(2019, 3, 1), phone="9876543210"
    )
    bob = Employee(
        name="Bob Nair", email="bob@company.com",
        role="Senior Engineer", department_id=eng.id,
        status=EmploymentStatus.active,
        hire_date=datetime.date(2020, 6, 15), phone="9123456780"
    )
    carol = Employee(
        name="Carol Thomas", email="carol@company.com",
        role="HR Specialist", department_id=hr.id,
        status=EmploymentStatus.active,
        hire_date=datetime.date(2021, 1, 10), phone="9000011112"
    )
    dave = Employee(
        name="Dave Pillai", email="dave@company.com",
        role="Marketing Lead", department_id=mkt.id,
        status=EmploymentStatus.on_leave,
        hire_date=datetime.date(2018, 11, 20), phone="9111122223"
    )
    eve = Employee(
        name="Eve Krishnan", email="eve@company.com",
        role="Junior Engineer", department_id=eng.id,
        status=EmploymentStatus.active,
        hire_date=datetime.date(2023, 8, 1), phone="9222233334"
    )
    db.add_all([alice, bob, carol, dave, eve])
    db.flush()

    # Manager relationships
    bob.manager_id = alice.id
    eve.manager_id = alice.id

    # Salaries
    db.add_all([
        Salary(employee_id=alice.id, amount=120000, effective=datetime.date(2023, 1, 1)),
        Salary(employee_id=alice.id, amount=130000, effective=datetime.date(2024, 1, 1)),
        Salary(employee_id=bob.id,   amount=90000,  effective=datetime.date(2023, 1, 1)),
        Salary(employee_id=carol.id, amount=75000,  effective=datetime.date(2023, 6, 1)),
        Salary(employee_id=dave.id,  amount=85000,  effective=datetime.date(2022, 4, 1)),
        Salary(employee_id=eve.id,   amount=60000,  effective=datetime.date(2023, 8, 1)),
    ])

    # Projects
    p1 = Project(
        name="AI Platform",
        description="Internal ML inference platform",
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2024, 12, 31),
        status="active"
    )
    p2 = Project(
        name="Website Revamp",
        description="Company website redesign",
        start_date=datetime.date(2023, 6, 1),
        end_date=datetime.date(2023, 12, 31),
        status="completed"
    )
    db.add_all([p1, p2])
    db.flush()

    # Project Assignments
    db.add_all([
        ProjectAssignment(employee_id=alice.id, project_id=p1.id, role="Lead"),
        ProjectAssignment(employee_id=bob.id,   project_id=p1.id, role="Developer"),
        ProjectAssignment(employee_id=eve.id,   project_id=p1.id, role="Developer"),
        ProjectAssignment(employee_id=dave.id,  project_id=p2.id, role="Lead"),
        ProjectAssignment(employee_id=carol.id, project_id=p2.id, role="Coordinator"),
    ])

    # Leave Records
    db.add_all([
        LeaveRecord(
            employee_id=dave.id,
            leave_type=LeaveType.sick,
            start_date=datetime.date(2024, 5, 1),
            end_date=datetime.date(2024, 5, 10),
            approved="approved",
            reason="Fever"
        ),
        LeaveRecord(
            employee_id=eve.id,
            leave_type=LeaveType.casual,
            start_date=datetime.date(2024, 6, 20),
            end_date=datetime.date(2024, 6, 21),
            approved="approved",
            reason="Personal"
        ),
    ])

    db.commit()
    db.close()
    print("✅ Seed data inserted successfully")


if __name__ == "__main__":
    seed()