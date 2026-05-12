from sqlalchemy import create_engine,Column,Integer,String

from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base 

DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(DATABASE_URL)
session = sessionmaker(bind=engine)
Base = declarative_base()

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    role = Column(String, index=True)

    def __repr__(self):
        return f"Employee(id={self.id}, name='{self.name}', role='{self.role}')"

Base.metadata.create_all(engine)
print("Tables created successfully")