import logging, sys, time, traceback, os, random, string
from flask import Flask, jsonify, render_template
from sqlalchemy.exc import OperationalError
from config import Config
from extensions import db, login_manager
from models import User, Product, KVStore, EventLog
from admin.routes import admin_bp
from shop.routes import shop_bp
from werkzeug.security import generate_password_hash
from werkzeug.exceptions import HTTPException

def _retry(fn, attempts=5, delay=0.1):
    for i in range(attempts):
        try:
            return fn()
        except OperationalError as e:
            if "database is locked" in str(e):
                time.sleep(delay * (i + 1))
                continue
            raise
    return fn()

def _ensure_db_dir(uri: str):
    if uri.startswith("sqlite:////"):
        path = uri.replace("sqlite:////", "/")
        d = os.path.dirname(path)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)

def robust_sqlite_migration(app):
    # Use engine.begin() contexts only; no manual BEGIN/COMMIT.
    with app.app_context():
        # Set WAL mode and sane sync
        try:
            with db.engine.begin() as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL")
                conn.exec_driver_sql("PRAGMA synchronous=NORMAL")
        except Exception:
            pass

        # USER: add pw_hash column if missing and seed hashes if blank
        with db.engine.begin() as conn:
            try:
                info = conn.exec_driver_sql("PRAGMA table_info(user)").all()
                if info:
                    cols = {row[1] for row in info}
                    if "pw_hash" not in cols:
                        conn.exec_driver_sql("ALTER TABLE user ADD COLUMN pw_hash VARCHAR(255)")
            except Exception:
                pass
            try:
                res = conn.exec_driver_sql("SELECT id, pw_hash FROM user").all()
                for uid, pwh in res:
                    if pwh is None or pwh == "":
                        hashed = generate_password_hash(os.getenv("ADMIN_PASSWORD","admin123"))
                        conn.exec_driver_sql("UPDATE user SET pw_hash = :h WHERE id = :i", {"h": hashed, "i": uid})
            except Exception:
                pass

        # PRODUCT: rebuild table if any required column is missing
        required = ["id","sku","slug","name","price","cost","currency","description","image_url"]
        need_rebuild = False
        with db.engine.begin() as conn:
            try:
                pinfo = conn.exec_driver_sql("PRAGMA table_info(product)").all()
                if pinfo:
                    pcols = {row[1] for row in pinfo}
                    if any(col not in pcols for col in required):
                        need_rebuild = True
            except Exception:
                need_rebuild = False

        if need_rebuild:
            with db.engine.begin() as conn:
                conn.exec_driver_sql("ALTER TABLE product RENAME TO product_old")
                conn.exec_driver_sql("""                    CREATE TABLE product (
                        id INTEGER PRIMARY KEY,
                        sku VARCHAR(64) UNIQUE,
                        slug VARCHAR(128) UNIQUE,
                        name VARCHAR(200),
                        price FLOAT DEFAULT 0.0,
                        cost FLOAT DEFAULT 0.0,
                        currency VARCHAR(8) DEFAULT 'USD',
                        description TEXT,
                        image_url VARCHAR(512)
                    )
                """ )
                old_cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(product_old)").all()]
                parts = []
                for col in required:
                    if col in old_cols:
                        parts.append(col)
                    elif col=="slug":
                        parts.append("lower(replace(coalesce(name,'product'), ' ', '-')) AS slug")
                    elif col=="currency":
                        parts.append("'USD' AS currency")
                    elif col in ("price","cost"):
                        parts.append(f"0.0 AS {col}")
                    else:
                        parts.append(f"NULL AS {col}")
                sel_sql = "SELECT " + ", ".join(parts) + " FROM product_old"
                conn.exec_driver_sql("INSERT INTO product (id, sku, slug, name, price, cost, currency, description, image_url) " + sel_sql)
                conn.exec_driver_sql("DROP TABLE product_old")

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)
    # Ensure sqlite directory exists
    try:
        _ensure_db_dir(app.config.get("SQLALCHEMY_DATABASE_URI",""))
    except Exception:
        pass

    # Basic logging to stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    app.logger.setLevel(logging.INFO)
    if not any(isinstance(h, logging.StreamHandler) for h in app.logger.handlers):
        app.logger.addHandler(handler)

    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(uid):
        return db.session.get(User, int(uid))

    # Health & diagnostics
    @app.route("/healthz", methods=["GET", "HEAD"])
    def healthz():
        return "ok", 200

    @app.route("/health", methods=["GET", "HEAD"])
    def health():
        return "ok", 200

    @app.route("/_diag/env")
    def diag_env():
        keys = ["PIXEL_ID","ACCESS_TOKEN","GRAPH_VER","BASE_URL","TEST_EVENT_CODE","FLASK_ENV"]
        return jsonify({k: bool(os.getenv(k)) for k in keys})

    @app.route("/_diag/dburi")
    def diag_dburi():
        uri = app.config.get("SQLALCHEMY_DATABASE_URI","")
        return {"uri": uri}

    @app.route("/_diag/db")
    def diag_db():
        try:
            with db.engine.begin() as conn:
                mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
            return jsonify({"ok": True, "journal_mode": mode})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # Global error handlers

    @app.route("/_selftest")
    def selftest():
        info = {
            "python": sys.version,
            "cwd": os.getcwd(),
            "db_uri": app.config.get("SQLALCHEMY_DATABASE_URI",""),
            "env_present": {k: bool(os.getenv(k)) for k in ["PIXEL_ID","ACCESS_TOKEN","GRAPH_VER","BASE_URL","TEST_EVENT_CODE","SECRET_KEY"]},
            "routes": sorted([str(r) for r in app.url_map.iter_rules()])[:120],
        }
        # Try a trivial DB round-trip (read-only where possible)
        try:
            with db.engine.begin() as conn:
                mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
            info["sqlite_journal_mode"] = mode
            info["db_ok"] = True
        except Exception as e:
            info["db_ok"] = False
            info["db_error"] = str(e)
        return jsonify(info), 200

    @app.errorhandler(Exception)
    def on_any_exception(e):
        if isinstance(e, HTTPException):
            return e
        tb = ''.join(traceback.format_exception(None, e, e.__traceback__))
        try:
            ev = EventLog(channel="app", event_name="exception", status="500", latency_ms=0, payload="", error=tb[:4000])
            db.session.add(ev); db.session.commit()
        except Exception:
            pass
        return ("Internal Server Error", 500)

    @app.errorhandler(500)
    def on_500(e):
        tb = ''.join(traceback.format_exception(None, e, e.__traceback__))
        try:
            ev = EventLog(channel="app", event_name="error", status="500", latency_ms=0, payload="", error=tb[:4000])
            db.session.add(ev); db.session.commit()
        except Exception:
            pass
        try:
            return render_template("500.html", error=str(e)), 500
        except Exception:
            return "Internal Server Error", 500

    # DB boot
    with app.app_context():
        try:
            _retry(lambda: db.create_all())
            robust_sqlite_migration(app)
            _retry(lambda: db.create_all())
            if not User.query.first():
                u = User(username=os.getenv("ADMIN_USERNAME","admin"))
                u.set_password(os.getenv("ADMIN_PASSWORD","admin123"))
                db.session.add(u); _retry(lambda: db.session.commit())
            from sqlalchemy import text
            try:
                count = db.session.execute(text("SELECT COUNT(1) FROM product")).scalar_one()
            except Exception:
                count = 0
            if count == 0:
                for i in range(12):
                    name=f"Demo Product {i+1}"; slug=f"demo-product-{i+1}"
                    price=round(random.uniform(10,200),2)
                    cost=round(price*random.uniform(0.5,0.9),2)
                    p=Product(sku="SKU-"+''.join(random.choices(string.digits,k=6)), slug=slug, name=name,
                              price=price, cost=cost, currency="USD",
                              description="<p>Great demo item.</p>",
                              image_url=f"https://picsum.photos/seed/{i+10}/600/600")
                    db.session.add(p)
                _retry(lambda: db.session.commit())
        except Exception as boot_err:
            app.logger.exception("Boot error: %s", boot_err)
            try:
                KVStore.set("last_boot_error", str(boot_err))
            except Exception:
                pass

    app.register_blueprint(shop_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
