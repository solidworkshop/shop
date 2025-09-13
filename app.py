
import os, sys
from flask import Flask, jsonify, render_template
from flask_cors import CORS
from extensions import db, login_manager
from models import User, Product, KVStore

DB_PATH = "/var/tmp/app.db"

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    CORS(app)
    db.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        db.create_all()
        seed_admin()
        seed_products()

    from admin.routes import admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.route("/healthz")
    def healthz(): return "ok", 200

    @app.route("/")
    def index(): return render_template("public/home.html", build="v1.6.0")

    @app.route("/about")
    def about(): return render_template("public/about.html", build="v1.6.0")

    @app.route("/faq")
    def faq(): return render_template("public/faq.html", build="v1.6.0")

    @app.route("/contact")
    def contact(): return render_template("public/contact.html", build="v1.6.0")

    return app

def seed_admin():
    username = os.getenv("ADMIN_USERNAME","admin")
    password = os.getenv("ADMIN_PASSWORD","admin123")
    u = User.query.filter_by(username=username).first()
    if not u:
        u = User(username=username); u.set_password(password)
        db.session.add(u); db.session.commit()

def seed_products():
    if Product.query.count() == 0:
        items = [
            dict(sku="SKU-1", slug="widget-alpha", name="Widget Alpha", price=19.99, cost=8.50, currency="USD",
                 description="<p>Lightweight, reliable widget.</p>", image_url="https://picsum.photos/seed/alpha/600/400"),
            dict(sku="SKU-2", slug="widget-beta", name="Widget Beta", price=39.99, cost=16.00, currency="USD",
                 description="<p>Next-gen widget with extras.</p>", image_url="https://picsum.photos/seed/beta/600/400"),
        ]
        for it in items:
            p = Product(**it); db.session.add(p)
        db.session.commit()

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
