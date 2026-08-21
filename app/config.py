import os

from dotenv import load_dotenv

load_dotenv()


def normalize_database_url(raw_url):
    # Railway/Heroku hand out 'postgres://' or 'postgresql://'; SQLAlchemy's
    if raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql://", 1)
    if raw_url.startswith("postgresql://"):
        raw_url = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw_url


def running_in_production():
    return bool(os.environ.get("RAILWAY_ENVIRONMENT")) or os.environ.get(
        "DATABASE_URL", ""
    ).startswith(("postgres://", "postgresql://"))


def require_secret_key():
    secret_key = os.environ.get("SECRET_KEY")
    if secret_key:
        return secret_key
    # A known default key would let anyone forge login sessions in production.
    if running_in_production():
        raise RuntimeError("SECRET_KEY is not set. Refusing to start in production without one.")
    return "dev-secret-change-me"


class Config:
    SECRET_KEY = require_secret_key()

    # Login session cookie: HTTPS-only in production, out of reach of page
    # scripts, and not sent on cross-site requests.
    SESSION_COOKIE_SECURE = running_in_production()
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SQLALCHEMY_DATABASE_URI = normalize_database_url(
        os.environ.get("DATABASE_URL", "sqlite:///attendance.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        # Drop dead connections instead of failing a scan; recycle before the
        # platform's idle cutoff. Pool sized well above the gunicorn thread count.
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_size": int(os.environ.get("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "20")),
    }

    # When set, lecturer sign-up requires this code; unset leaves it open for dev.
    STAFF_SIGNUP_CODE = os.environ.get("STAFF_SIGNUP_CODE", "")

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

    # In-memory rate limits are per-replica; set this to a Redis URL once more
    # than one gunicorn instance runs so limits are shared across them.
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    # Attendance scan checks.
    SCAN_WINDOW_MINUTES = int(os.environ.get("SCAN_WINDOW_MINUTES", "120"))
    CLASSROOM_RADIUS_M = float(os.environ.get("CLASSROOM_RADIUS_M", "200"))
    GPS_ACCURACY_LIMIT_M = float(os.environ.get("GPS_ACCURACY_LIMIT_M", "50"))
