import sqlite3
import random
from datetime import datetime, timedelta

# =========================================
# CONNECT DATABASE
# =========================================

conn = sqlite3.connect("test.db")
cursor = conn.cursor()

print("Connected to test.db")

# =========================================
# DROP OLD TABLES
# =========================================

cursor.executescript("""

DROP TABLE IF EXISTS project_assignments;
DROP TABLE IF EXISTS leave_records;
DROP TABLE IF EXISTS salaries;
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS departments;

""")

print("Old tables removed")

# =========================================
# CREATE TABLES
# =========================================

cursor.executescript("""

CREATE TABLE departments (
    id INTEGER PRIMARY KEY NOT NULL,
    name VARCHAR(100) NOT NULL,
    location VARCHAR(100),
    budget FLOAT
);

CREATE TABLE employees (
    id INTEGER PRIMARY KEY NOT NULL,
    name VARCHAR(100),
    role VARCHAR(100)
);

CREATE TABLE leave_records (
    id INTEGER PRIMARY KEY NOT NULL,
    employee_id INTEGER NOT NULL,
    leave_type VARCHAR(20) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    approved VARCHAR(20),
    reason TEXT
);

CREATE TABLE project_assignments (
    id INTEGER PRIMARY KEY NOT NULL,
    employee_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    role VARCHAR(100),
    joined_on DATE
);

CREATE TABLE projects (
    id INTEGER PRIMARY KEY NOT NULL,
    name VARCHAR(150) NOT NULL,
    description TEXT,
    start_date DATE,
    end_date DATE,
    status VARCHAR(50)
);

CREATE TABLE salaries (
    id INTEGER PRIMARY KEY NOT NULL,
    employee_id INTEGER NOT NULL,
    amount FLOAT NOT NULL,
    currency VARCHAR(10),
    effective DATE NOT NULL,
    notes TEXT
);

""")

print("Tables created successfully")

# =========================================
# SAMPLE DATA
# =========================================

departments = [
    ("Engineering", "Bangalore", 10000000),
    ("AI Research", "Hyderabad", 15000000),
    ("Human Resources", "Mumbai", 3000000),
    ("Finance", "Chennai", 5000000),
    ("Marketing", "Delhi", 4000000),
    ("Operations", "Pune", 3500000),
    ("Cloud Infrastructure", "Kochi", 9000000),
]

employee_names = [
    "Arjun Nair",
    "Sneha Pillai",
    "Rahul Menon",
    "Aisha Khan",
    "Kiran Das",
    "Meera Krishnan",
    "Vikram Rao",
    "Anjali Sharma",
    "Rohit Verma",
    "Priya Iyer",
    "Nikhil Joseph",
    "Sara Thomas",
    "Aditya Singh",
    "Neha Kapoor",
    "Aman Gupta",
    "Fathima Noor",
    "Rakesh Kumar",
    "Deepa Nair",
    "Varun Reddy",
    "Sanjay Pillai"
]

roles = [
    "Backend Developer",
    "Frontend Developer",
    "AI Engineer",
    "ML Engineer",
    "Data Scientist",
    "DevOps Engineer",
    "HR Manager",
    "Finance Analyst",
    "UI/UX Designer",
    "Cloud Engineer",
    "Product Manager"
]

projects = [
    ("AI Employee Assistant", "AI HR assistant platform"),
    ("Payroll Automation", "Payroll management system"),
    ("MCP Integration", "Enterprise MCP tools"),
    ("Analytics Dashboard", "Employee analytics"),
    ("Cloud Migration", "Infrastructure migration"),
    ("Recruitment AI", "Resume screening AI"),
    ("Internal Chatbot", "Company chatbot system")
]

leave_types = [
    "SICK",
    "VACATION",
    "CASUAL"
]

approval_status = [
    "Approved",
    "Pending",
    "Rejected"
]

# =========================================
# INSERT DEPARTMENTS
# =========================================

for idx, dept in enumerate(departments, start=1):

    cursor.execute("""
        INSERT INTO departments (
            id,
            name,
            location,
            budget
        )
        VALUES (?, ?, ?, ?)
    """, (
        idx,
        dept[0],
        dept[1],
        dept[2]
    ))

print("Departments inserted")

# =========================================
# INSERT EMPLOYEES
# =========================================

for idx, name in enumerate(employee_names, start=1):

    role = random.choice(roles)

    cursor.execute("""
        INSERT INTO employees (
            id,
            name,
            role
        )
        VALUES (?, ?, ?)
    """, (
        idx,
        name,
        role
    ))

print("Employees inserted")

# =========================================
# INSERT PROJECTS
# =========================================

for idx, project in enumerate(projects, start=1):

    start_date = datetime(2026, 1, 1) + timedelta(
        days=random.randint(1, 100)
    )

    end_date = start_date + timedelta(
        days=random.randint(60, 180)
    )

    status = random.choice([
        "Active",
        "Completed",
        "Planning"
    ])

    cursor.execute("""
        INSERT INTO projects (
            id,
            name,
            description,
            start_date,
            end_date,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        idx,
        project[0],
        project[1],
        start_date.date(),
        end_date.date(),
        status
    ))

print("Projects inserted")

# =========================================
# INSERT SALARIES
# =========================================

salary_id = 1

for employee_id in range(1, len(employee_names) + 1):

    amount = random.randint(400000, 2500000)

    cursor.execute("""
        INSERT INTO salaries (
            id,
            employee_id,
            amount,
            currency,
            effective,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        salary_id,
        employee_id,
        amount,
        "INR",
        "2026-01-01",
        "Annual package"
    ))

    salary_id += 1

print("Salaries inserted")

# =========================================
# INSERT LEAVE RECORDS
# =========================================

leave_id = 1

for _ in range(30):

    employee_id = random.randint(
        1,
        len(employee_names)
    )

    start_date = datetime(2026, 1, 1) + timedelta(
        days=random.randint(1, 200)
    )

    end_date = start_date + timedelta(
        days=random.randint(1, 7)
    )

    cursor.execute("""
        INSERT INTO leave_records (
            id,
            employee_id,
            leave_type,
            start_date,
            end_date,
            approved,
            reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        leave_id,
        employee_id,
        random.choice(leave_types),
        start_date.date(),
        end_date.date(),
        random.choice(approval_status),
        "Personal leave"
    ))

    leave_id += 1

print("Leave records inserted")

# =========================================
# INSERT PROJECT ASSIGNMENTS
# =========================================

assignment_id = 1

for _ in range(40):

    employee_id = random.randint(
        1,
        len(employee_names)
    )

    project_id = random.randint(
        1,
        len(projects)
    )

    joined_on = datetime(2026, 1, 1) + timedelta(
        days=random.randint(1, 100)
    )

    cursor.execute("""
        INSERT INTO project_assignments (
            id,
            employee_id,
            project_id,
            role,
            joined_on
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        assignment_id,
        employee_id,
        project_id,
        random.choice(roles),
        joined_on.date()
    ))

    assignment_id += 1

print("Project assignments inserted")

# =========================================
# SAVE CHANGES
# =========================================

conn.commit()

print("\n✅ Large dummy database created successfully!")
print("📂 Database Name: test.db")

# =========================================
# VERIFY DATA
# =========================================

tables = [
    "departments",
    "employees",
    "projects",
    "salaries",
    "leave_records",
    "project_assignments"
]

print("\n📊 TABLE ROW COUNTS")

for table in tables:

    cursor.execute(
        f"SELECT COUNT(*) FROM {table}"
    )

    count = cursor.fetchone()[0]

    print(f"{table}: {count} rows")

# =========================================
# CLOSE CONNECTION
# =========================================

conn.close()

print("\n✅ Database connection closed")