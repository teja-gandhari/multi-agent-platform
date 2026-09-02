from passlib.context import CryptContext

from datetime import datetime,timedelta,timezone

from jose import jwt,JWTError

from app.core.config import settings

pwd_context=CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)
def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashes_password: str):
    return pwd_context.verify(
        plain_password,
        hashes_password
    )

def create_access_token(data : dict):
    is_encode=data.copy()

    expire=datetime.now(timezone.utc)+timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    is_encode.update(
        {
            "exp":expire
        }
    )

    token=jwt.encode(
        is_encode,
        settings.SECRET_KEY,
        algorithm="HS256"
    )

    return token

def decode_token(token: str):
    
    try:
        payload=jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms="HS256"
        )
        return payload
    
    except JWTError:
        return None
        
