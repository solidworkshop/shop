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
        const ap = $('#autoPixel'); if (ap) ap.checked = !!s.automation_pixel;
        const ac = $('#autoCapi');  if (ac) ac.checked = !!s.automation_capi;
      }
    } catch(e) {
      // ignore
    } finally {
      setTimeout(poll, 1500);
    }
  }

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
  const startBtn = $('#startAuto');
  if (startBtn) startBtn.addEventListener('click', async ()=>{
    const body = { cmd:'start', intervals: gatherIntervals() };
    await fetch('/admin/api/automation', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
  });
  const stopBtn = $('#stopAuto');
  if (stopBtn) stopBtn.addEventListener('click', async ()=>{
    await fetch('/admin/api/automation', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ cmd:'stop' }) });
  });

  // Channel toggles (automation only)
  const autoPixel = $('#autoPixel');
  if (autoPixel) autoPixel.addEventListener('change', async ()=>{
    await fetch('/admin/api/settings', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ automation_pixel: autoPixel.checked }) });
  });
  const autoCapi = $('#autoCapi');
  if (autoCapi) autoCapi.addEventListener('change', async ()=>{
    await fetch('/admin/api/settings', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ automation_capi: autoCapi.checked }) });
  });

  // Pixel checker
  const pixelBtn = $('#pixelCheckBtn'), pixelOut = $('#pixelCheckResult');
  if (pixelBtn) pixelBtn.addEventListener('click', async ()=>{
    pixelOut.textContent = 'Checking...';
    try{
      const r = await fetch('/admin/api/pixel-check', {method:'POST'});
      const j = await r.json();
      if (j.ok) {
        pixelOut.textContent = `source: ${j.source} · noindex: ${j.has_meta_noindex ? 'yes' : 'no'} · pixel snippet: ${j.has_pixel_snippet ? 'yes' : 'no'}`;
      } else {
        pixelOut.textContent = 'Error: ' + (j.error || 'unknown');
      }
    } catch(e){
      pixelOut.textContent = 'Error: ' + e;
    }
  });

  // Start polling
  poll();
})();
