
import os, json, uuid, threading, time, queue
import requests
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from flask_login import login_user, logout_user, login_required
from sqlalchemy import text
from extensions import db, login_manager
from models import User, Product, KVStore, EventLog
from utils.events import send_capi_event, graph_url, get_pixel_id, get_test_event_code, should_attach_margin, should_attach_pltv, profit_margin, STANDARD_EVENTS

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

# ---------------- Helpers ----------------
def kv_bool(k, default=False):
    v = KVStore.get(k, "1" if default else "0")
    return str(v) == "1"

def counters_snapshot():
    px = EventLog.query.filter_by(channel="pixel", status="ok").count()
    cp = EventLog.query.filter_by(channel="capi", status="ok").count()
    # deduped = count of distinct event_ids present on both channels
    deduped = db.session.execute(text("""
        SELECT COUNT(*) AS c FROM (
          SELECT event_id FROM event_log WHERE channel='pixel' AND status='ok' GROUP BY event_id
          INTERSECT
          SELECT event_id FROM event_log WHERE channel='capi' AND status='ok' GROUP BY event_id
        ) sub
    """)).scalar() or 0
    with_margin = db.session.execute(text("""
        SELECT COUNT(*) FROM event_log WHERE payload LIKE '%"profit_margin"%'
    """)).scalar() or 0
    with_pltv = db.session.execute(text("""
        SELECT COUNT(*) FROM event_log WHERE payload LIKE '%"pltv"%'
    """)).scalar() or 0
    return {"pixel": px, "capi": cp, "deduped": int(deduped), "margin_events": int(with_margin), "pltv_events": int(with_pltv)}

# ---------------- Dashboard ----------------
@admin_bp.route("/")
@login_required
def dashboard():
    cfg = {k: KVStore.get(k) for k in [
        "enable_pixel","enable_capi","automation_interval","automation_concurrency",
        "pixel_qps","capi_qps","pct_pltv","pct_margin","pltv_value",
        "margin_min","margin_max","dry_run"
    ]}
    ev_toggles = {ev: kv_bool(f"on_{ev}", True) for ev in STANDARD_EVENTS}
    running = kv_bool("automation_running", False)
    threads = int(KVStore.get("automation_threads","0") or 0)
    return render_template("admin/dashboard.html",
        cfg=cfg, ev_toggles=ev_toggles, running=running,
        counters=counters_snapshot(),
        pixel_id=get_pixel_id(), test_event_code=get_test_event_code(),
        build="v2.5.0", standard_events=STANDARD_EVENTS, threads=threads)

@admin_bp.route("/counters")
@login_required
def counters_api():
    d = counters_snapshot()
    d["running"] = kv_bool("automation_running", False)
    d["threads"] = int(KVStore.get("automation_threads","0") or 0)
    return d

# ---------------- Settings API ----------------
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
    return render_template("admin/catalog.html", products=products, build="v2.5.0")

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

# ---------------- Inspector & Logs ----------------
@admin_bp.route("/inspector")
@login_required
def inspector():
    last = EventLog.query.order_by(EventLog.ts.desc()).limit(100).all()
    return render_template("admin/inspector.html", rows=last, build="v2.5.0")

@admin_bp.route("/logs")
@login_required
def logs_view():
    last = EventLog.query.order_by(EventLog.ts.desc()).limit(500).all()
    return render_template("admin/logs.html", rows=last, build="v2.5.0")

# ---------------- Health & Pixel Check ----------------
@admin_bp.route("/pixel-check")
@login_required
def pixel_check():
    ok = bool(get_pixel_id())
    # quick network poke
    try:
        r = requests.get("https://graph.facebook.com/", timeout=4)
        net = f"http_{r.status_code}"
    except Exception as e:
        net = f"error:{e}"
    return {"ok": ok, "pixel": "ok" if ok else "missing", "network": net, "graph": graph_url("")}, 200

@admin_bp.route("/health")
@login_required
def admin_health():
    return {"ok": True, "build": "v2.5.0", "graph": graph_url("")}, 200

# ---------------- Manual send / Self-test ----------------
@admin_bp.route("/manual_send", methods=["POST"])
@login_required
def manual_send():
    try:
        data = request.get_json(force=True) or {}
        event_name = data.get("event_name","CustomEvent")
        event_id = data.get("event_id") or str(uuid.uuid4())
        custom_data = data.get("custom_data") or {}
        dry = bool(data.get("dry_run"))
        res = send_capi_event(event_name, event_id, custom_data, dry_run=dry)
        return {"ok": True, "result": res}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

# ---------------- Automation Engine ----------------
_threads = []
_stop_flag = False

def _qps_ok(channel, last_times, qps_cap):
    if qps_cap <= 0: return True
    now = time.time()
    # purge older than 1s
    while last_times and now - last_times[0] > 1.0:
        last_times.pop(0)
    if len(last_times) < qps_cap:
        last_times.append(now); return True
    return False

def build_custom_data(ev):
    cd = {"currency":"USD"}
    if ev in ("ViewContent","AddToCart"): cd["value"] = 9.99
    if ev in ("InitiateCheckout",): cd["value"] = 14.99
    if ev in ("Purchase",): 
        price = 19.99; cd["value"] = price
        if should_attach_margin(): cd["profit_margin"] = profit_margin(price)
        if should_attach_pltv(): cd["pltv"] = float(KVStore.get("pltv_value","49.0") or 49.0)
    return cd

def worker_loop(idx):
    global _stop_flag
    rnd_seed = int(KVStore.get("rnd_seed","12345") or 12345) + idx
    import random as _r; _r.seed(rnd_seed)
    pixel_on = kv_bool("enable_pixel", True)
    capi_on  = kv_bool("enable_capi", True)
    pixel_qps = int(KVStore.get("pixel_qps","5") or 5)
    capi_qps  = int(KVStore.get("capi_qps","5") or 5)
    interval  = max(1, int(KVStore.get("automation_interval","5") or 5))
    active_events = [e for e in STANDARD_EVENTS if kv_bool(f"on_{e}", True)]
    last_pixel = []; last_capi = []
    while not _stop_flag and kv_bool("automation_running", False):
        # choose an event
        ev = active_events[_r.randrange(len(active_events))] if active_events else "PageView"
        eid = str(uuid.uuid4())
        cd = build_custom_data(ev)
        # Pixel (simulated)
        if pixel_on and _qps_ok("pixel", last_pixel, pixel_qps):
            try:
                db.session.add(EventLog(channel="pixel", event_name=ev, event_id=eid, status="ok", latency_ms=0, payload=json.dumps(cd), error=""))
                db.session.commit()
            except Exception: pass
        # CAPI
        if capi_on and _qps_ok("capi", last_capi, capi_qps):
            send_capi_event(ev, eid, cd, dry_run=kv_bool("dry_run", False))
        # sleep
        time.sleep(interval)

@admin_bp.route("/automation/start", methods=["POST"])
@login_required
def automation_start():
    global _threads, _stop_flag
    _stop_flag = False
    KVStore.set("automation_running","1")
    n = max(1, min(10, int(KVStore.get("automation_concurrency","2") or 2)))
    _threads = []
    for i in range(n):
        t = threading.Thread(target=worker_loop, args=(i,), daemon=True)
        t.start(); _threads.append(t)
    KVStore.set("automation_threads", str(len(_threads)))
    return {"ok": True, "threads": len(_threads)}

@admin_bp.route("/automation/stop", methods=["POST"])
@login_required
def automation_stop():
    global _threads, _stop_flag
    KVStore.set("automation_running","0")
    _stop_flag = True
    KVStore.set("automation_threads","0")
    return {"ok": True}

@admin_bp.route("/automation/status")
@login_required
def automation_status():
    running = KVStore.get("automation_running","0") == "1"
    threads = int(KVStore.get("automation_threads","0") or 0)
    return {"ok": True, "running": running, "threads": threads}
