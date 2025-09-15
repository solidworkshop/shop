#!/usr/bin/env python3
import os, threading, time
from datetime import datetime
from flask import Flask, send_from_directory, Response, render_template
try:
    from flask_migrate import Migrate  # optional
except Exception:
    Migrate = lambda *a, **k: None  # no-op if not available
from dotenv import load_dotenv

from extensions import db, login_manager
from config import Config
from models import ensure_seed_admin, KVStore

# Blueprints
from shop.routes import shop_bp
from admin.routes import admin_bp

load_dotenv()

def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config())

    db.init_app(app)
    Migrate(app, db)  # safe even if it's the no-op

    login_manager.init_app(app)

    app.register_blueprint(shop_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.after_request
    def add_noindex(response):
        response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive, nosnippet'
        return response

    @app.route("/robots.txt")
    def robots():
        text = "User-agent: *\nDisallow: /\n"
        return Response(text, mimetype="text/plain")

    @app.route("/healthz")
    def healthz():
        return {"ok": True, "time": datetime.utcnow().isoformat()}

    with app.app_context():
        ensure_seed_admin()
        KVStore.set("build_number", os.getenv("BUILD_NUMBER", "v1.0.0"))
        KVStore.set("graph_version", os.getenv("GRAPH_VER", "v20.0"))

    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
