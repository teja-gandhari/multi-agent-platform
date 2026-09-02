from pydantic_settings import BaseSettings,SettingsConfigDict

class Settings(BaseSettings):

    APP_NAME: str

    DATABASE_URL:str

    SECRET_KEY:str

    ACCESS_TOKEN_EXPIRE_MINUTES:int

    REDIS_URL:str

    OPENAI_API_KEY:str


    model_config = SettingsConfigDict(
       env_file=".env",
       extra="ignore"
   )


settings=Settings()

