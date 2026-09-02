from fastapi import APIRouter,Depends
from fastapi.security import OAuth2PasswordRequestForm

from sqlalchemy.orm import Session

from app.schemas.user_schema import UserCreate,UserResponse
from app.database.session import get_db
from app.services.user_service import UserService
from app.schemas.auth_schema import LoginRequest,TokenRequest
from app.services.auth_service import AuthService
from app.core.dependencies import get_current_user
from app.models.user import User

auth_router=APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

@auth_router.post("/register",response_model=UserResponse)

def register(user_data: UserCreate ,db : Session = Depends(get_db)):

    service = UserService(db)
    return service.create_user(
        email=user_data.email,
        username=user_data.username,
        password=user_data.password
    )

@auth_router.post("/login",response_model=TokenRequest)
def login(user_login: OAuth2PasswordRequestForm = Depends(),db: Session =Depends(get_db)):
    service = AuthService(db)

    return service.login(
        email=user_login.username,
        password=user_login.password
    )

@auth_router.get("/me",response_model=UserResponse)
def get_profile(current_user: User = Depends(get_current_user)):
    return current_user
    

