from __future__ import annotations

from flask import Flask, jsonify

from .agent import from_env

app = Flask(__name__)


@app.get("/")
def index():
    return jsonify(from_env().stats())


@app.get("/health")
def health():
    return jsonify({"status": "ok"})
