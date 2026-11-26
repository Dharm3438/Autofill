from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MONGODB_URI: str
    JWT_SECRET: str
    JWT_EXPIRE_HOURS: int = 24

    # Look up the email domain's mail servers at sign-up / email change, so a
    # typo like "gmail.con" is caught before a code is sent. Tests turn it off.
    EMAIL_DNS_CHECK: bool = True

    BREVO_API_KEY: str = ""
    FROM_EMAIL: str = ""
    FROM_NAME: str = "Solar Docs Platform"

    FRONTEND_URL: str = "http://localhost:5173"

    # How many X-Forwarded-For entries, counted from the right, were added after
    # the visitor's. The frontend's Cloudflare Pages Function sends XFF as just
    # the visitor's IP (from CF-Connecting-IP), then Render's side appends three:
    # the function's address (as Render's Cloudflare saw it), Render's
    # Cloudflare edge, and Render's internal load balancer. Seen in production:
    #   "223.233.85.74,2a06:98c0:3600::103, 172.69.86.98, 10.198.213.136"
    # Failed /api/auth requests log ip= and xff= so this can be re-checked.
    TRUSTED_PROXY_HOPS: int = 3

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

    # When true, the signing review page redirects each (non-merged) document to
    # a short-lived presigned R2 URL so the browser downloads it straight from R2
    # instead of streaming through the backend. Requires R2 bucket CORS to allow
    # the frontend origin (see backend/scripts/configure_r2_cors.py). Off by
    # default so the code can deploy before CORS is configured, then be flipped.
    R2_PRESIGNED_REVIEW: bool = False

    DOWNLOAD_WINDOW_DAYS: int = 3


settings = Settings()

if len(settings.JWT_SECRET) < 32:
    print(
        "WARNING: JWT_SECRET is shorter than 32 characters. Anyone who guesses it "
        "can forge logins. Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )
