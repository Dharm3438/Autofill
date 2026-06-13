"""
Configure CORS on the R2 bucket for WI-4 (presigned signing-review documents).

When R2_PRESIGNED_REVIEW is on, the signing page's PDF viewer fetches documents
straight from presigned R2 URLs. That is a cross-origin request from the
frontend domain to *.r2.cloudflarestorage.com, so the bucket must send CORS
headers allowing the frontend origin — otherwise the browser blocks the
response and the viewer shows nothing.

Run this once (from the backend/ directory, venv active) BEFORE setting
R2_PRESIGNED_REVIEW=true:

    python scripts/configure_r2_cors.py            # apply the policy
    python scripts/configure_r2_cors.py --show     # print the current policy

It reads R2 credentials, bucket name, and FRONTEND_URL from your .env, so the
allowed origins always match the deployed frontend. Add a custom domain to
FRONTEND_URL (or extra_origins below) when you point one at the frontend.
"""
import sys
from pathlib import Path

# Make "app" importable when run as scripts/configure_r2_cors.py from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.services import storage       # noqa: E402


def allowed_origins() -> list[str]:
    origins = ["http://localhost:5173", "http://localhost:4173"]
    if settings.FRONTEND_URL and settings.FRONTEND_URL not in origins:
        origins.append(settings.FRONTEND_URL)
    return origins


def cors_configuration() -> dict:
    return {
        "CORSRules": [
            {
                "AllowedOrigins": allowed_origins(),
                # GET to fetch the PDF, HEAD for PDF.js range/size probes.
                "AllowedMethods": ["GET", "HEAD"],
                "AllowedHeaders": ["*"],
                # PDF.js reads these to do partial (range) loading.
                "ExposeHeaders": ["Content-Length", "Content-Range", "Accept-Ranges", "ETag"],
                "MaxAgeSeconds": 3600,
            }
        ]
    }


def main() -> int:
    client = storage._client()
    bucket = settings.R2_BUCKET_NAME

    if "--show" in sys.argv:
        try:
            cfg = client.get_bucket_cors(Bucket=bucket)
            print(cfg.get("CORSRules"))
        except Exception as e:
            print(f"No CORS set (or error reading it): {e}")
        return 0

    client.put_bucket_cors(Bucket=bucket, CORSConfiguration=cors_configuration())
    print(f"Applied CORS to bucket '{bucket}'.")
    print(f"Allowed origins: {allowed_origins()}")
    print("You can now set R2_PRESIGNED_REVIEW=true and redeploy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
