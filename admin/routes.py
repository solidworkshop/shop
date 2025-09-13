
import os, json, uuid, threading, time
from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_user, logout_user, login_required
from sqlalchemy import text
from extensions import db, login_manager
from models import User, Product, KVStore, EventLog
from utils.events import send_capi_event, get_pixel_id, get_test_event_code, STANDARD_EVENTS, should_attach_margin, should_attach_pltv, profit_margin

admin_bp = Blueprint("admin", __name__, template_folder="../templates/admin")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Auth
@admin_bp.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(username=request.form.get("username","")).first()
        if u and u.check_password(request.form.get("password","")):
            login_user(u, remember=True); return redirect(url_for("admin.dashboard"))
        return render_template("admin/login.html", error="Invalid credentials", username=request.form.get("username","")), 401
    return render_template("admin/login.html")

@admin_bp.route("/logout")
@login_required
def logout():
    logout_user(); return redirect(url_for("admin.login"))

def counters_snapshot():
    px = EventLog.query.filter_by(channel="pixel", status="ok").count()
    cp = EventLog.query.filter_by(channel="capi", status="ok").count()
    deduped = db.session.execute(text("""
        SELECT COUNT(*) AS c FROM (
          SELECT event_id FROM event_log WHERE channel='pixel' AND status='ok' GROUP BY event_id
          INTERSECT
          SELECT event_id FROM event_log WHERE channel='capi' AND status='ok' GROUP BY event_id
        ) sub
    """)).scalar() or 0
    with_margin = db.session.execute(text("SELECT COUNT(*) FROM event_log WHERE payload LIKE '%"profit_margin"%'" )).scalar() or 0
    with_pltv = db.session.execute(text("SELECT COUNT(*) FROM event_log WHERE payload LIKE '%"pltv"%'" )).scalar() or 0
    return {"pixel": px, "capi": cp, "deduped": int(deduped), "margin_events": int(with_margin), "pltv_events": int(with_pltv)}

# Dashboard
@admin_bp.route("/")
@login_required
def dashboard():
    cfg = {k: KVStore.get(k) for k in ["automation_interval","automation_concurrency","pixel_qps","capi_qps","pct_pltv","pct_margin","pltv_value","margin_min","margin_max","dry_run","enable_pixel","enable_capi"]}
    ev_toggles = {ev: (KVStore.get(f'on_{ev}','1')=='1') for ev in STANDARD_EVENTS}
    running = KVStore.get("automation_running","0") == "1"
    return render_template("admin/dashboard.html",
        cfg=cfg, ev_toggles=ev_toggles, running=running,
        counters=counters_snapshot(),
        pixel_id=get_pixel_id(), test_event_code=get_test_event_code(),
        standard_events=STANDARD_EVENTS, build="v2.6.0")

@admin_bp.route("/counters")
@login_required
def counters_api():
    d = counters_snapshot()
    d["running"] = KVStore.get("automation_running","0") == "1"
    return d

@admin_bp.route("/recent-events")
@login_required
def recent_events():
    rows = EventLog.query.order_by(EventLog.ts.desc()).limit(10).all()
    return {"items": [dict(ts=r.ts.isoformat(), channel=r.channel, event=r.event_name, id=r.event_id, status=r.status) for r in rows]}

# Settings
@admin_bp.route("/settings", methods=["POST"])
@login_required
def settings_save():
    data = request.get_json() or {}
    for k,v in data.items(): KVStore.set(str(k), str(v))
    return {"ok": True}

# Catalog
@admin_bp.route("/catalog")
@login_required
def admin_catalog():
    products = Product.query.order_by(Product.id.asc()).all()
    return render_template("admin/catalog.html", products=products, build="v2.6.0")

@admin_bp.route("/catalog/save", methods=["POST"])
@login_required
def admin_catalog_save():
    f = request.form; pid = f.get("id")
    p = Product.query.get(int(pid)) if pid else Product(); 
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

# Inspector & Logs
@admin_bp.route("/inspector")
@login_required
def inspector():
    last = EventLog.query.order_by(EventLog.ts.desc()).limit(100).all()
    return render_template("admin/inspector.html", rows=last, build="v2.6.0")

@admin_bp.route("/logs")
@login_required
def logs_view():
    last = EventLog.query.order_by(EventLog.ts.desc()).limit(500).all()
    return render_template("admin/logs.html", rows=last, build="v2.6.0")

# Health & Pixel check
@admin_bp.route("/pixel-check")
@login_required
def pixel_check():
    ok = bool(get_pixel_id())
    return {"ok": ok, "pixel": "ok" if ok else "missing"}, 200

# Manual send (separate from chaos)
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

# Automation engine
_threads = []; _stop = False

def _qps_ok(bucket, cap):
    import time
    now = time.time(); # sliding 1s window using list of timestamps in KVStore not necessary; per-thread memory ok
    while bucket and now - bucket[0] > 1.0: bucket.pop(0)
    if cap <= 0: return True
    if len(bucket) < cap: bucket.append(now); return True
    return False

def build_custom(ev):
    cd = {"currency":"USD"}
    if ev in ("ViewContent","AddToCart"): cd["value"] = 9.99
    if ev in ("InitiateCheckout",): cd["value"] = 14.99
    if ev in ("Purchase",): 
        price = 19.99; cd["value"] = price
        if should_attach_margin(): cd["profit_margin"] = profit_margin(price)
        if should_attach_pltv(): cd["pltv"] = float(KVStore.get("pltv_value","49.0") or 49.0)
    return cd

def worker(idx):
    import random, time, uuid, json as _json
    random.seed(12345+idx)
    pixel_on = KVStore.get("enable_pixel","1")=="1"
    capi_on  = KVStore.get("enable_capi","1")=="1"
    pixel_qps = int(KVStore.get("pixel_qps","5") or 5)
    capi_qps  = int(KVStore.get("capi_qps","5") or 5)
    interval  = max(1, int(KVStore.get("automation_interval","5") or 5))
    evs = [e for e in STANDARD_EVENTS if KVStore.get(f'on_{e}','1')=='1'] or ["PageView"]
    b_px=[]; b_ca=[]
    while KVStore.get("automation_running","0")=="1" and not _stop:
        ev = random.choice(evs); eid = str(uuid.uuid4()); cd = build_custom(ev)
        if pixel_on and _qps_ok(b_px, pixel_qps):
            db.session.add(EventLog(channel="pixel", event_name=ev, event_id=eid, status="ok", latency_ms=0, payload=_json.dumps(cd), error="")); db.session.commit()
        if capi_on and _qps_ok(b_ca, capi_qps):
            send_capi_event(ev, eid, cd, dry_run=(KVStore.get("dry_run","0")=="1"))
        time.sleep(interval)

@admin_bp.route("/automation/start", methods=["POST"])
@login_required
def automation_start():
    global _threads, _stop
    _stop = False
    KVStore.set("automation_running","1")
    n = max(1, min(10, int(KVStore.get("automation_concurrency","2") or 2)))
    _threads = []
    for i in range(n):
        t = threading.Thread(target=worker, args=(i,), daemon=True); t.start(); _threads.append(t)
    return {"ok": True, "threads": len(_threads)}

@admin_bp.route("/automation/stop", methods=["POST"])
@login_required
def automation_stop():
    global _stop; _stop = True; KVStore.set("automation_running","0"); return {"ok": True}

@admin_bp.route("/automation/status")
@login_required
def automation_status():
    running = KVStore.get("automation_running","0") == "1"
    return {"ok": True, "running": running}
