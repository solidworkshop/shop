import json, uuid, time, requests, random, threading, ipaddress
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_user, logout_user, login_required
from sqlalchemy import desc, func
from config import Config
from extensions import db
from models import User, KVStore, EventLog, Counters

admin_bp = Blueprint("admin", __name__, template_folder="../templates/admin")

def _as_dict(x):
    if isinstance(x, dict): return x
    try: return dict(x)
    except Exception: return {}

def _sg(d, k, default=None):
    return d.get(k, default) if isinstance(d, dict) else default

def pixel_enabled(): return True
def capi_enabled(): return True
def get_auto_pixel(): return (KVStore.get("automation_pixel","1")=="1")
def get_auto_capi():  return (KVStore.get("automation_capi","1")=="1")
def use_test_code():  return (KVStore.get("use_test_event_code","1")=="1")

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

class TokenBucket:
    def __init__(self, qps, burst=None):
        self.qps=float(qps or 1.0); self.capacity=burst or max(1,int(self.qps*2))
        self.tokens=self.capacity; self.updated=time.time(); self.lock=threading.Lock()
    def take(self):
        with self.lock:
            now=time.time()
            self.tokens=min(self.capacity, self.tokens+(now-self.updated)*self.qps)
            self.updated=now
            if self.tokens>=1: self.tokens-=1; return True
            return False
pixel_bucket=TokenBucket(float(getattr(Config,"RATE_LIMIT_QPS_PIXEL",5)))
capi_bucket=TokenBucket(float(getattr(Config,"RATE_LIMIT_QPS_CAPI",5)))

@admin_bp.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        u = User.query.filter_by(username=request.form.get("username") or "").first()
        if u and u.check_password(request.form.get("password") or ""):
            login_user(u, remember=True); return redirect(url_for("admin.dashboard"))
        flash("Invalid credentials","danger")
    return render_template("admin/login.html")

@admin_bp.route("/logout")
@login_required
def logout():
    logout_user(); return redirect(url_for("admin.login"))

def send_pixel(event):
    if not pixel_enabled() or chaos_drop(): return ("dropped",0,None)
    start=time.time()
    time.sleep(0.003); latency=int((time.time()-start)*1000)
    try:
        ev=EventLog(ts=datetime.utcnow(), channel="pixel", event_name=_sg(event,"event_name","?"),
                    event_id=_sg(event,"event_id",str(uuid.uuid4())), status="ok", latency_ms=latency,
                    payload=json.dumps(event))
        db.session.add(ev); c=Counters.get_or_create(); c.pixel+=1
        dup=EventLog.query.filter_by(event_id=ev.event_id, channel="capi").first()
        if dup: c.dedup+=1
        db.session.commit()
        return ("ok",latency,None)
    except Exception as e:
        return ("error",0,str(e)[:500])

def _clean_ip(raw):
    if not raw: return None
    ip=raw.split(",")[0].strip()
    if "." in ip and ip.count(":")==1: ip=ip.split(":")[0]
    try: ipaddress.ip_address(ip); return ip
    except Exception: return None

def _ephemeral_fbp():
    return f"fb.1.{int(time.time())}.{random.randint(1000000000, 9999999999)}"

def send_capi(event, force_live=False):
    if not capi_enabled() or chaos_drop(): return ("dropped",0,None)
    start=time.time()
    try:
        ua=request.headers.get("User-Agent","") if request else "Mozilla/5.0"
        ip_raw=(request.headers.get("X-Forwarded-For","") or (request.remote_addr or "")) if request else ""
        fbp=request.cookies.get("_fbp") if request else None
        fbc=request.cookies.get("_fbc") if request else None
    except Exception:
        ua="Mozilla/5.0"; ip_raw=""; fbp=None; fbc=None
    if not ua: ua="Mozilla/5.0"
    clean_ip=_clean_ip(ip_raw)
    if not fbp: fbp=_ephemeral_fbp()

    url=f"https://graph.facebook.com/{getattr(Config,'GRAPH_VER','v20.0')}/{getattr(Config,'PIXEL_ID','')}/events"
    custom={"currency": _sg(event,"currency","USD"), "value": float(_sg(event,"value",0) or 0)}
    if "profit_margin" in event: custom["profit_margin"]=_sg(event,"profit_margin")
    if "pltv" in event: custom["pltv"]=_sg(event,"pltv")
    data={"data":[{
        "event_name": _sg(event,"event_name","?"),
        "event_time": int(time.time()),
        "event_id": _sg(event,"event_id",str(uuid.uuid4())),
        "action_source": "website",
        "event_source_url": getattr(Config,"BASE_URL","https://example.com"),
        "user_data": {
            "client_user_agent": ua,
            **({"client_ip_address": clean_ip} if clean_ip else {}),
            **({"fbp": fbp} if fbp else {}),
            **({"fbc": fbc} if fbc else {}),
        },
        "custom_data": custom
    }]}
    test_code=getattr(Config,"TEST_EVENT_CODE","")
    if test_code and use_test_code() and not force_live:
        data["test_event_code"]=test_code
    err=None
    try:
        while not capi_bucket.take(): time.sleep(0.02)
        if getattr(Config,"PIXEL_ID","") and getattr(Config,"ACCESS_TOKEN",""):
            resp=requests.post(url, params={"access_token": getattr(Config,"ACCESS_TOKEN","")}, json=data, timeout=12)
            ok=200<=resp.status_code<300; status="ok" if ok else f"http_{resp.status_code}"
            if not ok: err=(resp.text or "")[:1000]
        else:
            status="dry_run"
    except Exception as e:
        status="error"; err=str(e)[:1000]
    latency=int((time.time()-start)*1000)
    try:
        ev=EventLog(ts=datetime.utcnow(), channel="capi",
                    event_name=_sg(event,"event_name","?"),
                    event_id=_sg(event,"event_id",""),
                    status=status, latency_ms=latency, payload=json.dumps(data), error=err)
        db.session.add(ev)
        if status in ("ok","dry_run"):
            c=Counters.get_or_create(); c.capi+=1
            dup=EventLog.query.filter_by(event_id=ev.event_id, channel="pixel").first()
            if dup: c.dedup+=1
        db.session.commit()
    except Exception: pass
    return (status,latency,err)

@admin_bp.route("/")
@login_required
def dashboard():
    KVStore.set("build_number","v1.4.11")
    c=Counters.get_or_create()
    build=KVStore.get("build_number","v1.4.11")
    recent=EventLog.query.order_by(desc(EventLog.ts)).limit(20).all()
    defaults={"PageView":1.5,"ViewContent":2.0,"AddToCart":3.5,"InitiateCheckout":4.0,"AddPaymentInfo":5.0,"Purchase":6.0}
    user_intervals={n: float(KVStore.get(f"interval_{n}", d)) for n,d in defaults.items()}
    chaos={"drop": chaos_drop(), "omit": chaos_omit(), "malformed": chaos_malformed()}
    return render_template("admin/dashboard.html", counters=c, build=build, recent=recent, events=EVENT_NAMES,
                           intervals=user_intervals, chaos=chaos,
                           auto_pixel=get_auto_pixel(), auto_capi=get_auto_capi(), use_test_code=use_test_code(),
                           pct_profit_margin=pct_margin(), pct_pltv=pct_pltv())

@admin_bp.route("/api/settings", methods=["POST"])
@login_required
def api_settings():
    data=request.get_json(silent=True) or {}
    if "automation_pixel" in data: KVStore.set("automation_pixel","1" if data["automation_pixel"] else "0")
    if "automation_capi" in data:  KVStore.set("automation_capi","1" if data["automation_capi"] else "0")
    if "use_test_event_code" in data: KVStore.set("use_test_event_code","1" if data["use_test_event_code"] else "0")
    if "pct_profit_margin" in data:
        try: KVStore.set("pct_profit_margin", str(max(0,min(100,int(data["pct_profit_margin"]))))) 
        except Exception: pass
    if "pct_pltv" in data:
        try: KVStore.set("pct_pltv", str(max(0,min(100,int(data["pct_pltv"]))))) 
        except Exception: pass
    for n in EVENT_NAMES:
        k=f"interval_{n}"
        if k in data:
            try: KVStore.set(k, str(float(data[k])))
            except Exception: pass
    return {"ok":True}

@admin_bp.route("/api/chaos", methods=["POST"])
@login_required
def api_chaos():
    data=request.get_json(silent=True) or {}
    for k in ("chaos_drop","chaos_omit","chaos_malformed"):
        if k in data: KVStore.set(k, "1" if bool(data[k]) else "0")
    return {"ok":True}

@admin_bp.route("/api/manual_send", methods=["POST"])
@login_required
def manual_send():
    try:
        body = request.get_json(silent=True)
        if body is None:
            raw = request.get_data(as_text=True) or ""
            body = json.loads(raw) if raw.strip() else {}
        payload=_as_dict(body)
        if "event_name" not in payload: payload["event_name"]="PageView"
        if "event_id" not in payload:   payload["event_id"]=str(uuid.uuid4())
        if "currency" not in payload:   payload["currency"]="USD"
        if "value" in payload:
            try: payload["value"]=float(payload["value"])
            except Exception: payload["value"]=0.0
        if chaos_omit(): payload.pop("currency", None)
        if chaos_malformed(): payload["value"]="NaN"
        force_live=(request.args.get("live")=="1")
        p_status=send_pixel(payload)
        c_status=send_capi(payload, force_live=force_live)
        return jsonify({"ok":True, "pixel":p_status[0], "capi":c_status[0]})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}),500

AUTOMATION_THREADS={}
AUTOMATION_STOP=threading.Event()

def _safe_float(v, default):
    try: return float(v)
    except Exception:
        try: return float(str(v).strip())
        except Exception: return float(default)

def automation_worker(app, event_name, interval_s):
    with app.app_context():
        while not AUTOMATION_STOP.is_set():
            payload={"event_name":event_name,"event_id":str(uuid.uuid4()),"currency":"USD"}
            if event_name=="Purchase":
                price=_safe_float(random.uniform(20,200),50)
                cost=price*random.uniform(margin_min(), margin_max())
                payload["value"]=price
                if random.randint(1,100)<=pct_margin():
                    payload["profit_margin"]=round(max(0,price-cost),2)
                if pltv_randomized() and (random.randint(1,100)<=pct_pltv()):
                    payload["pltv"]=round(random.uniform(pltv_min(), pltv_max()),2)
            else:
                payload["value"]=0.0
            if get_auto_pixel(): 
                try: send_pixel(payload)
                except Exception: pass
            if get_auto_capi():
                try: send_capi(payload)
                except Exception: pass
            time.sleep(max(0.25, _safe_float(interval_s,1.0)))

@admin_bp.route("/api/automation", methods=["POST"])
@login_required
def api_automation():
    data=request.get_json(silent=True) or {}
    cmd=data.get("cmd")
    if cmd=="start":
        defaults={"PageView":1.5,"ViewContent":2.0,"AddToCart":3.5,"InitiateCheckout":4.0,"AddPaymentInfo":4.5,"Purchase":6.0}
        intervals={}
        for n,d in defaults.items():
            k=f"interval_{n}"
            intervals[n]=_safe_float(data.get("intervals",{}).get(k, KVStore.get(k,d)), d)
            KVStore.set(k, str(intervals[n]))
        if AUTOMATION_THREADS and not AUTOMATION_STOP.is_set():
            return {"ok":True,"running":True,"threads":list(AUTOMATION_THREADS.keys()),"intervals":intervals}
        AUTOMATION_STOP.clear()
        app=current_app._get_current_object()
        for n,iv in intervals.items():
            t=threading.Thread(target=automation_worker, args=(app,n,iv), daemon=True)
            t.start(); AUTOMATION_THREADS[n]=t
        return {"ok":True,"running":True,"threads":list(AUTOMATION_THREADS.keys()),"intervals":intervals}
    elif cmd=="stop":
        AUTOMATION_STOP.set()
        for k,t in list(AUTOMATION_THREADS.items()):
            try: t.join(timeout=0.2)
            except Exception: pass
        AUTOMATION_THREADS.clear()
        return {"ok":True,"stopped":True}
    return {"ok":False,"error":"unknown cmd"},400

@admin_bp.route("/api/automation/ping", methods=["POST"])
@login_required
def api_automation_ping():
    payload={"event_name":"Purchase","event_id":str(uuid.uuid4()),"currency":"USD","value":99.0,"profit_margin":10.0}
    send_pixel(payload); send_capi(payload); return {"ok":True}

@admin_bp.route("/api/automation_status")
@login_required
def api_automation_status():
    running=bool(AUTOMATION_THREADS) and not AUTOMATION_STOP.is_set()
    return jsonify({"ok":True,"running":running,
                    "threads": list(AUTOMATION_THREADS.keys()),
                    "automation_pixel": get_auto_pixel(),
                    "automation_capi": get_auto_capi(),
                    "use_test_event_code": use_test_code(),
                    "chaos_drop": chaos_drop(),
                    "chaos_omit": chaos_omit(),
                    "chaos_malformed": chaos_malformed(),
                    "pct_profit_margin": pct_margin(),
                    "pct_pltv": pct_pltv()})

@admin_bp.route("/api/counters")
@login_required
def api_counters():
    c=Counters.get_or_create()
    margin_events = db.session.query(func.count(EventLog.id)).filter(EventLog.payload.contains('"profit_margin"')).scalar() or 0
    pltv_events   = db.session.query(func.count(EventLog.id)).filter(EventLog.payload.contains('"pltv"')).scalar() or 0
    return {"ok":True,"pixel":c.pixel,"capi":c.capi,"dedup":c.dedup,"margin_events":int(margin_events),"pltv_events":int(pltv_events)}

@admin_bp.route("/api/health")
@login_required
def api_health():
    px=getattr(Config,'PIXEL_ID',''); at=getattr(Config,'ACCESS_TOKEN',''); gv=getattr(Config,'GRAPH_VER',''); bu=getattr(Config,'BASE_URL','')
    return jsonify({"ok":True,"pixel_id_present":bool(px),"access_token_present":bool(at),"graph_version":gv,"base_url":bu})

@admin_bp.route("/api/pixel-check", methods=["POST"])
@login_required
def pixel_check():
    import os, requests as rq
    candidates=[]
    port=os.getenv("PORT")
    if port: candidates.append(f"http://127.0.0.1:{port}/")
    base=(getattr(Config,'BASE_URL','') or '').rstrip("/")
    if base.startswith("http"): candidates.append(f"{base}/")
    try:
        if request and request.host_url: candidates.append(request.host_url)
    except Exception: pass
    last_err=None
    for url in candidates:
        try:
            resp=rq.get(url, timeout=8)
            html=resp.text.lower()
            has_meta_noindex=('name="robots"' in html) or ('noindex' in html)
            has_pixel_snippet=("window.demopixel" in html) or ("/static/js/pixel.js" in html)
            return {"ok":True,"source":url,"has_meta_noindex":has_meta_noindex,"has_pixel_snippet":has_pixel_snippet}
        except Exception as e:
            last_err=str(e)[:200]; continue
    return {"ok":False,"error": last_err or "unable to fetch any candidate URL"}

@admin_bp.route("/request-inspector")
@login_required
def request_inspector():
    logs=EventLog.query.order_by(desc(EventLog.ts)).limit(100).all()
    return render_template("admin/request_inspector.html", logs=logs)

@admin_bp.route("/logs")
@login_required
def logs_view():
    logs=EventLog.query.order_by(desc(EventLog.ts)).limit(500).all()
    return render_template("admin/logs.html", logs=logs)
