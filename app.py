from flask import Flask
from config import Config
from extensions import db, login_manager
from models import User, Product
from admin.routes import admin_bp
from shop.routes import shop_bp
import os, random, string

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
        if not User.query.first():
            u = User(username=os.getenv("ADMIN_USERNAME","admin"))
            u.set_password(os.getenv("ADMIN_PASSWORD","admin123"))
            db.session.add(u); db.session.commit()
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
