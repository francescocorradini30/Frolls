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

    # --- Accounts -----------------------------------------------------------
    # Address of the app as the browser sees it: OAuth redirects come back here.
    public_url: str = "http://localhost:5173"
    # Development only: sign in with just a name (each browser tab its own user), and the
    # old hello with a self-declared player. Never enable in production.
    dev_login: bool = False
    session_days: int = 30
    # Send the session cookie only over HTTPS (production).
    cookie_secure: bool = False
    # OAuth apps (empty = that sign-in button is hidden).
    discord_client_id: str = ""
    discord_client_secret: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""


settings = Settings()
