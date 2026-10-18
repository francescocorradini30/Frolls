from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FROLLS_")

    app_name: str = "Frolls"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:5173"]
    database_url: str = "postgresql+asyncpg://frolls:frolls@localhost:5432/frolls_dev"
    chat_history_limit: int = 200
    # Tests open a new event loop per client, so pooled connections cannot be reused.
    db_null_pool: bool = False


settings = Settings()
