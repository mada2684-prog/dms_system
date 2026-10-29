import os

class Config:
    SECRET_KEY = "change-this-secret"

    SQLALCHEMY_DATABASE_URI = "postgresql://postgres:password@localhost:5432/dms_cairo"
    SQLALCHEMY_TRACK_MODIFICATIONS = False