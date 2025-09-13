
async function apiPost(url, body=null){
  const res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: body?JSON.stringify(body):null});
  const txt = await res.text();
  try { return {ok: res.ok, status: res.status, json: JSON.parse(txt)}; } catch { return {ok: res.ok, status: res.status, text: txt}; }
}
async function startIntervals(){
  const r = await apiPost('/admin/automation/start');
  updateStatus(r.ok && r.json && r.json.ok ? 'running':'error');
}
async function stopIntervals(){
  const r = await apiPost('/admin/automation/stop');
  updateStatus(r.ok && r.json && r.json.ok ? 'stopped':'error');
}
function updateStatus(state){
  const el = document.getElementById('automation-status');
  if(!el) return;
  const map = {running:'success', stopped:'secondary', error:'danger'};
  el.className = 'badge text-bg-' + (map[state]||'secondary');
  el.textContent = state;
}
async function pollAutomation(){
  try{
    const r = await fetch('/admin/automation/status'); const d = await r.json();
    updateStatus(d.running ? 'running':'stopped');
  }catch(e){}
}
async function pollCounters(){
  try{
    const r = await fetch('/admin/counters'); const d = await r.json();
    for(const k of ['pixel','capi','deduped','margin_events','pltv_events']){
      const el = document.getElementById('cnt-'+k); if(el) el.textContent = d[k];
    }
  }catch(e){}
}
setInterval(pollAutomation, 3000);
setInterval(pollCounters, 3000);
