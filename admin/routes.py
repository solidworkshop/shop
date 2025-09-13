
import os, json, uuid, threading, time
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db, login_manager
from models import User, Product, KVStore, EventLog
from utils.events import send_capi_event, graph_url, get_pixel_id, get_test_event_code

app = current_app
admin_bp = Blueprint("admin", __name__, template_folder="../templates/admin")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------------- Auth ----------------
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

# ---------------- Dashboard ----------------
@admin_bp.route("/")
@login_required
def dashboard():
    running = KVStore.get("automation_running","0") == "1"
    counters = counters_snapshot()
    return render_template("admin/dashboard.html",
                           running=running,
                           counters=counters,
                           pixel_id=get_pixel_id(),
                           test_event_code=get_test_event_code(),
                           build="v2.0.0")

def counters_snapshot():
    # counts by channel
    px = EventLog.query.filter_by(channel="pixel", status="ok").count()
    cp = EventLog.query.filter_by(channel="capi", status="ok").count()
    dd = EventLog.query.filter_by(status="deduped").count()
    # number of events (not sums) with margin or pltv
    with_margin = EventLog.query.filter(EventLog.payload.contains('"profit_margin"')).count()
    with_pltv = EventLog.query.filter(EventLog.payload.contains('"pltv"')).count()
    return {"pixel": px, "capi": cp, "deduped": dd, "margin_events": with_margin, "pltv_events": with_pltv}

@admin_bp.route("/counters")
@login_required
def counters_api():
    return counters_snapshot()

# ---------------- Automation ----------------
automation_thread = None
automation_stop_flag = False

def automation_runner():
    global automation_stop_flag
    # simple loop emitting pageview/ purchase mixes with configurable intervals
    while not automation_stop_flag:
        if KVStore.get("automation_running","0") != "1":
            break
        try:
            # choose event
            event = "PageView" if int(time.time()) % 3 else "Purchase"
            eid = str(uuid.uuid4())
            custom = {"currency": "USD"}
            if event == "Purchase":
                price = 19.99
                if should_attach_margin(): custom["profit_margin"] = profit_margin(price)
                if should_attach_pltv(): custom["pltv"] = float(KVStore.get("pltv_value","49.0"))
                custom["value"] = price
            # log pixel ok (simulated; real pixel comes from browser)
            db.session.add(EventLog(channel="pixel", event_name=event, event_id=eid, status="ok", latency_ms=0, payload=json.dumps(custom), error=""))
            db.session.commit()
            # send capi
            send_capi_event(event, eid, custom)
        except Exception as e:
            try:
                db.session.add(EventLog(channel="app", event_name="automation_error", status="500", latency_ms=0, payload="", error=str(e)))
                db.session.commit()
            except Exception:
                pass
        time.sleep(max(1, int(KVStore.get("automation_interval","5"))))

from utils.events import should_attach_margin, should_attach_pltv, profit_margin

@admin_bp.route("/automation/start", methods=["POST"])
@login_required
def automation_start():
    global automation_thread, automation_stop_flag
    KVStore.set("automation_running","1")
    if not automation_thread or not automation_thread.is_alive():
        automation_stop_flag = False
        automation_thread = threading.Thread(target=automation_runner, daemon=True)
        automation_thread.start()
    return {"ok": True}

@admin_bp.route("/automation/stop", methods=["POST"])
@login_required
def automation_stop():
    global automation_stop_flag
    KVStore.set("automation_running","0")
    automation_stop_flag = True
    return {"ok": True}

@admin_bp.route("/automation/status")
@login_required
def automation_status():
    running = KVStore.get("automation_running","0") == "1"
    return {"ok": True, "running": running}

# ---------------- Pixel check & Health ----------------
@admin_bp.route("/pixel-check")
@login_required
def pixel_check():
    # basic check: pixel id present and graph reachable
    ok = bool(get_pixel_id())
    return {"ok": ok, "pixel": "ok" if ok else "missing", "capi": "ok"}, 200

@admin_bp.route("/health")
@login_required
def admin_health():
    # include build, graph version url, simple reachability
    return {"ok": True, "build": "v2.0.0", "graph": graph_url("")}, 200

# ---------------- Request inspector & Logs ----------------
@admin_bp.route("/inspector")
@login_required
def inspector():
    last = EventLog.query.order_by(EventLog.ts.desc()).limit(50).all()
    return render_template("admin/inspector.html", rows=last)

@admin_bp.route("/logs")
@login_required
def logs_view():
    last = EventLog.query.order_by(EventLog.ts.desc()).limit(200).all()
    return render_template("admin/logs.html", rows=last)

# ---------------- Settings (percentages etc.) ----------------
@admin_bp.route("/settings", methods=["POST"])
@login_required
def settings_save():
    data = request.get_json() or {}
    for k,v in data.items():
        KVStore.set(str(k), str(v))
    return {"ok": True}

# ---------------- Catalog ----------------
@admin_bp.route("/catalog")
@login_required
def admin_catalog():
    products = Product.query.order_by(Product.id.asc()).all()
    return render_template("admin/catalog.html", products=products, build="v2.0.0")

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

# ---------------- Manual send (raw JSON) ----------------
@admin_bp.route("/manual_send", methods=["POST"])
@login_required
def manual_send():
    try:
        data = request.get_json(force=True)
        event_name = data.get("event_name","CustomEvent")
        event_id = data.get("event_id") or str(uuid.uuid4())
        custom_data = data.get("custom_data") or {}
        res = send_capi_event(event_name, event_id, custom_data)
        return {"ok": True, "result": res}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

# ---------------- Simple API: last N payloads ----------------
@admin_bp.route("/inspector/last")
@login_required
def inspector_last():
    n = int(request.args.get("n","20"))
    rows = EventLog.query.order_by(EventLog.ts.desc()).limit(n).all()
    return jsonify([{"ts": r.ts.isoformat(), "channel": r.channel, "event": r.event_name, "id": r.event_id, "status": r.status, "latency": r.latency_ms, "error": r.error} for r in rows])
