
function q(s){return document.querySelector(s)}
async function saveKV(k,v){ await fetch('/admin/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({[k]:v})}) }
async function api(url){ const r=await fetch(url); return await r.json() }
async function apiPost(url, body=null){ const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):null}); return await r.json() }
async function startIntervals(){ const r = await apiPost('/admin/automation/start'); setTimeout(refreshAll, 400) }
async function stopIntervals(){ const r = await apiPost('/admin/automation/stop'); setTimeout(refreshAll, 400) }
function setBadge(state){ const el=q('#automation-status'); const ok=!!state; el.className='badge text-bg-'+(ok?'success':'secondary'); el.textContent= ok?'running':'stopped' }
async function refreshStatus(){ try{ const d=await api('/admin/automation/status'); setBadge(d.running) }catch(e){} }
async function refreshCounters(){ try{ const d=await api('/admin/counters'); ['pixel','capi','deduped','margin_events','pltv_events'].forEach(k=>{ const el=q('#cnt-'+k); if(el) el.textContent=d[k] }); setBadge(d.running) }catch(e){} }
async function refreshRecent(){ try{ const d=await api('/admin/recent-events'); const ul=q('#recent-ul'); if(!ul) return; ul.innerHTML=''; d.items.forEach(it=>{ const li=document.createElement('li'); li.className='list-group-item py-1 small'; li.textContent = `${it.channel} • ${it.event} • ${it.status}`; ul.appendChild(li); }); }catch(e){} }
async function runPixelCheck(){ const r=await api('/admin/pixel-check'); q('#pixel-check-res').textContent=JSON.stringify(r) }
async function manualSend(){ try{ const t=q('#manual-json').value; const dry=q('#dry-run').checked; const body=JSON.parse(t); if(dry) body.dry_run=true; const r=await apiPost('/admin/manual_send',body); q('#manual-res').textContent=JSON.stringify(r) } catch(e){ q('#manual-res').textContent='Invalid JSON: '+e } }
function refreshAll(){ refreshStatus(); refreshCounters(); refreshRecent(); }
setInterval(refreshAll, 3000); window.addEventListener('load', ()=> setTimeout(refreshAll, 300));
