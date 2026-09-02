from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship,Mapped,mapped_column

from datetime import datetime
import uuid


from app.database.database import Base



class User(Base):
    __tablename__="users"

    id:Mapped[UUID] = mapped_column(UUID(as_uuid=True),default=uuid.uuid4,primary_key=True)
    email:Mapped[str] = mapped_column(String(255),index=True,nullable=False,unique=True)
    username:Mapped[str] = mapped_column(String(50),nullable=False,unique=True)
    password_hash:Mapped[str]=mapped_column(String(255),nullable=False)
    is_active:Mapped[bool]=mapped_column(default=True)
    created_at:Mapped[datetime]=mapped_column(default=datetime.utcnow)
    updated_at:Mapped[datetime]=mapped_column(default=datetime.utcnow,onupdate=datetime.utcnow)
    projects: Mapped[list["Project"]]=relationship("Project",back_populates="owner")
    



