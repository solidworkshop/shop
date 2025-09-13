
import os, json, time, uuid, random, ipaddress
import requests
from urllib.parse import urljoin
from flask import request
from extensions import db
from models import KVStore, EventLog

def graph_url(path=''):
    base = 'https://graph.facebook.com/'
    ver = (os.getenv('GRAPH_VER') or KVStore.get('graph_ver','v18.0') or 'v18.0')
    ver = 'v' + str(ver).lstrip('v')
    return urljoin(base, ver + '/' + path.lstrip('/'))

def get_pixel_id():
    return os.getenv('PIXEL_ID') or KVStore.get('pixel_id', '') or ''

def get_access_token():
    return os.getenv('ACCESS_TOKEN') or KVStore.get('access_token', '') or ''

def get_test_event_code():
    return os.getenv('TEST_EVENT_CODE') or KVStore.get('test_event_code', '') or ''

def chaos_enabled():
    return KVStore.get('chaos_enabled','0') == '1'

def chaos_behavior():
    # returns dict with flags: drop, omit_user_data, malformed
    return {
        "drop": KVStore.get('chaos_drop','0') == '1',
        "omit_user_data": KVStore.get('chaos_omit_ud','0') == '1',
        "malformed": KVStore.get('chaos_malformed','0') == '1',
    }

def should_attach_margin():
    try:
        pct = int(KVStore.get('pct_margin','100'))
    except Exception:
        pct = 100
    return random.randint(1,100) <= max(0, min(100, pct))

def should_attach_pltv():
    try:
        pct = int(KVStore.get('pct_pltv','100'))
    except Exception:
        pct = 100
    return random.randint(1,100) <= max(0, min(100, pct))

def profit_margin(price: float):
    # price – random cost% with min/max sliders (stored in KV)
    try:
        mn = float(KVStore.get('margin_min','10'))
        mx = float(KVStore.get('margin_max','50'))
        if mn > mx: mn, mx = mx, mn
        pct = random.uniform(mn, mx)
        cost = price * pct/100.0
        return max(0.0, price - cost)
    except Exception:
        return 0.0

def build_user_data():
    omit = chaos_behavior().get("omit_user_data", False)
    if omit:
        return {}
    # Minimal recommended: client_ip_address, client_user_agent; include fbp/fbc if present
    ua = request.headers.get('User-Agent', 'python-requests/2.x')
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '127.0.0.1')
    try:
        # take first IPv4 if list
        ip = [p.strip() for p in (ip or '').split(',')][0] or '127.0.0.1'
        ipaddress.ip_address(ip)
    except Exception:
        ip = '127.0.0.1'
    fbp = request.cookies.get('_fbp')
    fbc = request.args.get('fbclid')
    ud = {
        "client_ip_address": ip,
        "client_user_agent": ua,
    }
    if fbp: ud["fbp"] = fbp
    if fbc: ud["fbc"] = f"fb.1.{int(time.time())}.{fbc}"
    # Hashable identifiers if form provided (optional)
    email = request.args.get('em') or request.form.get('em')
    phone = request.args.get('ph') or request.form.get('ph')
    if email: ud["em"] = email
    if phone: ud["ph"] = phone
    return ud

def send_capi_event(event_name, event_id, custom_data):
    if chaos_enabled() and chaos_behavior().get("drop"):
        # Simulate a drop: do not send
        _log("capi", event_name, event_id, "dropped", 0, json.dumps(custom_data), "chaos_drop")
        return {"ok": True, "dropped": True}

    pixel_id = get_pixel_id()
    token = get_access_token()
    if not pixel_id or not token:
        _log("capi", event_name, event_id, "skipped", 0, json.dumps(custom_data), "missing_pixel_or_token")
        return {"ok": False, "error": "missing_pixel_or_token"}

    url = graph_url(f"{pixel_id}/events")
    payload = {
        "data": [{
            "event_name": event_name,
            "event_time": int(time.time()),
            "event_id": event_id,
            "action_source": "website",
            "user_data": {} if chaos_behavior().get("omit_user_data") else build_user_data(),
            "custom_data": custom_data
        }]
    }
    tec = get_test_event_code()
    if tec: payload["test_event_code"] = tec

    if chaos_behavior().get("malformed"):
        payload = {"oops": "bad"}  # invalid payload to exercise error paths

    t0 = time.time()
    try:
        r = requests.post(url, params={"access_token": token}, json=payload, timeout=8)
        dt = int((time.time()-t0)*1000)
        ok = r.status_code in (200, 201)
        if not ok:
            _log("capi", event_name, event_id, f"http_{r.status_code}", dt, json.dumps(payload), r.text[:2000])
        else:
            _log("capi", event_name, event_id, "ok", dt, json.dumps(payload), "")
        return {"ok": ok, "status": r.status_code, "resp": r.text}
    except Exception as e:
        dt = int((time.time()-t0)*1000)
        _log("capi", event_name, event_id, "exception", dt, json.dumps(payload), str(e)[:1000])
        return {"ok": False, "error": str(e)}

def _log(channel, event_name, event_id, status, latency_ms, payload, error):
    try:
        row = EventLog(channel=channel, event_name=event_name, event_id=event_id, status=str(status),
                       latency_ms=int(latency_ms or 0), payload=payload, error=error)
        db.session.add(row); db.session.commit()
    except Exception:
        pass
