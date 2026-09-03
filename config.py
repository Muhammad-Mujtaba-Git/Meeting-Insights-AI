from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GROQ_API_KEY: str
    HUGGINGFACEHUB_API_TOKEN : str
    LANGFUSE_SECRET_KEY: str
    LANGFUSE_PUBLIC_KEY: str
    
    
 
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    DATABASE_URL:str 
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"  
    )


settings = Settings()