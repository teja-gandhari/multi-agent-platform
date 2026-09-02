from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends,HTTPException,status

from sqlalchemy.orm import Session

from app.repositories.user_repository import UserRepository
from app.database.session import get_db
from app.core.security import decode_token

oauth2_scheme= OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)

def get_current_user(token: str = Depends(oauth2_scheme),db: Session= Depends(get_db)):
    payload = decode_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    user_id=payload.get("sub")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    user_repository=UserRepository(db)

    user=user_repository.get_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user      



    
