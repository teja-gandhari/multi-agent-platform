from sqlalchemy.orm import Session

from app.repositories.user_repository import UserRepository
from app.core.security import hash_password
from app.models.user import User



class UserService:
    def __init__(self,db: Session):
        self.user_repository=UserRepository(db)

    def create_user(self,email: str,username: str,password: str):

        existing_user=self.user_repository.get_by_email(email)

        if existing_user:
            raise ValueError("Email already exists")

        hashed_password = hash_password(password)

        user =User(
            email=email,
            username=username,
            password_hash=hashed_password,
        )

        return self.user_repository.create(user)
    