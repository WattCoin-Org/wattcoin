from flask import Flask
from .middleware.rate_limiter import app as rate_limiter_app

def create_app():
    app = Flask(__name__)
    app.register_blueprint(rate_limiter_app)
    return app
