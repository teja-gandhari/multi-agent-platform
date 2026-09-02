from uuid import UUID

from pydantic import BaseModel,EmailStr


class UserCreate(BaseModel):

    email:EmailStr
    username:str
    password:str

class UserResponse(BaseModel):

    id:UUID
    email:EmailStr
    username:str
    is_active:bool

    model_config={
        'from_attributes': True
    }
