import json, uuid, time, traceback, requests, random, threading, ipaddress
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_user, logout_user, login_required
from sqlalchemy import desc

from config import Config
from extensions import db
from models import User, KVStore, EventLog, Counters, Product

admin_bp = Blueprint("admin", __name__, template_folder="templates")

# -------------------- Helpers & Config Flags --------------------
def _as_dict(x):
    """Coerce any JSON-ish into a dict, else {}."""
    if isinstance(x, dict):
        return x
    try:
        return dict(x)
    except Exception:
        return {}

def _sg(d, key, default=None):
    """Safe get from dict-like; never subscript None."""
    return d.get(key, default) if isinstance(d, dict) else default

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

# -------------------- Rate Limiting (Token Bucket) --------------------
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
@admin_bp.route("/login", methods=["GET", "POST"])
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

# -------------------- Event Builders & Senders --------------------
def make_event(event_name, value=0.0, currency="USD"):
    eid = str(uuid.uuid4())
    payload = {"event_name": event_name, "event_id": eid, "currency": currency, "value": value}
    if chaos_omit():
        payload.pop("currency", None)
    if chaos_malformed():
        payload["value"] = "NaN"
    return payload

def send_pixel(event, status_override=None):
    # Fully defensive: never raise
    event = _as_dict(event)
    if not pixel_enabled() or chaos_drop():
        return ("dropped", 0, None)
    try:
        start = time.time()
        time.sleep(0.005)  # simulate small client delay
        latency = int((time.time() - start) * 1000)
        status = status_override or "ok"
        ev = EventLog(
            ts=datetime.utcnow(),
            channel="pixel",
            event_name=_sg(event, "event_name", "?"),
            event_id=_sg(event, "event_id", str(uuid.uuid4())),
            status=status,
            latency_ms=latency,
            payload=json.dumps(event)
        )
        db.session.add(ev)
        c = Counters.get_or_create()
        c.pixel += 1
        # dedup if same id already logged on CAPI
        dup = EventLog.query.filter_by(event_id=ev.event_id, channel="capi").first()
        if dup:
            c.dedup += 1
        db.session.commit()
        return (status, latency, None)
    except Exception as e:
        try:
            ev = EventLog(
                ts=datetime.utcnow(), channel="pixel",
                event_name=_sg(event, "event_name", "?"),
                event_id=_sg(event, "event_id", ""),
                status="error", latency_ms=0,
                payload=json.dumps(_as_dict(event)),
                error=str(e)[:1000]
            )
            db.session.add(ev); db.session.commit()
        except Exception:
            pass
        return ("error", 0, str(e)[:1000])

def _clean_ip(raw):
    """Return a valid IPv4/IPv6 string or None."""
    if not raw:
        return None
    ip = raw.split(",")[0].strip()  # take first from XFF chain
    # Strip :port for IPv4 "x.x.x.x:port"; preserve IPv6 format
    if "." in ip and ip.count(":") == 1:
        ip = ip.split(":")[0]
    try:
        ipaddress.ip_address(ip)
        return ip
    except Exception:
        return None

def send_capi(event):
    # Fully defensive: never raise
    event = _as_dict(event)
    if not capi_enabled() or chaos_drop():
        return ("dropped", 0, None)

    start = time.time()
    status, err = "ok", None

    # Minimal user_data for website events (avoids 2804050). Clean invalid IPs.
    try:
        ua = request.headers.get("User-Agent", "") if request else ""
        ip_raw = (request.headers.get("X-Forwarded-For", "") or (request.remote_addr or "")) if request else ""
        fbp = request.cookies.get("_fbp") if request else None
        fbc = request.cookies.get("_fbc") if request else None
    except Exception:
        ua, ip_raw, fbp, fbc = "Mozilla/5.0 (Server Automation)", "", None, None
    if not ua:
        ua = "Mozilla/5.0"
    clean_ip = _clean_ip(ip_raw)

    url = f"https://graph.facebook.com/{getattr(Config,'GRAPH_VER','v20.0')}/{getattr(Config,'PIXEL_ID','')}/events"
    data = {
        "data": [{
            "event_name": _sg(event, "event_name", "?"),
            "event_time": int(time.time()),
            "event_id": _sg(event, "event_id", str(uuid.uuid4())),
            "action_source": "website",
            "event_source_url": (getattr(Config,'BASE_URL',None) or "https://example.com"),
            "user_data": {
                "client_user_agent": ua,
                **({"client_ip_address": clean_ip} if clean_ip else {}),
                **({"fbp": fbp} if fbp else {}),
                **({"fbc": fbc} if fbc else {}),
            },
            "custom_data": {
                "currency": _sg(event, "currency", "USD"),
                "value": float(_sg(event, "value", 0) or 0)
            }
        }]
    }
    test_code = getattr(Config, "TEST_EVENT_CODE", "")
    if test_code:
        data["test_event_code"] = test_code

    try:
        # Respect channel rate limit
        while not capi_bucket.take():
            time.sleep(0.02)

        # Real call only when creds exist; otherwise dry-run
        if getattr(Config, "PIXEL_ID", "") and getattr(Config, "ACCESS_TOKEN", ""):
            resp = requests.post(
                url,
                params={"access_token": getattr(Config, "ACCESS_TOKEN", "")},
                json=data,
                timeout=10
            )
            ok = 200 <= resp.status_code < 300
            status = "ok" if ok else f"http_{resp.status_code}"
            if not ok:
                err = (resp.text or "")[:1000]
        else:
            status = "dry_run"
    except Exception as e:
        status = "error"
        err = str(e)[:1000]

    latency = int((time.time() - start) * 1000)

    # Always log
    try:
        ev = EventLog(
            ts=datetime.utcnow(), channel="capi",
            event_name=_sg(event, "event_name", "?"),
            event_id=_sg(event, "event_id", ""),
            status=status, latency_ms=latency,
            payload=json.dumps(data), error=err
        )
        db.session.add(ev)
        if status in ("ok", "dry_run"):
            c = Counters.get_or_create()
            c.capi += 1
            dup = EventLog.query.filter_by(event_id=ev.event_id, channel="pixel").first()
            if dup:
                c.dedup += 1
        db.session.commit()
    except Exception:
        pass

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
    default_intervals = {"PageView":1.5,"ViewContent":2.0,"AddToCart":3.5,"InitiateCheckout":4.0,"AddPaymentInfo":5.0,"Purchase":6.0}
    user_intervals = {}
    for name, d in default_intervals.items():
        user_intervals[name] = float(KVStore.get(f"interval_{name}", d))
    chaos = {"drop": chaos_drop(), "omit": chaos_omit(), "malformed": chaos_malformed()}
    return render_template("admin/dashboard.html", counters=c, build=build, graph=graph,
                           pixel=pixel, capi=capi, recent=recent, events=EVENT_NAMES,
                           seed=seed, intervals=user_intervals, chaos=chaos)

# -------------------- Toggles & Settings APIs --------------------
@admin_bp.route("/api/toggle", methods=["POST"])
@login_required
def api_toggle():
    data = request.get_json(silent=True) or {}
    key = data.get("key")
    val = bool(data.get("value", True))
    if key is None:
        return {"ok": False, "error":"missing key"}, 400
    KVStore.set(key, "1" if val else "0")
    return {"ok": True}

@admin_bp.route("/api/settings", methods=["GET","POST"])
@login_required
def api_settings():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        for k,v in data.items():
            KVStore.set(k, str(v))
        return {"ok": True}
    # GET
    out = { "pixel_enabled": pixel_enabled(), "capi_enabled": capi_enabled() }
    for name in EVENT_NAMES:
        out[f"ev_{name}"] = _get_bool(f"ev_{name}", True)
    out.update({
        "margin_min": margin_min(), "margin_max": margin_max(),
        "pltv_min": pltv_min(), "pltv_max": pltv_max(),
        "pltv_randomized": pltv_randomized(),
        "chaos_drop": chaos_drop(),
        "chaos_omit": chaos_omit(),
        "chaos_malformed": chaos_malformed(),
        "rng_seed": KVStore.get("rng_seed","")
    })
    # intervals defaults
    for name in EVENT_NAMES:
        default = {"PageView":1.5,"ViewContent":2.0,"AddToCart":3.5,"InitiateCheckout":4.0,"AddPaymentInfo":5.0,"Purchase":6.0}.get(name, 8.0)
        out[f"interval_{name}"] = float(KVStore.get(f"interval_{name}", default))
    return out

@admin_bp.route("/api/seed", methods=["POST"])
@login_required
def api_seed():
    data = request.get_json(silent=True) or {}
    seed = data.get("seed")
    if seed is None or seed == "":
        KVStore.set("rng_seed","")
        return {"ok": True, "message":"Seed cleared"}
    try:
        seed_val = int(seed)
    except Exception:
        return {"ok": False, "error":"Seed must be an integer"}, 400
    KVStore.set("rng_seed", str(seed_val))
    random.seed(seed_val)
    return {"ok": True, "seed": seed_val}

@admin_bp.route("/api/chaos", methods=["POST"])
@login_required
def api_chaos():
    data = request.get_json(silent=True) or {}
    for k in ("chaos_drop","chaos_omit","chaos_malformed"):
        if k in data:
            KVStore.set(k, "1" if bool(data[k]) else "0")
    return {"ok": True}

# -------------------- Manual Send & Automation --------------------
@admin_bp.route("/api/manual_send", methods=["POST"])
@login_required
def manual_send():
    payload = {}
    try:
        body = request.get_json(silent=True)
        if body is None:
            raw = request.get_data(as_text=True) or ""
            body = json.loads(raw) if raw.strip() else {}
        payload = _as_dict(body)

        # Fill defaults and normalize
        payload.setdefault("event_name", "PageView")
        payload.setdefault("event_id", str(uuid.uuid4()))
        payload.setdefault("currency", "USD")
        try:
            payload["value"] = float(payload.get("value", 0) or 0)
        except Exception:
            payload["value"] = 0.0

        # Call channels individually and never let exceptions escape
        try:
            p_status = send_pixel(payload)
        except Exception as e:
            p_status = ("error", 0, str(e)[:1000])
        try:
            c_status = send_capi(payload)
        except Exception as e:
            c_status = ("error", 0, str(e)[:1000])

        return jsonify({"ok": True, "pixel": p_status[0], "capi": c_status[0]})
    except Exception as e:
        tb = traceback.format_exc(limit=3)
        try:
            ev = EventLog(
                ts=datetime.utcnow(), channel="capi",
                event_name="manual_send", event_id=_sg(payload, "event_id", ""),
                status="server_500", latency_ms=0,
                payload=json.dumps(_as_dict(payload)),
                error=(str(e) + " | " + tb)[:1000]
            )
            db.session.add(ev); db.session.commit()
        except Exception:
            pass
        return jsonify({"ok": False, "error": str(e)}), 500

# Automation
AUTOMATION_THREADS = {}
AUTOMATION_STOP = threading.Event()

def automation_worker(app, event_name, interval_s):
    # Ensure a Flask app context so DB and config work in threads
    with app.app_context():
        while not AUTOMATION_STOP.is_set():
            if not _get_bool(f"ev_{event_name}", True):
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
            try:
                send_pixel(ev)
                send_capi(ev)
            except Exception:
                pass
            time.sleep(max(0.25, float(interval_s)))

@admin_bp.route("/api/automation", methods=["POST"])
@login_required
def api_automation():
    data = request.get_json(silent=True) or {}
    cmd = data.get("cmd")
    if cmd == "start":
        if AUTOMATION_THREADS:
            return {"ok": False, "error":"already running"}, 400
        AUTOMATION_STOP.clear()
        # intervals from request or KV
        intervals = data.get("intervals", {})
        app = current_app._get_current_object()
        for name in ("PageView","ViewContent","AddToCart","InitiateCheckout","AddPaymentInfo","Purchase"):
            key = f"interval_{name}"
            default = {"PageView":1.5,"ViewContent":2.0,"AddToCart":3.5,"InitiateCheckout":4.0,"AddPaymentInfo":5.0,"Purchase":6.0}.get(name, 8.0)
            interval = float(intervals.get(key, KVStore.get(key, default)))
            t = threading.Thread(target=automation_worker, args=(app, name, interval), daemon=True)
            t.start()
            AUTOMATION_THREADS[name] = t
        return {"ok": True, "started": list(AUTOMATION_THREADS.keys())}
    elif cmd == "stop":
        AUTOMATION_STOP.set()
        for k,t in list(AUTOMATION_THREADS.items()):
            t.join(timeout=0.2)
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
    pixel_ok = bool(getattr(Config, "PIXEL_ID", ""))
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
    candidates = []
    # 1) Prefer localhost inside the container
    port = os.getenv("PORT")
    if port:
        candidates.append(f"http://127.0.0.1:{port}/")
    # 2) Configured BASE_URL (must include http/https)
    base = (getattr(Config,'BASE_URL',None) or "").rstrip("/")
    if base.startswith("http"):
        candidates.append(f"{base}/")
    # 3) Fallback to current host_url
    try:
        if request and request.host_url:
            candidates.append(request.host_url)
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
                "ok": True, "source": url,
                "has_meta_noindex": has_meta_noindex,
                "has_pixel_snippet": has_pixel_snippet
            }
        except Exception as e:
            last_err = str(e)[:200]
            continue
    return {"ok": False, "error": last_err or "unable to fetch any candidate URL"}
