from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CMDB Service"
    app_version: str = "1.0.0"
    database_url: str = "sqlite:///./cmdb.db"

    model_config = SettingsConfigDict(env_prefix="CMDB_", env_file=".env", extra="ignore")


settings = Settings()

