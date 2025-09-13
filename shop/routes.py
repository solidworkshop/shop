from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, make_response
from datetime import datetime
import uuid, json
from extensions import db
from models import Product, EventLog, Counters

shop_bp = Blueprint("shop", __name__)

def cart_get(): return session.get("cart", {})
def cart_set(c): session["cart"] = c

@shop_bp.route("/")
def home():
    try:
        products = Product.query.order_by(Product.id.asc()).all()
    except Exception as e:
        products = []
    return render_template("shop/home.html", products=products)

@shop_bp.route("/product/<slug>")
def product_detail(slug):
    try:
        p = Product.query.filter_by(slug=slug).first()
    except Exception:
        p = None
    if not p:
        return render_template('shop/404.html'), 404
    return render_template("shop/product_detail.html", p=p)

@shop_bp.route("/cart")
def cart():
    cart = cart_get(); items=[]; total=0.0
    for pid,qty in cart.items():
        p = db.session.get(Product, int(pid))
        if not p: continue
        items.append((p,qty)); total += p.price*qty
    return render_template("shop/cart.html", items=items, total=total)

@shop_bp.route("/add-to-cart/<int:pid>", methods=["POST"])
def add_to_cart(pid):
    cart = cart_get(); cart[str(pid)] = cart.get(str(pid),0) + 1; cart_set(cart)
    return redirect(url_for("shop.cart"))

@shop_bp.route("/checkout", methods=["GET","POST"])
def checkout():
    cart = cart_get()
    if request.method=="POST":
        session["cart"] = {}
        return render_template("shop/thanks.html")
    items=[]; total=0.0
    for pid,qty in cart.items():
        p = db.session.get(Product, int(pid))
        if not p: continue
        items.append((p,qty)); total += p.price*qty
    return render_template("shop/checkout.html", items=items, total=total)

@shop_bp.route("/about")
def about(): return render_template("shop/about.html")

@shop_bp.route("/faq")
def faq(): return render_template("shop/faq.html")

@shop_bp.route("/contact")
def contact(): return render_template("shop/contact.html")

@shop_bp.route("/robots.txt")
def robots():
    resp = make_response("User-agent: *\nDisallow: /\n"); resp.headers["Content-Type"]="text/plain"; return resp

@shop_bp.route("/beacon", methods=["POST"])
def beacon():
    try:
        data = request.get_json(silent=True) or {}
        ev = EventLog(ts=datetime.utcnow(), channel="pixel",
                      event_name=data.get("event_name","?"),
                      event_id=data.get("event_id", str(uuid.uuid4())),
                      status="ok", latency_ms=0, payload=json.dumps(data))
        db.session.add(ev); c = Counters.get_or_create(); c.pixel += 1; db.session.commit()
        return jsonify({"ok":True})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}),500
