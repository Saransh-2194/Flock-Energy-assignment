from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    portal_base_url: str = "https://urja-ops.flockenergy.tech"
    portal_username: str = ""
    portal_password: str = ""
    portal_login_path: str = "/login"
    portal_username_field: str = "email"
    portal_password_field: str = "password"
    portal_timeout_seconds: float = 15.0

    # Credentials for people using this API/web console (separate from portal login).
    app_username: str = ""
    app_password: str = ""
    session_secret: str = ""
    session_cookie_secure: bool = False  # Set true when served over HTTPS.
    session_max_age_seconds: int = 8 * 60 * 60

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
