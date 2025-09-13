
import os, sqlite3
from flask import Flask, render_template, request, make_response, session, redirect, url_for, jsonify
from flask_cors import CORS
from extensions import db, login_manager
from models import User, Product, KVStore

DB_PATH = "/var/tmp/app.db"

def ensure_sqlite_columns():
    # Adds missing columns for legacy DBs without dropping data
    engine = db.engine
    with engine.connect() as conn:
        def cols(table):
            rs = conn.exec_driver_sql(f"PRAGMA table_info({table})").mappings().all()
            return {r['name'] for r in rs}
        # user.pw_hash
        if engine.dialect.has_table(conn, "user"):
            c = cols("user")
            if "pw_hash" not in c:
                conn.exec_driver_sql("ALTER TABLE user ADD COLUMN pw_hash VARCHAR(255)")
        # product.*
        if engine.dialect.has_table(conn, "product"):
            c = cols("product")
            if "slug" not in c: conn.exec_driver_sql("ALTER TABLE product ADD COLUMN slug VARCHAR(128)")
            if "cost" not in c: conn.exec_driver_sql("ALTER TABLE product ADD COLUMN cost FLOAT DEFAULT 0")
            if "currency" not in c: conn.exec_driver_sql("ALTER TABLE product ADD COLUMN currency VARCHAR(8) DEFAULT 'USD'")
            if "description" not in c: conn.exec_driver_sql("ALTER TABLE product ADD COLUMN description TEXT")
            if "image_url" not in c: conn.exec_driver_sql("ALTER TABLE product ADD COLUMN image_url VARCHAR(500)")

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
        ensure_sqlite_columns()
        seed_admin()
        seed_products()

    from admin.routes import admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.route("/healthz")
    def healthz(): return "ok v2.6.1", 200

    @app.after_request
    def add_noindex(resp):
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        return resp

    # ----- Public store
    @app.route("/")
    def home():
        products = Product.query.all()
        return render_template("public/home.html", products=products, build="v2.6.1", pixel_id=os.getenv("PIXEL_ID",""))

    @app.route("/p/<slug>")
    def product_detail(slug):
        p = Product.query.filter_by(slug=slug).first_or_404()
        return render_template("public/product.html", p=p, build="v2.6.1", pixel_id=os.getenv("PIXEL_ID",""))

    @app.route("/cart/add/<int:pid>", methods=["POST"])
    def cart_add(pid):
        cart = session.get("cart", {}); cart[str(pid)] = cart.get(str(pid), 0) + 1; session["cart"] = cart
        return redirect(url_for("home"))

    @app.route("/checkout", methods=["GET","POST"])
    def checkout():
        if request.method == "POST":
            session["cart"] = {}
            return render_template("public/thanks.html", build="v2.6.1", pixel_id=os.getenv("PIXEL_ID",""))
        return render_template("public/checkout.html", build="v2.6.1", pixel_id=os.getenv("PIXEL_ID",""))

    @app.route("/about")
    def about(): return render_template("public/about.html", build="v2.6.1", pixel_id=os.getenv("PIXEL_ID",""))

    @app.route("/faq")
    def faq(): return render_template("public/faq.html", build="v2.6.1", pixel_id=os.getenv("PIXEL_ID",""))

    @app.route("/contact")
    def contact(): return render_template("public/contact.html", build="v2.6.1", pixel_id=os.getenv("PIXEL_ID",""))

    @app.route("/robots.txt")
    def robots():
        resp = make_response("User-agent: *\nDisallow: /\n", 200); resp.mimetype = "text/plain"; return resp

    # Diag endpoint to echo env and DB status (no secrets)
    @app.route("/diag")
    def diag():
        try:
            n_products = Product.query.count()
            n_events = db.session.execute(db.text("SELECT COUNT(*) AS c FROM event_log")).scalar() or 0
        except Exception as e:
            n_products = -1; n_events = -1
        payload = {
            "build":"v2.6.1",
            "env":{"PIXEL_ID": bool(os.getenv("PIXEL_ID")),"ACCESS_TOKEN":bool(os.getenv("ACCESS_TOKEN")),"GRAPH_VER": os.getenv("GRAPH_VER")},
            "db":{"path": DB_PATH, "products": n_products, "events": n_events}
        }
        return jsonify(payload)
    return app

def seed_admin():
    from models import User
    username = os.getenv("ADMIN_USERNAME","admin"); password = os.getenv("ADMIN_PASSWORD","admin123")
    u = User.query.filter_by(username=username).first()
    if not u:
        u = User(username=username); u.set_password(password); db.session.add(u); db.session.commit()
    elif not u.pw_hash:
        u.set_password(password); db.session.commit()

def seed_products():
    from models import Product
    if Product.query.count() == 0:
        items = [
            ("SKU-1","widget-alpha","Widget Alpha",19.99,8.50,"USD","<p>Lightweight, reliable widget.</p>","https://picsum.photos/seed/alpha/600/400"),
            ("SKU-2","widget-beta","Widget Beta",29.99,12.00,"USD","<p>Next-gen widget with extras.</p>","https://picsum.photos/seed/beta/600/400"),
            ("SKU-3","widget-gamma","Widget Gamma",24.99,10.00,"USD","<p>Popular mid-range widget.</p>","https://picsum.photos/seed/gamma/600/400"),
            ("SKU-4","widget-delta","Widget Delta",49.99,22.00,"USD","<p>Premium performance widget.</p>","https://picsum.photos/seed/delta/600/400"),
            ("SKU-5","widget-epsilon","Widget Epsilon",14.99,6.00,"USD","<p>Budget friendly widget.</p>","https://picsum.photos/seed/eps/600/400"),
            ("SKU-6","widget-zeta","Widget Zeta",34.99,15.00,"USD","<p>Compact and sturdy.</p>","https://picsum.photos/seed/zeta/600/400"),
            ("SKU-7","widget-eta","Widget Eta",54.99,24.00,"USD","<p>Professional-grade widget.</p>","https://picsum.photos/seed/eta/600/400"),
            ("SKU-8","widget-theta","Widget Theta",18.99,7.50,"USD","<p>Great for daily use.</p>","https://picsum.photos/seed/theta/600/400"),
            ("SKU-9","widget-iota","Widget Iota",22.50,9.50,"USD","<p>Balanced features.</p>","https://picsum.photos/seed/iota/600/400"),
            ("SKU-10","widget-kappa","Widget Kappa",31.00,13.00,"USD","<p>Robust and versatile.</p>","https://picsum.photos/seed/kappa/600/400"),
            ("SKU-11","widget-lambda","Widget Lambda",27.75,11.25,"USD","<p>Reliable everyday tool.</p>","https://picsum.photos/seed/lambda/600/400"),
            ("SKU-12","widget-mu","Widget Mu",42.00,18.00,"USD","<p>Advanced capabilities.</p>","https://picsum.photos/seed/mu/600/400"),
        ]
        for sku,slug,name,price,cost,curr,desc,img in items:
            db.session.add(Product(sku=sku,slug=slug,name=name,price=price,cost=cost,currency=curr,description=desc,image_url=img))
        db.session.commit()

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","5000")))
