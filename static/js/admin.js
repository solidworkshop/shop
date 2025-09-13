
function q(sel){return document.querySelector(sel)}
async function apiPost(url, body=null){
  const res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: body?JSON.stringify(body):null});
  const txt = await res.text(); try{ return {ok:res.ok, status:res.status, json:JSON.parse(txt)} }catch(e){ return {ok:res.ok, status:res.status, text:txt} }
}
async function saveKV(k,v){ await fetch('/admin/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({[k]: v})}); }
async function startIntervals(){ const r = await apiPost('/admin/automation/start'); }
async function stopIntervals(){ const r = await apiPost('/admin/automation/stop'); }
function setBadge(id, state){ const el=q(id); if(!el) return; const map={true:'success', false:'secondary'}; el.className='badge text-bg-'+(map[!!state]||'secondary'); el.textContent=state?'running':'stopped'; }
async function pollAutomation(){
  try{ const r = await fetch('/admin/automation/status'); const d = await r.json(); setBadge('#automation-status', d.running); const th=q('#thread-count'); if(th) th.textContent=d.threads; }catch(e){}
}
async function pollCounters(){
  try{
    const r = await fetch('/admin/counters'); const d = await r.json();
    for(const k of ['pixel','capi','deduped','margin_events','pltv_events']){
      const el = document.getElementById('cnt-'+k); if(el) el.textContent = d[k];
    }
    setBadge('#automation-status', d.running); const th=q('#thread-count'); if(th) th.textContent=d.threads;
  }catch(e){}
}
setInterval(pollAutomation, 3000);
setInterval(pollCounters, 3000);
async function runPixelCheck(){ const r = await fetch('/admin/pixel-check'); q('#pixel-check-res').textContent = await r.text(); }
async function manualSend(){
  try{
    const txt = q('#manual-json').value; const dry = q('#dry-run').checked;
    const body = JSON.parse(txt); if(dry) body.dry_run=true;
    const r = await fetch('/admin/manual_send', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    q('#manual-res').textContent = await r.text();
  }catch(e){ q('#manual-res').textContent = 'Invalid JSON: ' + e; }
}
