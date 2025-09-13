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
      if (j.ok && j.running){
        note('Automation started ✓', 'success');
      } else {
        note('Start failed: ' + (j.error || 'unknown'), 'danger');
      }
    } catch(e){
      note('Request error: '+e, 'danger');
    } finally {
      btn.disabled = false;
      refreshStatus();
    }
  });

  $('#stopAuto')?.addEventListener('click', async ()=>{
    const btn = $('#stopAuto'); btn.disabled = true;
    note('Stopping…');
    try{
      const r = await fetch('/admin/api/automation', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ cmd:'stop' }) });
      const j = await r.json();
      if (j.ok){
        note('Automation stopped', 'secondary');
      } else {
        note('Stop failed: ' + (j.error || 'unknown'), 'danger');
      }
    } catch(e){
      note('Request error: '+e, 'danger');
    } finally {
      btn.disabled = false;
      refreshStatus();
    }
  });

  $('#pingAuto')?.addEventListener('click', async ()=>{
    const btn = $('#pingAuto'); btn.disabled = true;
    try{
      const r = await fetch('/admin/api/automation/ping', { method:'POST' });
      const j = await r.json();
      if (j.ok) note('One Purchase event sent ✓', 'success');
      else note('Ping failed', 'danger');
    }finally{
      btn.disabled = false;
    }
  });

  // Manual validate & send (kept)
  $('#btnValidate')?.addEventListener('click', ()=>{
    const txt = $('#manualJson').value || '';
    try { const obj = JSON.parse(txt); if (!obj.event_name || !obj.event_id) throw new Error('Missing event_name or event_id'); note('Valid ✓','success'); }
    catch(e){ note('Invalid JSON: ' + e.message, 'danger'); }
  });
  $('#btnSend')?.addEventListener('click', async ()=>{
    const txt = $('#manualJson').value || '';
    try{ JSON.parse(txt); } catch(e){ note('Invalid JSON: ' + e.message, 'danger'); return; }
    const r = await fetch('/admin/api/manual_send', { method:'POST', headers:{'Content-Type':'application/json'}, body: txt });
    const t = await r.text();
    note('HTTP '+r.status+' — '+t.slice(0,200), r.ok?'success':'danger');
  });

  // Counters poll
  async function poll() {
    try {
      const [cRes, sRes] = await Promise.all([
        fetch('/admin/api/counters'),
        fetch('/admin/api/automation_status')
      ]);
      const c = await cRes.json();
      const s = await sRes.json();

      if (c && c.ok) {
        const set = (id,val)=>{ const el=$(id); if(el) el.textContent = val; };
        set('#countPixel', c.pixel);
        set('#countCapi', c.capi);
        set('#countDedup', c.dedup);
        set('#countMarginEvents', c.margin_events || 0);
        set('#countPLTVEvents', c.pltv_events || 0);
      }
      if (s && s.ok) {
        const st = $('#autoStatus');
        if (st) {
          st.className = 'badge ' + (s.running ? 'text-bg-success' : 'text-bg-secondary');
          st.textContent = 'Automation: ' + (s.running ? 'Running' : 'Stopped');
        }
      }
    } catch(e) {} finally {
      setTimeout(poll, 1500);
    }
  }

  refreshStatus();
  poll();
})();
