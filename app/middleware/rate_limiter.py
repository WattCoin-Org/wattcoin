import os
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["60 per minute"]
)

@app.before_request
def before_request_func():
    if request.endpoint in public_endpoints:
        limiter.limit("120 per minute")(request)
    else:
        limiter.limit(default_rate_limit)(request)

public_endpoints = [
    "api.public_endpoint_1",
    "api.public_endpoint_2"
]
default_rate_limit = os.getenv('RATE_LIMIT', '60 per minute')

@app.route("/api/public_endpoint_1", methods=["GET"])
def public_endpoint_1():
    return jsonify({"message": "Public endpoint 1"})

@app.route("/api/public_endpoint_2", methods=["POST"])
def public_endpoint_2():
    return jsonify({"message": "Public endpoint 2"})
