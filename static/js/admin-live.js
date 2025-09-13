(function(){
  const $ = (sel)=>document.querySelector(sel);

  async function poll() {
    try {
      const [cRes, sRes] = await Promise.all([
        fetch('/admin/api/counters', {credentials:'same-origin'}),
        fetch('/admin/api/automation_status', {credentials:'same-origin'})
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
        $('#autoPixel') && ($('#autoPixel').checked = !!s.automation_pixel);
        $('#autoCapi') && ($('#autoCapi').checked = !!s.automation_capi);
        $('#useTestCode') && ($('#useTestCode').checked = !!s.use_test_event_code);
        $('#pct_profit_margin') && ($('#pct_profit_margin').value = s.pct_profit_margin ?? $('#pct_profit_margin').value);
        $('#pct_pltv') && ($('#pct_pltv').value = s.pct_pltv ?? $('#pct_pltv').value);
      }
    } catch(e) {
      // ignore
    } finally {
      setTimeout(poll, 1500);
    }
  }

  // Intervals helpers
  function gatherIntervals() {
    const names = ['PageView','ViewContent','AddToCart','InitiateCheckout','AddPaymentInfo','Purchase'];
    const obj = {};
    names.forEach(n=>{
      const el = document.getElementById('interval_'+n);
      if (el) obj['interval_'+n] = parseFloat(el.value||'0') || 1.0;
    });
    return obj;
  }

  // Start/Stop
  $('#startAuto')?.addEventListener('click', async ()=>{
    const body = { cmd:'start', intervals: gatherIntervals() };
    await fetch('/admin/api/automation', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
  });
  $('#stopAuto')?.addEventListener('click', async ()=>{
    await fetch('/admin/api/automation', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ cmd:'stop' }) });
  });

  // Channel toggles & test code
  $('#autoPixel')?.addEventListener('change', async (e)=>{
    await fetch('/admin/api/settings', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ automation_pixel: e.target.checked }) });
  });
  $('#autoCapi')?.addEventListener('change', async (e)=>{
    await fetch('/admin/api/settings', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ automation_capi: e.target.checked }) });
  });
  $('#useTestCode')?.addEventListener('change', async (e)=>{
    await fetch('/admin/api/settings', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ use_test_event_code: e.target.checked }) });
  });

  // Percent controls
  $('#pct_profit_margin')?.addEventListener('change', async (e)=>{
    const v = Math.max(0, Math.min(100, parseInt(e.target.value || '0', 10)));
    e.target.value = v;
    await fetch('/admin/api/settings', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ pct_profit_margin: v }) });
  });
  $('#pct_pltv')?.addEventListener('change', async (e)=>{
    const v = Math.max(0, Math.min(100, parseInt(e.target.value || '0', 10)));
    e.target.value = v;
    await fetch('/admin/api/settings', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ pct_pltv: v }) });
  });

  // Chaos toggles
  async function setChaos(key, value){
    await fetch('/admin/api/chaos', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ [key]: value })});
  }
  $('#chaos_drop')?.addEventListener('change', e=> setChaos('chaos_drop', e.target.checked));
  $('#chaos_omit')?.addEventListener('change', e=> setChaos('chaos_omit', e.target.checked));
  $('#chaos_malformed')?.addEventListener('change', e=> setChaos('chaos_malformed', e.target.checked));

  // Manual Validate & Send
  $('#btnValidate')?.addEventListener('click', ()=>{
    const txt = $('#manualJson').value || '';
    try {
      const obj = JSON.parse(txt);
      if (!obj.event_name) throw new Error('Missing "event_name"');
      if (!obj.event_id) throw new Error('Missing "event_id"');
      $('#manualResult').textContent = 'Valid ✓';
    } catch(e){
      $('#manualResult').textContent = 'Invalid JSON: ' + e.message;
    }
  });
  $('#btnSend')?.addEventListener('click', async ()=>{
    const txt = $('#manualJson').value || '';
    try{ JSON.parse(txt); } catch(e){ $('#manualResult').textContent = 'Invalid JSON: ' + e.message; return; }
    const r = await fetch('/admin/api/manual_send', { method:'POST', headers:{'Content-Type':'application/json'}, body: txt });
    const t = await r.text();
    try{ $('#manualResult').textContent = 'HTTP '+r.status+' — '+JSON.stringify(JSON.parse(t), null, 2); }
    catch{ $('#manualResult').textContent = 'HTTP '+r.status+' — '+t; }
  });
  $('#btnSendLive')?.addEventListener('click', async ()=>{
    // force a live purchase with a new ID even if UI textarea is empty
    let txt = $('#manualJson').value || '';
    if (!txt.trim()){
      const id = 'live-' + Math.random().toString(36).slice(2);
      txt = JSON.stringify({event_name:'Purchase', event_id:id, currency:'USD', value:Math.round(Math.random()*200+20)});
    }
    try{ JSON.parse(txt); } catch(e){ $('#manualResult').textContent = 'Invalid JSON: ' + e.message; return; }
    const r = await fetch('/admin/api/manual_send?live=1', { method:'POST', headers:{'Content-Type':'application/json'}, body: txt });
    const t = await r.text();
    try{ $('#manualResult').textContent = 'HTTP '+r.status+' — '+JSON.stringify(JSON.parse(t), null, 2); }
    catch{ $('#manualResult').textContent = 'HTTP '+r.status+' — '+t; }
  });

  // Health summary
  $('#btnHealth')?.addEventListener('click', async ()=>{
    const r = await fetch('/admin/api/health');
    const j = await r.json();
    $('#healthOut').textContent = JSON.stringify(j, null, 2);
  });

  // Start polling
  poll();
})();
