from sqlalchemy import String,ForeignKey,UUID,Text
from sqlalchemy.orm import mapped_column,Mapped,relationship

from datetime import datetime
import uuid

from app.database.database import Base
from app.models.enums import TaskPriority,TaskStatus

class Task(Base):
    __tablename__="tasks"

    id:Mapped[UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    project_id:Mapped[UUID]=mapped_column(ForeignKey("projects.id"),nullable=False)
    title:Mapped[str]=mapped_column(String(255),nullable=False)
    description:Mapped[str | None]=mapped_column(Text,nullable=True)
    status:Mapped[TaskStatus]=mapped_column(default=TaskStatus.PENDING,nullable=False)
    priority:Mapped[TaskPriority]=mapped_column(default=TaskPriority.MEDIUM,nullable=False)
    created_at:Mapped[datetime]=mapped_column(default=datetime.utcnow)
    updated_at:Mapped[datetime]=mapped_column(default=datetime.utcnow,onupdate=datetime.utcnow)
    project:Mapped["Project"]=relationship("Project",back_populates="tasks")
    

