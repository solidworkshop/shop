import json, uuid, time, traceback, requests, random, threading, ipaddress
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_user, logout_user, login_required
from sqlalchemy import desc, func

from config import Config
from extensions import db
from models import User, KVStore, EventLog, Counters, Product

admin_bp = Blueprint("admin", __name__, template_folder="templates")

# -------------------- Helpers & Flags --------------------
def _as_dict(x):
    if isinstance(x, dict): return x
    try: return dict(x)
    except Exception: return {}

def _sg(d, key, default=None):
    return d.get(key, default) if isinstance(d, dict) else default

# Pixel/CAPI always available; automation can target channels via toggles
def pixel_enabled(): return True
def capi_enabled(): return True

def get_auto_pixel(): return (KVStore.get("automation_pixel","1") == "1")
def get_auto_capi():  return (KVStore.get("automation_capi","1") == "1")

EVENT_NAMES = ["PageView","ViewContent","AddToCart","InitiateCheckout","AddPaymentInfo","Purchase","Contact","Search","CompleteRegistration"]

def chaos_drop(): return (KVStore.get("chaos_drop","0")=="1")
def chaos_omit(): return (KVStore.get("chaos_omit","0")=="1")
def chaos_malformed(): return (KVStore.get("chaos_malformed","0")=="1")

def margin_min(): return float(KVStore.get("margin_min","0.10"))
def margin_max(): return float(KVStore.get("margin_max","0.40"))
def pltv_min(): return float(KVStore.get("pltv_min","120"))
def pltv_max(): return float(KVStore.get("pltv_max","600"))
def pltv_randomized(): return (KVStore.get("pltv_randomized","1")=="1")

def pct_margin(): return int(KVStore.get("pct_profit_margin","100"))
def pct_pltv():   return int(KVStore.get("pct_pltv","100"))

# Catalog settings
def catalog_item_count(): return int(KVStore.get("catalog_item_count","12"))
def catalog_currency_mode(): return KVStore.get("catalog_currency_mode","auto")  # auto|null|specific
def catalog_currency_specific(): return KVStore.get("catalog_currency_specific","USD")
def catalog_locale(): return KVStore.get("catalog_locale","en-US")

# -------------------- Rate Limiting --------------------
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
def send_pixel(event, status_override=None):
    event = _as_dict(event)
    if not pixel_enabled() or chaos_drop(): return ("dropped", 0, None)
    try:
        start = time.time()
        time.sleep(0.005)
        latency = int((time.time() - start) * 1000)
        status = status_override or "ok"
        ev = EventLog(
            ts=datetime.utcnow(), channel="pixel",
            event_name=_sg(event,"event_name","?"),
            event_id=_sg(event,"event_id",str(uuid.uuid4())),
            status=status, latency_ms=latency,
            payload=json.dumps(event)
        )
        db.session.add(ev)
        c = Counters.get_or_create()
        c.pixel += 1
        dup = EventLog.query.filter_by(event_id=ev.event_id, channel="capi").first()
        if dup: c.dedup += 1
        db.session.commit()
        return (status, latency, None)
    except Exception as e:
        try:
            ev = EventLog(ts=datetime.utcnow(), channel="pixel",
                          event_name=_sg(event,"event_name","?"),
                          event_id=_sg(event,"event_id",""),
                          status="error", latency_ms=0,
                          payload=json.dumps(_as_dict(event)), error=str(e)[:1000])
            db.session.add(ev); db.session.commit()
        except Exception: pass
        return ("error", 0, str(e)[:1000])

import ipaddress
def _clean_ip(raw):
    if not raw: return None
    ip = raw.split(",")[0].strip()
    if "." in ip and ip.count(":")==1:
        ip = ip.split(":")[0]
    try:
        ipaddress.ip_address(ip)
        return ip
    except Exception:
        return None

def _ensure_synthetic_fbp():
    fbpk = "synthetic_fbp"
    fbp = KVStore.get(fbpk, None)
    if not fbp:
        fbp = f"fb.1.{int(time.time())}.{random.randint(1000000000, 9999999999)}"
        KVStore.set(fbpk, fbp)
    return fbp

def send_capi(event):
    event = _as_dict(event)
    if not capi_enabled() or chaos_drop(): return ("dropped", 0, None)
    start = time.time(); status, err = "ok", None
    try:
        ua = request.headers.get("User-Agent","") if request else ""
        ip_raw = (request.headers.get("X-Forwarded-For","") or (request.remote_addr or "")) if request else ""
        fbp = request.cookies.get("_fbp") if request else None
        fbc = request.cookies.get("_fbc") if request else None
    except Exception:
        ua, ip_raw, fbp, fbc = "Mozilla/5.0 (Server Automation)", "", None, None
    if not ua: ua = "Mozilla/5.0"
    clean_ip = _clean_ip(ip_raw)
    if not fbp:
        try: fbp = _ensure_synthetic_fbp()
        except Exception: fbp = f"fb.1.{int(time.time())}.{random.randint(1000000000, 9999999999)}"

    url = f"https://graph.facebook.com/{getattr(Config,'GRAPH_VER','v20.0')}/{getattr(Config,'PIXEL_ID','')}/events"
    custom = {"currency": _sg(event,"currency","USD"), "value": float(_sg(event,"value",0) or 0)}
    if "profit_margin" in event: custom["profit_margin"] = _sg(event,"profit_margin")
    if "pltv" in event: custom["pltv"] = _sg(event,"pltv")
    data = {"data":[{
        "event_name": _sg(event,"event_name","?"),
        "event_time": int(time.time()),
        "event_id": _sg(event,"event_id",str(uuid.uuid4())),
        "action_source": "website",
        "event_source_url": (getattr(Config,'BASE_URL',None) or "https://example.com"),
        "user_data": {
            "client_user_agent": ua,
            **({"client_ip_address": clean_ip} if clean_ip else {}),
            **({"fbp": fbp} if fbp else {}),
            **({"fbc": fbc} if fbc else {}),
        },
        "custom_data": custom
    }]}
    test_code = getattr(Config,"TEST_EVENT_CODE","")
    if test_code: data["test_event_code"]=test_code
    try:
        while not capi_bucket.take(): time.sleep(0.02)
        if getattr(Config,"PIXEL_ID","") and getattr(Config,"ACCESS_TOKEN",""):
            resp = requests.post(url, params={"access_token": getattr(Config,"ACCESS_TOKEN","")}, json=data, timeout=10)
            ok = 200 <= resp.status_code < 300
            status = "ok" if ok else f"http_{resp.status_code}"
            if not ok: err = (resp.text or "")[:1000]
        else:
            status = "dry_run"
    except Exception as e:
        status="error"; err=str(e)[:1000]
    latency = int((time.time()-start)*1000)
    try:
        ev = EventLog(ts=datetime.utcnow(), channel="capi",
                      event_name=_sg(event,"event_name","?"),
                      event_id=_sg(event,"event_id",""),
                      status=status, latency_ms=latency,
                      payload=json.dumps(data), error=err)
        db.session.add(ev)
        if status in ("ok","dry_run"):
            c = Counters.get_or_create()
            c.capi += 1
            dup = EventLog.query.filter_by(event_id=ev.event_id, channel="pixel").first()
            if dup: c.dedup += 1
        db.session.commit()
    except Exception: pass
    return (status, latency, err)

# -------------------- UI --------------------
@admin_bp.route("/")
@login_required
def dashboard():
    # Force-update build number so badge always matches this bundle
    KVStore.set("build_number","v1.3.0")
    c = Counters.get_or_create()
    build = KVStore.get("build_number","v1.3.0")
    recent = EventLog.query.order_by(desc(EventLog.ts)).limit(20).all()
    default_intervals = {"PageView":1.5,"ViewContent":2.0,"AddToCart":3.5,"InitiateCheckout":4.0,"AddPaymentInfo":5.0,"Purchase":6.0}
    user_intervals = {n: float(KVStore.get(f"interval_{n}", d)) for n,d in default_intervals.items()}
    chaos = {"drop": chaos_drop(), "omit": chaos_omit(), "malformed": chaos_malformed()}
    auto_pixel = get_auto_pixel()
    auto_capi = get_auto_capi()
    return render_template("admin/dashboard.html",
        counters=c, build=build, recent=recent, events=EVENT_NAMES,
        intervals=user_intervals, chaos=chaos, auto_pixel=auto_pixel, auto_capi=auto_capi,
        pct_profit_margin=pct_margin(), pct_pltv=pct_pltv())

# -------------------- Settings APIs --------------------
@admin_bp.route("/api/settings", methods=["GET","POST"])
@login_required
def api_settings():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        if "automation_pixel" in data: KVStore.set("automation_pixel", "1" if data["automation_pixel"] else "0")
        if "automation_capi" in data:  KVStore.set("automation_capi", "1" if data["automation_capi"] else "0")
        if "pct_profit_margin" in data:
            try: KVStore.set("pct_profit_margin", str(max(0,min(100,int(data["pct_profit_margin"])))))
            except Exception: pass
        if "pct_pltv" in data:
            try: KVStore.set("pct_pltv", str(max(0,min(100,int(data["pct_pltv"])))))
            except Exception: pass
        for n in ("PageView","ViewContent","AddToCart","InitiateCheckout","AddPaymentInfo","Purchase"):
            k = f"interval_{n}"
            if k in data:
                try: KVStore.set(k, str(float(data[k])))
                except Exception: pass
        return {"ok":True}
    # GET
    return {
        "chaos_drop": chaos_drop(),
        "chaos_omit": chaos_omit(),
        "chaos_malformed": chaos_malformed(),
        "automation_pixel": get_auto_pixel(),
        "automation_capi": get_auto_capi(),
        "pct_profit_margin": pct_margin(),
        "pct_pltv": pct_pltv(),
        **{ f"interval_{n}": float(KVStore.get(f"interval_{n}", d))
           for n,d in {"PageView":1.5,"ViewContent":2.0,"AddToCart":3.5,"InitiateCheckout":4.0,"AddPaymentInfo":5.0,"Purchase":6.0}.items()
        }
    }

@admin_bp.route("/api/chaos", methods=["POST"])
@login_required
def api_chaos():
    data = request.get_json(silent=True) or {}
    for k in ("chaos_drop","chaos_omit","chaos_malformed"):
        if k in data: KVStore.set(k, "1" if bool(data[k]) else "0")
    return {"ok":True}

# -------------------- Manual Send --------------------
@admin_bp.route("/api/manual_send", methods=["POST"])
@login_required
def manual_send():
    try:
        body = request.get_json(silent=True)
        if body is None:
            raw = request.get_data(as_text=True) or ""
            body = json.loads(raw) if raw.strip() else {}
        payload = _as_dict(body)
        if "event_name" not in payload: payload["event_name"] = "PageView"
        if "event_id" not in payload:   payload["event_id"] = str(uuid.uuid4())
        if "currency" not in payload:   payload["currency"] = "USD"
        if "value" in payload:
            try: payload["value"] = float(payload["value"])
            except Exception: payload["value"] = 0.0
        if chaos_omit():
            payload.pop("currency", None)
        if chaos_malformed():
            payload["value"] = "NaN"
        p_status = send_pixel(payload)
        c_status = send_capi(payload)
        return jsonify({"ok": True, "pixel": p_status[0], "capi": c_status[0]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# -------------------- Automation --------------------
AUTOMATION_THREADS = {}
AUTOMATION_STOP = threading.Event()

def automation_worker(app, event_name, interval_s):
    with app.app_context():
        while not AUTOMATION_STOP.is_set():
            value = 0.0; currency="USD"
            event_payload = {"event_name": event_name, "event_id": str(uuid.uuid4()), "currency": currency}
            if event_name == "Purchase":
                price = random.uniform(10,300)
                cmin,cmax = margin_min(), margin_max()
                cost = price * random.uniform(cmin,cmax)
                margin = max(0, price - cost)
                value = price
                event_payload["value"] = value
                if random.randint(1,100) <= pct_margin():
                    event_payload["profit_margin"] = round(margin, 2)
                if pltv_randomized() and (random.randint(1,100) <= pct_pltv()):
                    event_payload["pltv"] = round(random.uniform(pltv_min(), pltv_max()), 2)
            else:
                event_payload["value"] = value

            if get_auto_pixel():
                try: send_pixel(event_payload)
                except Exception: pass
            if get_auto_capi():
                try: send_capi(event_payload)
                except Exception: pass
            time.sleep(max(0.25, float(interval_s)))

@admin_bp.route("/api/automation", methods=["POST"])
@login_required
def api_automation():
    data = request.get_json(silent=True) or {}
    cmd = data.get("cmd")
    if cmd == "start":
        if AUTOMATION_THREADS:
            return {"ok":False,"error":"already running"},400
        AUTOMATION_STOP.clear()
        intervals = data.get("intervals", {})
        app = current_app._get_current_object()
        defaults = {"PageView":1.5,"ViewContent":2.0,"AddToCart":3.5,"InitiateCheckout":4.0,"AddPaymentInfo":5.0,"Purchase":6.0}
        for name, default in defaults.items():
            key = f"interval_{name}"
            interval = float(intervals.get(key, KVStore.get(key, default)))
            t = threading.Thread(target=automation_worker, args=(app,name,interval), daemon=True)
            t.start(); AUTOMATION_THREADS[name]=t
        return {"ok":True,"started": list(AUTOMATION_THREADS.keys())}
    elif cmd == "stop":
        AUTOMATION_STOP.set()
        for k,t in list(AUTOMATION_THREADS.items()):
            t.join(timeout=0.2)
        AUTOMATION_THREADS.clear()
        return {"ok":True,"stopped":True}
    return {"ok":False,"error":"unknown cmd"},400

# -------------------- Live Status Endpoints --------------------
@admin_bp.route("/api/counters")
@login_required
def api_counters():
    c = Counters.get_or_create()
    margin_events = db.session.query(func.count(EventLog.id)).filter(EventLog.payload.contains('"profit_margin"')).scalar() or 0
    pltv_events   = db.session.query(func.count(EventLog.id)).filter(EventLog.payload.contains('"pltv"')).scalar() or 0
    return {
        "ok": True,
        "pixel": c.pixel,
        "capi": c.capi,
        "dedup": c.dedup,
        "margin_events": int(margin_events),
        "pltv_events": int(pltv_events)
    }

@admin_bp.route("/api/automation_status")
@login_required
def api_automation_status():
    running = bool(AUTOMATION_THREADS) and not AUTOMATION_STOP.is_set()
    return {"ok": True, "running": running, "threads": list(AUTOMATION_THREADS.keys()),
            "automation_pixel": get_auto_pixel(), "automation_capi": get_auto_capi(),
            "pct_profit_margin": pct_margin(), "pct_pltv": pct_pltv()}

# -------------------- Catalog Management --------------------
def product_to_dict(p):
    return {
        "id": p.id, "sku": p.sku, "name": p.name, "price": float(getattr(p,"price",0) or 0),
        "currency": getattr(p,"currency","USD"),
        "description": getattr(p,"description",""),
        "image_url": getattr(p,"image_url","")
    }

@admin_bp.route("/catalog")
@login_required
def catalog_page():
    products = Product.query.order_by(Product.id.asc()).all()
    return render_template("admin/catalog.html",
        products=products,
        settings={
            "item_count": catalog_item_count(),
            "currency_mode": catalog_currency_mode(),
            "currency_specific": catalog_currency_specific(),
            "locale": catalog_locale()
        }
    )

@admin_bp.route("/api/catalog", methods=["GET","POST"])
@login_required
def api_catalog():
    if request.method == "GET":
        products = Product.query.order_by(Product.id.asc()).all()
        return jsonify({"ok":True, "products":[product_to_dict(p) for p in products]})
    data = request.get_json(silent=True) or {}
    pid = data.get("id")
    if pid:
        p = Product.query.get(pid)
        if not p: return {"ok":False,"error":"not found"},404
    else:
        p = Product()
        db.session.add(p)
    p.sku = data.get("sku") or p.sku or f"SKU-{random.randint(10000,99999)}"
    p.name = data.get("name") or p.name or "Product"
    try:
        p.price = float(data.get("price", getattr(p,"price",0) or 0))
    except Exception:
        p.price = 0.0
    p.currency = data.get("currency") or getattr(p,"currency", catalog_currency_specific() if catalog_currency_mode()=="specific" else "USD")
    p.description = data.get("description") or getattr(p,"description","")
    p.image_url = data.get("image_url") or getattr(p,"image_url","")
    db.session.commit()
    return {"ok":True, "product": product_to_dict(p)}

@admin_bp.route("/api/catalog/<int:pid>", methods=["DELETE"])
@login_required
def api_catalog_delete(pid):
    p = Product.query.get(pid)
    if not p: return {"ok":False,"error":"not found"},404
    db.session.delete(p); db.session.commit()
    return {"ok":True}

@admin_bp.route("/api/catalog/seed", methods=["POST"])
@login_required
def api_catalog_seed():
    data = request.get_json(silent=True) or {}
    count = int(data.get("count", catalog_item_count()))
    mode = catalog_currency_mode()
    cur = catalog_currency_specific()
    for i in range(count):
        p = Product(
            sku=f"SKU-{random.randint(10000,99999)}",
            name=f"Demo Item {random.randint(100,999)}",
            price=round(random.uniform(5,250), 2),
            currency=(None if mode=="null" else (cur if mode=="specific" else "USD")),
            description="Demo product for Pixel/CAPI testing.",
            image_url="https://picsum.photos/seed/"+str(random.randint(1,9999))+"/400/400"
        )
        db.session.add(p)
    db.session.commit()
    return {"ok":True,"seeded":count}

@admin_bp.route("/api/catalog/settings", methods=["GET","POST"])
@login_required
def api_catalog_settings():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        if "item_count" in data:
            try: KVStore.set("catalog_item_count", str(max(1, int(data["item_count"]))))
            except Exception: pass
        if "currency_mode" in data:
            if data["currency_mode"] in ("auto","null","specific"):
                KVStore.set("catalog_currency_mode", data["currency_mode"])
        if "currency_specific" in data:
            KVStore.set("catalog_currency_specific", str(data["currency_specific"]).upper()[:3])
        if "locale" in data:
            KVStore.set("catalog_locale", str(data["locale"]))
        return {"ok":True}
    return {"ok":True,
            "item_count": catalog_item_count(),
            "currency_mode": catalog_currency_mode(),
            "currency_specific": catalog_currency_specific(),
            "locale": catalog_locale()}

# -------------------- Inspector & Pixel Check --------------------
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

@admin_bp.route("/api/pixel-check", methods=["POST"])
@login_required
def pixel_check():
    import os
    candidates = []
    port = os.getenv("PORT")
    if port: candidates.append(f"http://127.0.0.1:{port}/")
    base = (getattr(Config,'BASE_URL',None) or "").rstrip("/")
    if base.startswith("http"): candidates.append(f"{base}/")
    try:
        if request and request.host_url: candidates.append(request.host_url)
    except Exception: pass
    last_err=None
    for url in candidates:
        try:
            resp = requests.get(url, timeout=8)
            html = resp.text.lower()
            has_meta_noindex = ('name="robots"' in html) or ('noindex' in html)
            has_pixel_snippet = ("window.demopixel" in html) or ("/static/js/pixel.js" in html)
            return {"ok":True,"source":url,"has_meta_noindex":has_meta_noindex,"has_pixel_snippet":has_pixel_snippet}
        except Exception as e:
            last_err = str(e)[:200]; continue
    return {"ok":False,"error": last_err or "unable to fetch any candidate URL"}
