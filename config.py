import os
class Config:
    SECRET_KEY = os.getenv("SECRET_KEY","dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL","sqlite:///app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PIXEL_ID = os.getenv("PIXEL_ID","")
    ACCESS_TOKEN = os.getenv("ACCESS_TOKEN","")
    GRAPH_VER = os.getenv("GRAPH_VER","v20.0")
    BASE_URL = os.getenv("BASE_URL","")
    TEST_EVENT_CODE = os.getenv("TEST_EVENT_CODE","")
    RATE_LIMIT_QPS_PIXEL = float(os.getenv("RATE_LIMIT_QPS_PIXEL","10"))
    RATE_LIMIT_QPS_CAPI  = float(os.getenv("RATE_LIMIT_QPS_CAPI","5"))

    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True, 'pool_recycle': 280}
