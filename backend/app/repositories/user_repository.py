
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str) -> User | None:
        return (
            self.db.query(User)
            .filter(User.email == email)
            .first()
        )

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_by_id(self, user_id: UUID | str) -> User | None:
        try:
            parsed_id = UUID(str(user_id))
        except (ValueError, TypeError, AttributeError):
            return None

        return (
            self.db.query(User)
            .filter(User.id == parsed_id)
            .first()
        )
