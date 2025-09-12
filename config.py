import os

class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///store.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 7

    # Meta / CAPI
    PIXEL_ID = os.getenv("PIXEL_ID", "")
    ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "")
    GRAPH_VER = os.getenv("GRAPH_VER", "v20.0")
    TEST_EVENT_CODE = os.getenv("TEST_EVENT_CODE", "")
    BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000")

    # Admin
    ADMIN_USER = os.getenv("ADMIN_USER", "admin")
    ADMIN_PASS = os.getenv("ADMIN_PASS", "changeme")

    # Automation defaults
    AUTOMATION_MAX_CONCURRENCY = int(os.getenv("AUTOMATION_MAX_CONCURRENCY", "4"))
    RATE_LIMIT_QPS_PIXEL = float(os.getenv("RATE_LIMIT_QPS_PIXEL", "5"))
    RATE_LIMIT_QPS_CAPI = float(os.getenv("RATE_LIMIT_QPS_CAPI", "5"))
