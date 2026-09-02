from sqlalchemy.orm import Session

from typing import Optional

from app.models.user import User



class UserRepository:

    def __init__(self,db: Session):
        self.db=db


    def get_by_email(self,email:str)->Optional[User]:
        return (
            self.db.query(User)
            .filter(
                User.email==email
            ).first()
        )
    
    def create(self,user: User):
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        return user

    def get_by_id(self,user_id: int):
        return (
            self.db.query(User).filter(
                User.id==user_id
            ).first()
        )

