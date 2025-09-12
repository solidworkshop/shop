import os, json, time, threading, random, uuid, queue, requests
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required
from sqlalchemy import desc
from config import Config
from extensions import db
from models import User, KVStore, EventLog, Counters, Product

admin_bp = Blueprint("admin", __name__, template_folder="templates")

# -------------------- Auth --------------------
@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            return redirect(url_for("admin.dashboard"))
        flash("Invalid credentials", "danger")
    return render_template("admin/login.html")

@admin_bp.route("/logout")
@login_required
def logout():
    from flask_login import logout_user as _logout
    _logout_user = _logout
    _logout_user()
    return redirect(url_for("admin.login"))

# -------------------- Helpers --------------------
def _get_bool(key, default=False):
    return (KVStore.get(key, "1" if default else "0") == "1")

def _set_bool(key, value: bool):
    KVStore.set(key, "1" if value else "0")

def pixel_enabled(): return _get_bool("pixel_enabled", True)
def capi_enabled(): return _get_bool("capi_enabled", True)

EVENT_NAMES = [
    "PageView","ViewContent","AddToCart","InitiateCheckout",
    "AddPaymentInfo","Purchase","Contact","Search","CompleteRegistration"
]

# per-event toggles default True
def event_enabled(name): return _get_bool(f"ev_{name}", True)

# chaos toggles
def chaos_drop(): return _get_bool("chaos_drop", False)
def chaos_omit(): return _get_bool("chaos_omit", False)
def chaos_malformed(): return _get_bool("chaos_malformed", False)

# margin/PLTV config
def margin_min(): return float(KVStore.get("margin_min","0.10"))
def margin_max(): return float(KVStore.get("margin_max","0.40"))
def pltv_min(): return float(KVStore.get("pltv_min","120"))
def pltv_max(): return float(KVStore.get("pltv_max","600"))
def pltv_randomized(): return _get_bool("pltv_randomized", True)

# Automation state
AUTOMATION_THREADS = {}
AUTOMATION_STOP = threading.Event()

# Token-bucket rate limiters per channel
class TokenBucket:
    def __init__(self, qps, burst=None):
        self.qps = qps
        self.capacity = burst or max(1, int(qps*2))
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

pixel_bucket = TokenBucket(float(Config.RATE_LIMIT_QPS_PIXEL))
capi_bucket  = TokenBucket(float(Config.RATE_LIMIT_QPS_CAPI))

def make_event(event_name, value=0.0, currency="USD"):
    eid = str(uuid.uuid4())
    payload = {"event_name": event_name, "event_id": eid, "currency": currency, "value": value}
    if chaos_omit():
        payload.pop("currency", None)
    if chaos_malformed():
        payload["value"] = "NaN"
    return payload

def send_pixel(event, status_override=None):
    if not pixel_enabled() or chaos_drop():
        return ("dropped", 0, None)
    start = time.time()
    time.sleep(0.005)
    latency = int((time.time()-start)*1000)
    status = status_override or "ok"
    ev = EventLog(ts=datetime.utcnow(), channel="pixel", event_name=event.get("event_name","?"),
                  event_id=event.get("event_id","?"), status=status, latency_ms=latency, payload=json.dumps(event))
    db.session.add(ev)
    c = Counters.get_or_create()
    c.pixel += 1
    # dedup heuristic: if same event_id also seen in capi
    dup = EventLog.query.filter_by(event_id=event.get("event_id","?"), channel="capi").first()
    if dup:
        c.dedup += 1
    db.session.commit()
    return (status, latency, None)

def send_capi(event):
    if not capi_enabled() or chaos_drop():
        return ("dropped", 0, None)
    url = f"https://graph.facebook.com/{Config.GRAPH_VER}/{Config.PIXEL_ID}/events"
    data = {
        "data": [{
            "event_name": event.get("event_name","?"),
            "event_time": int(time.time()),
            "event_id": event.get("event_id"),
            "custom_data": {"currency": event.get("currency","USD"), "value": event.get("value",0)},
            "action_source": "website"
        }]
    }
    if Config.TEST_EVENT_CODE:
        data["test_event_code"] = Config.TEST_EVENT_CODE
    start = time.time()
    err = None
    status = "ok"
    try:
        # Respect rate limit
        while not capi_bucket.take():
            time.sleep(0.02)
        # Make real call only if creds exist; otherwise dry-run
        if Config.PIXEL_ID and Config.ACCESS_TOKEN:
            resp = requests.post(url, params={"access_token": Config.ACCESS_TOKEN}, json=data, timeout=6)
            ok = 200 <= resp.status_code < 300
            status = "ok" if ok else f"http_{resp.status_code}"
            if not ok:
                err = resp.text[:1000]
        else:
            status = "dry_run"
    except Exception as e:
        status = "error"
        err = str(e)[:1000]
    latency = int((time.time()-start)*1000)
    ev = EventLog(ts=datetime.utcnow(), channel="capi", event_name=event.get("event_name","?"),
                  event_id=event.get("event_id","?"), status=status, latency_ms=latency,
                  payload=json.dumps(data), error=err)
    db.session.add(ev)
    c = Counters.get_or_create()
    c.capi += 1 if status in ("ok","dry_run") else 0
    dup = EventLog.query.filter_by(event_id=event.get("event_id","?"), channel="pixel").first()
    if dup:
        c.dedup += 1
    db.session.commit()
    return (status, latency, err)

# -------------------- Dashboard --------------------
@admin_bp.route("/")
@login_required
def dashboard():
    c = Counters.get_or_create()
    build = KVStore.get("build_number","v1.0.0")
    graph = KVStore.get("graph_version","v20.0")
    pixel = "ON" if pixel_enabled() else "OFF"
    capi = "ON" if capi_enabled() else "OFF"
    recent = EventLog.query.order_by(desc(EventLog.ts)).limit(20).all()
    seed = KVStore.get("rng_seed","")
    # default intervals
    default_intervals = {"PageView":1.5,"ViewContent":2.0,"AddToCart":3.5,"Purchase":6.0}
    user_intervals = {}
    for name, d in default_intervals.items():
        user_intervals[name] = float(KVStore.get(f"interval_{name}", d))
    chaos = {
        "drop": chaos_drop(),
        "omit": chaos_omit(),
        "malformed": chaos_malformed()
    }
    return render_template("admin/dashboard.html", counters=c, build=build, graph=graph,
                           pixel=pixel, capi=capi, recent=recent, events=EVENT_NAMES,
                           seed=seed, intervals=user_intervals, chaos=chaos)

# -------------------- Toggles & Settings APIs --------------------
@admin_bp.route("/api/toggle", methods=["POST"])
@login_required
def api_toggle():
    data = request.json or {}
    key = data.get("key")
    val = data.get("value", True)
    if key is None: return {"ok": False, "error":"missing key"}, 400
    KVStore.set(key, "1" if val else "0")
    return {"ok": True}

@admin_bp.route("/api/settings", methods=["GET","POST"])
@login_required
def api_settings():
    if request.method == "POST":
        data = request.json or {}
        for k,v in data.items():
            KVStore.set(k, str(v))
        return {"ok": True}
    # GET
    out = { "pixel_enabled": pixel_enabled(), "capi_enabled": capi_enabled() }
    for name in EVENT_NAMES:
        out[f"ev_{name}"] = event_enabled(name)
    out.update({
        "margin_min": margin_min(), "margin_max": margin_max(),
        "pltv_min": pltv_min(), "pltv_max": pltv_max(),
        "pltv_randomized": pltv_randomized(),
        "chaos_drop": chaos_drop(),
        "chaos_omit": chaos_omit(),
        "chaos_malformed": chaos_malformed(),
        "rng_seed": KVStore.get("rng_seed","")
    })
    # intervals
    for name in EVENT_NAMES:
        if name in ("Contact","Search","CompleteRegistration"): # not in default table, but allow custom
            default = 10.0
        else:
            default = {"PageView":1.5,"ViewContent":2.0,"AddToCart":3.5,"InitiateCheckout":4.0,"AddPaymentInfo":5.0,"Purchase":6.0}.get(name, 8.0)
        out[f"interval_{name}"] = float(KVStore.get(f"interval_{name}", default))
    return out

@admin_bp.route("/api/seed", methods=["POST"])
@login_required
def api_seed():
    data = request.json or {}
    seed = data.get("seed")
    if seed is None or seed == "":
        KVStore.set("rng_seed","")
        return {"ok": True, "message":"Seed cleared"}
    try:
        seed_val = int(seed)
    except:
        return {"ok": False, "error":"Seed must be an integer"}, 400
    KVStore.set("rng_seed", str(seed_val))
    random.seed(seed_val)
    return {"ok": True, "seed": seed_val}

@admin_bp.route("/api/chaos", methods=["POST"])
@login_required
def api_chaos():
    data = request.json or {}
    for k in ("chaos_drop","chaos_omit","chaos_malformed"):
        if k in data:
            KVStore.set(k, "1" if bool(data[k]) else "0")
    return {"ok": True}

# -------------------- Manual Send & Automation --------------------
@admin_bp.route("/api/manual_send", methods=["POST"])
@login_required
def manual_send():
    payload = request.json or {}
    status_p = send_pixel(payload)
    status_c = send_capi(payload)
    return {"ok": True, "pixel": status_p[0], "capi": status_c[0]}

def automation_worker(event_name, interval_s):
    while not AUTOMATION_STOP.is_set():
        if not event_enabled(event_name):
            time.sleep(max(0.25, float(interval_s)))
            continue
        value = 0.0
        currency = "USD"
        if event_name == "Purchase":
            price = random.uniform(10, 300)
            cmin, cmax = margin_min(), margin_max()
            cost = price * random.uniform(cmin, cmax)
            margin = max(0, price - cost)
            value = price
            c = Counters.get_or_create()
            c.margin_sum += margin
            if pltv_randomized():
                c.pltv_sum += random.uniform(pltv_min(), pltv_max())
            db.session.commit()
        ev = make_event(event_name, value=value, currency=currency)
        send_pixel(ev)
        send_capi(ev)
        time.sleep(max(0.25, float(interval_s)))

@admin_bp.route("/api/automation", methods=["POST"])
@login_required
def api_automation():
    data = request.json or {}
    cmd = data.get("cmd")
    if cmd == "start":
        if AUTOMATION_THREADS:
            return {"ok": False, "error":"already running"}, 400
        AUTOMATION_STOP.clear()
        intervals = data.get("intervals", {})
        # Load saved intervals when not provided
        for name in EVENT_NAMES:
            key = f"interval_{name}"
            if key not in intervals:
                default = {"PageView":1.5,"ViewContent":2.0,"AddToCart":3.5,"InitiateCheckout":4.0,"AddPaymentInfo":5.0,"Purchase":6.0}.get(name, 8.0)
                intervals[key] = float(KVStore.get(key, default))
        # Start threads for commonly simulated events
        for name in ("PageView","ViewContent","AddToCart","InitiateCheckout","AddPaymentInfo","Purchase"):
            interval = float(intervals.get(f"interval_{name}", 6.0))
            t = threading.Thread(target=automation_worker, args=(name, interval), daemon=True)
            t.start()
            AUTOMATION_THREADS[name] = t
        return {"ok": True, "started": list(AUTOMATION_THREADS.keys())}
    elif cmd == "stop":
        AUTOMATION_STOP.set()
        for k,t in list(AUTOMATION_THREADS.items()):
            t.join(timeout=0.1)
        AUTOMATION_THREADS.clear()
        return {"ok": True, "stopped": True}
    return {"ok": False, "error":"unknown cmd"}, 400

# -------------------- Request Inspector & Logs --------------------
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

# -------------------- Catalog Manager --------------------
@admin_bp.route("/catalog", methods=["GET","POST"])
@login_required
def catalog():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            sku = request.form.get("sku")
            name = request.form.get("name")
            price = float(request.form.get("price","0"))
            currency = request.form.get("currency","USD")
            p = Product(sku=sku, name=name, price=price, currency=currency)
            db.session.add(p); db.session.commit()
        elif action == "delete":
            sku = request.form.get("sku")
            Product.query.filter_by(sku=sku).delete()
            db.session.commit()
    items = Product.query.all()
    return render_template("admin/catalog.html", items=items)

# -------------------- Health / Version & Pixel Install Checker --------------------
@admin_bp.route("/health")
@login_required
def health_panel():
    build = KVStore.get("build_number","v1.0.0")
    graph = KVStore.get("graph_version","v20.0")
    pixel_ok = bool(Config.PIXEL_ID)
    reach_ok = True
    try:
        requests.get("https://graph.facebook.com", timeout=3)
    except Exception:
        reach_ok = False
    return jsonify({"build":build,"graph_version":graph,"pixel_configured":pixel_ok,"network_reachability":reach_ok})

@admin_bp.route("/api/pixel-check", methods=["POST"])
@login_required
def pixel_check():
    import os
    from flask import request as _rq
    candidates = []
    # 1) Prefer localhost inside the container
    port = os.getenv("PORT")
    if port:
        candidates.append(f"http://127.0.0.1:{port}/")
    # 2) Configured BASE_URL (must include https://)
    base = (Config.BASE_URL or "").rstrip("/")
    if base.startswith("http"):
        candidates.append(f"{base}/")
    # 3) Fallback to the current host_url
    try:
        if _rq and _rq.host_url:
            candidates.append(_rq.host_url)
    except Exception:
        pass

    last_err = None
    for url in candidates:
        try:
            resp = requests.get(url, timeout=8)
            html = resp.text.lower()
            has_meta_noindex = ('name="robots"' in html) or ('noindex' in html)
            has_pixel_snippet = ("window.demopixel" in html) or ("/static/js/pixel.js" in html)
            return {
                "ok": True,
                "source": url,
                "has_meta_noindex": has_meta_noindex,
                "has_pixel_snippet": has_pixel_snippet
            }
        except Exception as e:
            last_err = str(e)[:200]
            continue
    return {"ok": False, "error": last_err or "unable to fetch any candidate URL"}

