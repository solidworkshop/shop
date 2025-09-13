(function(){
  const $ = (sel)=>document.querySelector(sel);

  // Live counters + status
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
        set('#sumMargin', (c.margin_sum||0).toFixed(2));
        set('#sumPLTV', (c.pltv_sum||0).toFixed(2));
      }
      if (s && s.ok) {
        const st = $('#autoStatus');
        if (st) {
          st.className = 'badge ' + (s.running ? 'text-bg-success' : 'text-bg-secondary');
          st.textContent = 'Automation: ' + (s.running ? 'Running' : 'Stopped');
        }
      }
    } catch(e) {
      // swallow
    } finally {
      setTimeout(poll, 1500);
    }
  }

  // Wire automation buttons
  function gatherIntervals() {
    const names = ['PageView','ViewContent','AddToCart','InitiateCheckout','AddPaymentInfo','Purchase'];
    const obj = {};
    names.forEach(n=>{
      const el = document.getElementById('interval_'+n);
      if (el) obj['interval_'+n] = parseFloat(el.value||'0') || 1.0;
    });
    return obj;
  }

  const startBtn = $('#startAuto');
  if (startBtn) startBtn.addEventListener('click', async ()=>{
    const body = { cmd:'start', intervals: gatherIntervals() };
    const r = await fetch('/admin/api/automation', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body)
    });
    await r.json();
  });

  const stopBtn = $('#stopAuto');
  if (stopBtn) stopBtn.addEventListener('click', async ()=>{
    const r = await fetch('/admin/api/automation', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ cmd:'stop' })
    });
    await r.json();
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

  // Kick off polling
  poll();
})();
