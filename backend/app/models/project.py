from sqlalchemy import String,ForeignKey,UUID,Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column,Mapped,relationship

from datetime import datetime
import uuid

from app.database.database import Base


class Project(Base):
    __tablename__="projects"
    
    id:Mapped[UUID]=mapped_column(
        UUID(as_uuid=True),primary_key=True,
        default=uuid.uuid4
    )
    name:Mapped[str]=mapped_column(String(255),nullable=False)
    description:Mapped[str | None]=mapped_column(Text,nullable=True)
    owner_id:Mapped[UUID]=mapped_column(ForeignKey("users.id"),nullable=False)
    created_at:Mapped[datetime]=mapped_column(default=datetime.utcnow)
    updated_at:Mapped[datetime]=mapped_column(default=datetime.utcnow,onupdate=datetime.utcnow)
    owner:Mapped["User"]=relationship("User",back_populates="projects")


