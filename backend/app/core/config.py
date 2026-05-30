from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MONGODB_URI: str
    JWT_SECRET: str
    JWT_EXPIRE_HOURS: int = 24

    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = "onboarding@resend.dev"
    FROM_NAME: str = "Solar Docs Platform"

    FRONTEND_URL: str = "http://localhost:5173"

    @property
    def allowed_origins(self) -> list[str]:
        origins = ["http://localhost:5173", "http://localhost:4173"]
        if self.FRONTEND_URL not in origins:
            origins.append(self.FRONTEND_URL)
        return origins

    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = "solar-docs"
    R2_PUBLIC_URL: str = ""

    DOWNLOAD_WINDOW_DAYS: int = 3


settings = Settings()
