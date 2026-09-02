from sqlalchemy.orm import Session

from app.core.security import (verify_password,create_access_token)
from app.repositories.user_repository import UserRepository

class AuthService:
    def __init__(self,db: Session):
        self.user_repository = UserRepository(db)

    def login(self,email: str, password: str):
        user=self.user_repository.get_by_email(email)

        if not user:
            raise ValueError("Invalid Credentials")

        if not verify_password(
            password,
            user.password_hash
        ):
            raise ValueError("Invalid Credentials")

        token = create_access_token(
            {
                "sub": str(user.id)
            }
        )
        return{
            "access_token":token,
            "token_type": "bearer"
        }
