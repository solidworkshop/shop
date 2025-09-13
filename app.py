from flask import Flask
from config import Config
from extensions import db, login_manager
from models import User, Product
from admin.routes import admin_bp
from shop.routes import shop_bp
import os, random, string
from werkzeug.security import generate_password_hash

def ensure_schema(app):
    # Auto-migrate SQLite to add missing columns (e.g., user.pw_hash)
    from sqlalchemy import text
    with app.app_context():
        conn = db.engine.connect()
        # user.pw_hash
        info = conn.exec_driver_sql("PRAGMA table_info(user)").all()
        cols = {row[1] for row in info} if info else set()
        if "pw_hash" not in cols:
            conn.exec_driver_sql("ALTER TABLE user ADD COLUMN pw_hash VARCHAR(255)")
        # seed/update pw_hash if empty
        res = conn.exec_driver_sql("SELECT id, username, pw_hash FROM user").all()
        admin_pw = os.getenv("ADMIN_PASSWORD","admin123")
        for uid, uname, pwh in res:
            if pwh is None or pwh == "":
                hashed = generate_password_hash(admin_pw)
                conn.exec_driver_sql("UPDATE user SET pw_hash = :h WHERE id = :i", {"h": hashed, "i": uid})
        conn.close()

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)
    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(uid):
        from models import User
        return db.session.get(User, int(uid))

    with app.app_context():
        db.create_all()
        # ensure schema (adds pw_hash if missing, sets default hashes)
        ensure_schema(app)
        # seed admin if none exist
        if not User.query.first():
            u = User(username=os.getenv("ADMIN_USERNAME","admin"))
            u.set_password(os.getenv("ADMIN_PASSWORD","admin123"))
            db.session.add(u); db.session.commit()
        # seed products
        if Product.query.count()==0:
            for i in range(12):
                name=f"Demo Product {i+1}"; slug=f"demo-product-{i+1}"
                price=round(random.uniform(10,200),2)
                cost=round(price*random.uniform(0.5,0.9),2)
                p=Product(sku="SKU-"+''.join(random.choices(string.digits,k=6)), slug=slug, name=name,
                          price=price, cost=cost, currency="USD",
                          description="<p>Great demo item.</p>",
                          image_url=f"https://picsum.photos/seed/{i+10}/600/600")
                db.session.add(p)
            db.session.commit()

    app.register_blueprint(shop_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
