(function(){
  const $ = (sel)=>document.querySelector(sel);
  function note(msg, cls='info'){
    const box = $('#autoMsg');
    if (!box) return;
    box.className = 'alert alert-' + cls + ' py-2 px-3 small';
    box.textContent = msg;
    box.style.display = 'block';
  }
  async function refreshStatus(){
    try{
      const r = await fetch('/admin/api/automation_status');
      const j = await r.json();
      const st = $('#autoStatus');
      if (st) {
        st.className = 'badge ' + (j.running ? 'text-bg-success' : 'text-bg-secondary');
        st.textContent = 'Automation: ' + (j.running ? 'Running' : 'Stopped');
      }
      if ($('#autoPixel')) $('#autoPixel').checked = !!j.automation_pixel;
      if ($('#autoCapi')) $('#autoCapi').checked = !!j.automation_capi;
      if ($('#useTestCode')) $('#useTestCode').checked = !!j.use_test_event_code;
      if ($('#chaos_drop')) $('#chaos_drop').checked = !!j.chaos_drop;
      if ($('#chaos_omit')) $('#chaos_omit').checked = !!j.chaos_omit;
      if ($('#chaos_malformed')) $('#chaos_malformed').checked = !!j.chaos_malformed;
    }catch(e){}
  }
  function gatherIntervals() {
    const names = ['PageView','ViewContent','AddToCart','InitiateCheckout','AddPaymentInfo','Purchase'];
    const obj = {};
    names.forEach(n=>{
      const el = document.getElementById('interval_'+n);
      const v = parseFloat(el?.value || '0');
      obj['interval_'+n] = (isFinite(v) && v>0) ? v : 1.0;
    });
    return obj;
  }
  $('#startAuto')?.addEventListener('click', async ()=>{
    const btn = $('#startAuto'); btn.disabled = true;
    note('Starting automation…');
    try{
      const body = { cmd:'start', intervals: gatherIntervals() };
      const r = await fetch('/admin/api/automation', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
      const j = await r.json();
      if (j.ok && j.running){ note('Automation started ✓', 'success'); }
      else { note('Start failed: ' + (j.error || 'unknown'), 'danger'); }
    } catch(e){ note('Request error: '+e, 'danger'); }
    finally { btn.disabled = false; refreshStatus(); }
  });
  $('#stopAuto')?.addEventListener('click', async ()=>{
    const btn = $('#stopAuto'); btn.disabled = true;
    note('Stopping…');
    try{
      const r = await fetch('/admin/api/automation', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ cmd:'stop' }) });
      const j = await r.json();
      if (j.ok){ note('Automation stopped', 'secondary'); }
      else { note('Stop failed: ' + (j.error || 'unknown'), 'danger'); }
    } catch(e){ note('Request error: '+e, 'danger'); }
    finally { btn.disabled = false; refreshStatus(); }
  });
  $('#pingAuto')?.addEventListener('click', async ()=>{
    const btn = $('#pingAuto'); btn.disabled = true;
    try{
      const r = await fetch('/admin/api/automation/ping', { method:'POST' });
      const j = await r.json();
      if (j.ok) note('One Purchase event sent ✓', 'success');
      else note('Ping failed', 'danger');
    }finally{ btn.disabled = false; }
  });
  function postJSON(url, obj){ return fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(obj)}); }
  $('#autoPixel')?.addEventListener('change', e=> postJSON('/admin/api/settings',{automation_pixel:e.target.checked}));
  $('#autoCapi')?.addEventListener('change', e=> postJSON('/admin/api/settings',{automation_capi:e.target.checked}));
  $('#useTestCode')?.addEventListener('change', e=> postJSON('/admin/api/settings',{use_test_event_code:e.target.checked}));
  $('#chaos_drop')?.addEventListener('change', e=> postJSON('/admin/api/chaos',{chaos_drop:e.target.checked}));
  $('#chaos_omit')?.addEventListener('change', e=> postJSON('/admin/api/chaos',{chaos_omit:e.target.checked}));
  $('#chaos_malformed')?.addEventListener('change', e=> postJSON('/admin/api/chaos',{chaos_malformed:e.target.checked}));
  $('#pct_profit_margin')?.addEventListener('change', e=>{
    const v = Math.max(0, Math.min(100, parseInt(e.target.value || '0', 10)));
    e.target.value = v; postJSON('/admin/api/settings',{pct_profit_margin:v});
  });
  $('#pct_pltv')?.addEventListener('change', e=>{
    const v = Math.max(0, Math.min(100, parseInt(e.target.value || '0', 10)));
    e.target.value = v; postJSON('/admin/api/settings',{pct_pltv:v});
  });
  // Manual send
  $('#btnValidate')?.addEventListener('click', ()=>{
    const txt = (document.querySelector('#manualJson')?.value)||'';
    try { const o = JSON.parse(txt); if(!o.event_name||!o.event_id) throw new Error('Missing event_name or event_id'); 
      document.querySelector('#manualResult').textContent='Valid ✓';
    } catch(e){ document.querySelector('#manualResult').textContent='Invalid JSON: '+e.message; }
  });
  $('#btnSend')?.addEventListener('click', async ()=>{
    const txt = (document.querySelector('#manualJson')?.value)||'';
    try{ JSON.parse(txt); } catch(e){ document.querySelector('#manualResult').textContent='Invalid JSON: '+e.message; return; }
    const r = await fetch('/admin/api/manual_send', { method:'POST', headers:{'Content-Type':'application/json'}, body: txt });
    const t = await r.text();
    try{ document.querySelector('#manualResult').textContent = 'HTTP '+r.status+' — '+JSON.stringify(JSON.parse(t), null, 2); }
    catch{ document.querySelector('#manualResult').textContent = 'HTTP '+r.status+' — '+t; }
  });
  $('#btnSendLive')?.addEventListener('click', async ()=>{
    let txt = (document.querySelector('#manualJson')?.value)||'';
    if (!txt.trim()){
      const id = 'live-' + Math.random().toString(36).slice(2);
      txt = JSON.stringify({event_name:'Purchase', event_id:id, currency:'USD', value:Math.round(Math.random()*200+20)});
    }
    try{ JSON.parse(txt); } catch(e){ document.querySelector('#manualResult').textContent='Invalid JSON: '+e.message; return; }
    const r = await fetch('/admin/api/manual_send?live=1', { method:'POST', headers:{'Content-Type':'application/json'}, body: txt });
    const t = await r.text();
    try{ document.querySelector('#manualResult').textContent = 'HTTP '+r.status+' — '+JSON.stringify(JSON.parse(t), null, 2); }
    catch{ document.querySelector('#manualResult').textContent = 'HTTP '+r.status+' — '+t; }
  });
  // Health/Pixel check
  $('#pixelCheckBtn')?.addEventListener('click', async ()=>{
    const out = document.querySelector('#pixelCheckResult'); out.textContent='Checking…';
    try{
      const r = await fetch('/admin/api/pixel-check', {method:'POST'});
      const j = await r.json(); const stamp = new Date().toISOString();
      if (j.ok) out.textContent = `[${stamp}] source: ${j.source} · noindex: ${j.has_meta_noindex ? 'yes' : 'no'} · pixel snippet: ${j.has_pixel_snippet ? 'yes' : 'no'}`;
      else out.textContent = `[${stamp}] Error: ${j.error || 'unknown'}`;
    }catch(e){ out.textContent='Error: '+e; }
  });
  document.querySelector('#btnHealth')?.addEventListener('click', async ()=>{
    const r = await fetch('/admin/api/health'); const j = await r.json();
    document.querySelector('#healthOut').textContent = JSON.stringify(j, null, 2);
  });
  // Poll
  async function poll(){
    try{
      const [cRes, sRes] = await Promise.all([ fetch('/admin/api/counters'), fetch('/admin/api/automation_status') ]);
      const c = await cRes.json(); const s = await sRes.json();
      if (c && c.ok){
        const set = (id,val)=>{ const el=$(id); if(el) el.textContent = val; };
        set('#countPixel', c.pixel); set('#countCapi', c.capi); set('#countDedup', c.dedup);
        set('#countMarginEvents', c.margin_events||0); set('#countPLTVEvents', c.pltv_events||0);
      }
      if (s && s.ok){
        const st = $('#autoStatus');
        if (st){ st.className = 'badge ' + (s.running ? 'text-bg-success' : 'text-bg-secondary');
                 st.textContent = 'Automation: ' + (s.running ? 'Running' : 'Stopped'); }
      }
    }catch(e){} finally { setTimeout(poll, 1500); }
  }
  refreshStatus(); poll();
})();