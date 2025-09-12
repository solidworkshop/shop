import math, random, uuid, time, json
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from sqlalchemy import func
from config import Config
from extensions import db
from models import Product, Counters, KVStore, EventLog

shop_bp = Blueprint("shop", __name__)

def fmt_currency(value, currency="USD", locale="en_US"):
    return f"{currency} {value:,.2f}"

def ensure_seed_products():
    if Product.query.count() == 0:
        import random as _r
        for i in range(1, 12+1):
            p = Product(
                sku=f"SKU{i:03d}",
                name=f"Product {i}",
                description="A demo product for the store simulator.",
                price=round(_r.uniform(10, 99), 2),
                currency="USD",
                image_url="https://picsum.photos/seed/{}/600/400".format(i),
            )
            db.session.add(p)
        db.session.commit()

@shop_bp.before_app_request
def _seed():
    ensure_seed_products()
    Counters.get_or_create()

@shop_bp.route("/")
def home():
    products = Product.query.all()
    return render_template("shop/home.html", products=products, cfg=Config)

@shop_bp.route("/product/<sku>")
def product_detail(sku):
    p = Product.query.filter_by(sku=sku).first_or_404()
    return render_template("shop/product.html", p=p, cfg=Config)

@shop_bp.route("/cart")
def cart():
    cart = session.get("cart", {})
    items, total = [], 0.0
    for sku, qty in cart.items():
        prod = Product.query.filter_by(sku=sku).first()
        if prod:
            items.append((prod, qty))
            total += prod.price * qty
    return render_template("shop/cart.html", items=items, total=total, fmt=fmt_currency, cfg=Config)

@shop_bp.route("/add_to_cart/<sku>")
def add_to_cart(sku):
    cart = session.get("cart", {})
    cart[sku] = cart.get(sku, 0) + 1
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("shop.cart"))

@shop_bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart = session.get("cart", {})
    items, total = [], 0.0
    for sku, qty in cart.items():
        prod = Product.query.filter_by(sku=sku).first()
        if prod:
            items.append((prod, qty))
            total += prod.price * qty

    if request.method == "POST":
        session["cart"] = {}
        session.modified = True
        return redirect(url_for("shop.thankyou"))
    return render_template("shop/checkout.html", items=items, total=total, fmt=fmt_currency, cfg=Config)

@shop_bp.route("/thank-you")
def thankyou():
    return render_template("shop/thankyou.html", cfg=Config)

@shop_bp.route("/about")
def about():
    return render_template("shop/about.html", cfg=Config)

@shop_bp.route("/faq")
def faq():
    return render_template("shop/faq.html", cfg=Config)

@shop_bp.route("/contact")
def contact():
    return render_template("shop/contact.html", cfg=Config)

# -------- Pixel beacon collector (client JS sends navigator.sendBeacon/fetch) --------
@shop_bp.route("/pixel-collect", methods=["POST"])
def pixel_collect():
    try:
        start = time.time()
        payload = request.get_json(force=True, silent=True) or {}
        eid = payload.get("event_id") or str(uuid.uuid4())
        event_name = payload.get("event_name","PageView")
        latency = int((time.time()-start)*1000)
        ev = EventLog(ts=datetime.utcnow(), channel="pixel", event_name=event_name,
                      event_id=eid, status="beacon", latency_ms=latency, payload=json.dumps(payload))
        db.session.add(ev)
        c = Counters.get_or_create()
        c.pixel += 1
        # dedup check
        from models import EventLog as EL
        dup = EL.query.filter_by(event_id=eid, channel="capi").first()
        if dup:
            c.dedup += 1
        db.session.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:200]}), 400
