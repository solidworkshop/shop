
import os, json
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db, login_manager
from models import User, Product, KVStore

app = current_app
admin_bp = Blueprint("admin", __name__, template_folder="../templates/admin")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@admin_bp.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","")
        password = request.form.get("password","")
        u = User.query.filter_by(username=username).first()
        if u and u.check_password(password):
            login_user(u, remember=True)
            return redirect(url_for("admin.dashboard"))
        return render_template("admin/login.html", error="Invalid credentials", username=username), 401
    return render_template("admin/login.html")

@admin_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("admin.login"))

@admin_bp.route("/")
@login_required
def dashboard():
    running = KVStore.get("automation_running","0") == "1"
    return render_template("admin/dashboard.html", running=running, build="v1.6.0")

# Automation JSON endpoints
@admin_bp.route("/automation/start", methods=["POST"])
@login_required
def automation_start():
    KVStore.set("automation_running","1")
    try: app.logger.info("automation start")
    except Exception: pass
    return {"ok": True}, 200

@admin_bp.route("/automation/stop", methods=["POST"])
@login_required
def automation_stop():
    KVStore.set("automation_running","0")
    try: app.logger.info("automation stop")
    except Exception: pass
    return {"ok": True}, 200

@admin_bp.route("/automation/status")
@login_required
def automation_status():
    running = KVStore.get("automation_running","0") == "1"
    return {"ok": True, "running": running}, 200

# Catalog management
@admin_bp.route("/catalog")
@login_required
def admin_catalog():
    products = Product.query.order_by(Product.id.asc()).all()
    return render_template("admin/catalog.html", products=products, build="v1.6.0")

@admin_bp.route("/catalog/save", methods=["POST"])
@login_required
def admin_catalog_save():
    f = request.form
    pid = f.get("id")
    p = Product.query.get(int(pid)) if pid else Product()
    if not pid: db.session.add(p)
    p.sku = f.get("sku") or p.sku
    p.slug = (f.get("slug") or p.slug or "").strip() or (f.get("name") or "product").lower().replace(" ","-")
    p.name = f.get("name") or p.name
    p.price = float(f.get("price") or (p.price or 0))
    p.cost = float(f.get("cost") or (p.cost or 0))
    p.currency = f.get("currency") or p.currency or "USD"
    p.description = f.get("description") or p.description
    p.image_url = f.get("image_url") or p.image_url
    db.session.commit()
    return redirect(url_for("admin.admin_catalog"))

# Health for admin blueprint
@admin_bp.route("/ping")
def admin_ping():
    return {"ok": True, "build": "v1.6.0"}, 200
