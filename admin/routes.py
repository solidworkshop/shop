import json, uuid, time, traceback, requests, random, threading
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_user, logout_user, login_required
from sqlalchemy import desc, func

from config import Config
from extensions import db
from models import User, KVStore, EventLog, Counters

admin_bp = Blueprint("admin", __name__, template_folder="templates")

# -------------------- Helpers --------------------
def _as_dict(x):
    if isinstance(x, dict): return x
    try: return dict(x)
    except Exception: return {}

def _sg(d, key, default=None):
    return d.get(key, default) if isinstance(d, dict) else default

def pixel_enabled(): return True
def capi_enabled(): return True

def get_auto_pixel(): return (KVStore.get("automation_pixel","1") == "1")
def get_auto_capi():  return (KVStore.get("automation_capi","1") == "1")
def use_test_code():  return (KVStore.get("use_test_event_code","1") == "1")

EVENT_NAMES = ["PageView","ViewContent","AddToCart","InitiateCheckout","AddPaymentInfo","Purchase"]

def chaos_drop(): return (KVStore.get("chaos_drop","0")=="1")
def chaos_omit(): return (KVStore.get("chaos_omit","0")=="1")
def chaos_malformed(): return (KVStore.get("chaos_malformed","0")=="1")

def pct_margin(): return int(KVStore.get("pct_profit_margin","100"))
def pct_pltv():   return int(KVStore.get("pct_pltv","100"))
def pltv_randomized(): return True
def pltv_min(): return 120.0
def pltv_max(): return 600.0
def margin_min(): return 0.10
def margin_max(): return 0.40

# -------------------- Rate limiting (stub) --------------------
class TokenBucket:
    def __init__(self, qps, burst=None):
        self.qps = float(qps or 1.0)
        self.capacity = burst or max(1, int(self.qps * 2))
        self.tokens = self.capacity
        self.updated = time.time()
        self.lock = threading.Lock()
    def take(self):
        with self.lock:
            now = time.time()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.qps)
            self.updated = now
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False

pixel_bucket = TokenBucket(float(getattr(Config, "RATE_LIMIT_QPS_PIXEL", 5)))
capi_bucket  = TokenBucket(float(getattr(Config, "RATE_LIMIT_QPS_CAPI", 5)))

# -------------------- Auth --------------------
@admin_bp.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username") or ""
        password = request.form.get("password") or ""
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            return redirect(url_for("admin.dashboard"))
        flash("Invalid credentials", "danger")
    return render_template("admin/login.html")

@admin_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("admin.login"))

# -------------------- Event Senders --------------------
def send_pixel(event):
    if not pixel_enabled() or chaos_drop(): return ("dropped", 0, None)
    try:
        start = time.time()
        time.sleep(0.003)
        latency = int((time.time() - start) * 1000)
        ev = EventLog(ts=datetime.utcnow(), channel="pixel",
                      event_name=_sg(event,"event_name","?"),
                      event_id=_sg(event,"event_id",str(uuid.uuid4())),
                      status="ok", latency_ms=latency,
                      payload=json.dumps(event))
        db.session.add(ev)
        c = Counters.get_or_create(); c.pixel += 1
        dup = EventLog.query.filter_by(event_id=ev.event_id, channel="capi").first()
        if dup: c.dedup += 1
        db.session.commit()
        return ("ok", latency, None)
    except Exception as e:
        return ("error", 0, str(e)[:300])

def send_capi(event, force_live=False):
    if not capi_enabled() or chaos_drop(): return ("dropped", 0, None)
    start = time.time()
    data = {"data":[{
        "event_name": _sg(event,"event_name","?"),
        "event_time": int(time.time()),
        "event_id": _sg(event,"event_id",str(uuid.uuid4())),
        "action_source": "website",
        "event_source_url": getattr(Config, "BASE_URL", "https://example.com"),
        "user_data": {"client_user_agent": "Mozilla/5.0"},
        "custom_data": {
            "currency": _sg(event,"currency","USD"),
            "value": float(_sg(event,"value",0) or 0),
            **({"profit_margin": _sg(event,"profit_margin")} if "profit_margin" in event else {}),
            **({"pltv": _sg(event,"pltv")} if "pltv" in event else {}),
        }
    }]}
    try:
        while not capi_bucket.take(): time.sleep(0.02)
        latency = int((time.time()-start)*1000)
        ev = EventLog(ts=datetime.utcnow(), channel="capi",
                      event_name=_sg(event,"event_name","?"),
                      event_id=_sg(event,"event_id",""),
                      status="ok", latency_ms=latency,
                      payload=json.dumps(data), error=None)
        db.session.add(ev)
        c = Counters.get_or_create(); c.capi += 1
        dup = EventLog.query.filter_by(event_id=ev.event_id, channel="pixel").first()
        if dup: c.dedup += 1
        db.session.commit()
        return ("ok", latency, None)
    except Exception as e:
        return ("error", 0, str(e)[:300])

# -------------------- UI --------------------
@admin_bp.route("/")
@login_required
def dashboard():
    KVStore.set("build_number","v1.3.3")
    c = Counters.get_or_create()
    build = KVStore.get("build_number","v1.3.3")
    recent = EventLog.query.order_by(desc(EventLog.ts)).limit(20).all()
    default_intervals = {"PageView":1.5,"ViewContent":2.0,"AddToCart":3.5,"InitiateCheckout":4.0,"AddPaymentInfo":5.0,"Purchase":6.0}
    user_intervals = {n: float(KVStore.get(f"interval_{n}", d)) for n,d in default_intervals.items()}
    chaos = {"drop": chaos_drop(), "omit": chaos_omit(), "malformed": chaos_malformed()}
    auto_pixel = get_auto_pixel(); auto_capi = get_auto_capi()
    return render_template("admin/dashboard.html",
        counters=c, build=build, recent=recent, events=EVENT_NAMES,
        intervals=user_intervals, chaos=chaos, auto_pixel=auto_pixel, auto_capi=auto_capi,
        pct_profit_margin=pct_margin(), pct_pltv=pct_pltv(), use_test_code=True)

# -------------------- Automation --------------------
AUTOMATION_THREADS = {}
AUTOMATION_STOP = threading.Event()

def _safe_float(v, default):
    try:
        return float(v)
    except Exception:
        try:
            return float(str(v).strip())
        except Exception:
            return float(default)

def automation_worker(app, event_name, interval_s):
    with app.app_context():
        while not AUTOMATION_STOP.is_set():
            payload = {"event_name": event_name, "event_id": str(uuid.uuid4()), "currency":"USD"}
            if event_name == "Purchase":
                price = _safe_float(random.uniform(20,200), 50)
                cost  = price * random.uniform(margin_min(), margin_max())
                payload["value"] = price
                if random.randint(1,100) <= pct_margin():
                    payload["profit_margin"] = round(max(0, price - cost), 2)
                if pltv_randomized() and (random.randint(1,100) <= pct_pltv()):
                    payload["pltv"] = round(random.uniform(pltv_min(), pltv_max()), 2)
            else:
                payload["value"] = 0.0
            if get_auto_pixel():
                try: send_pixel(payload)
                except Exception: pass
            if get_auto_capi():
                try: send_capi(payload)
                except Exception: pass
            time.sleep(max(0.25, _safe_float(interval_s, 1.0)))

@admin_bp.route("/api/automation", methods=["POST"])
@login_required
def api_automation():
    data = request.get_json(silent=True) or {}
    cmd = data.get("cmd")
    if cmd == "start":
        # parse intervals with fallbacks
        defaults = {"PageView":1.5,"ViewContent":2.0,"AddToCart":3.5,"InitiateCheckout":4.0,"AddPaymentInfo":4.5,"Purchase":6.0}
        intervals = {}
        for name, default in defaults.items():
            key = f"interval_{name}"
            intervals[name] = _safe_float(data.get("intervals",{}).get(key, KVStore.get(key, default)), default)
            KVStore.set(key, str(intervals[name]))
        if AUTOMATION_THREADS and not AUTOMATION_STOP.is_set():
            # already running — return OK with current state instead of 400
            return {"ok": True, "running": True, "threads": list(AUTOMATION_THREADS.keys()), "intervals": intervals}
        AUTOMATION_STOP.clear()
        app = current_app._get_current_object()
        for name, iv in intervals.items():
            t = threading.Thread(target=automation_worker, args=(app,name,iv), daemon=True)
            t.start(); AUTOMATION_THREADS[name]=t
        return {"ok": True, "running": True, "threads": list(AUTOMATION_THREADS.keys()), "intervals": intervals}
    elif cmd == "stop":
        AUTOMATION_STOP.set()
        for k,t in list(AUTOMATION_THREADS.items()):
            try: t.join(timeout=0.2)
            except Exception: pass
        AUTOMATION_THREADS.clear()
        return {"ok": True, "stopped": True}
    return {"ok": False, "error": "unknown cmd"}, 400

@admin_bp.route("/api/automation/ping", methods=["POST"])
@login_required
def api_automation_ping():
    # Do one immediate Purchase tick to prove the pipeline works
    payload = {"event_name":"Purchase", "event_id":str(uuid.uuid4()), "currency":"USD", "value":99.0, "profit_margin":10.0}
    send_pixel(payload); send_capi(payload)
    return {"ok":True}

# -------------------- Live status --------------------
@admin_bp.route("/api/counters")
@login_required
def api_counters():
    c = Counters.get_or_create()
    margin_events = db.session.query(func.count(EventLog.id)).filter(EventLog.payload.contains('"profit_margin"')).scalar() or 0
    pltv_events   = db.session.query(func.count(EventLog.id)).filter(EventLog.payload.contains('"pltv"')).scalar() or 0
    return {"ok": True, "pixel": c.pixel, "capi": c.capi, "dedup": c.dedup,
            "margin_events": int(margin_events), "pltv_events": int(pltv_events)}

# -------------------- Logs & Inspector (placeholders keep routes intact) --------------------
@admin_bp.route("/request-inspector")
@login_required
def request_inspector():
    logs = EventLog.query.order_by(desc(EventLog.ts)).limit(100).all()
    return render_template("admin/request_inspector.html", logs=logs)

@admin_bp.route("/logs")
@login_required
def logs_view():
    logs = EventLog.query.order_by(desc(EventLog.ts)).limit(500).all()
    return render_template("admin/logs.html", logs=logs)
