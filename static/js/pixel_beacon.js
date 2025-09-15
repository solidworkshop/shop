
const PB = (function(){
  let running=false, h=null, sent=0, err=0, bucket=[];
  function $(id){return document.getElementById(id)}
  function badge(){ $('pb-status').className = 'badge text-bg-'+(running?'success':'secondary'); $('pb-status').textContent = running?'running':'stopped' }
  function tokenBucketOk(cap){
    const now=performance.now()/1000;
    while(bucket.length && now-bucket[0]>1.0) bucket.shift();
    if (cap<=0) return true;
    if (bucket.length<cap){ bucket.push(now); return true }
    return false;
  }
  function getCookie(name){
    const m = document.cookie.match('(^|;)\s*'+name+'\s*=\s*([^;]+)');
    return m? m.pop() : null;
  }
  function ensureFbp(){
    let fbp = getCookie('_fbp');
    if(!fbp){
      const ts = Math.floor(Date.now()/1000);
      const rand = Math.floor(Math.random()*1e10);
      fbp = `fb.1.${ts}.${rand}`;
      document.cookie = `_fbp=${fbp}; path=/; SameSite=Lax`;
    }
    return fbp;
  }
  function makeUuid(){ return URL.createObjectURL(new Blob()).split('/').pop(); }
  function eventId(){
    const m = document.querySelector('input[name="pb-eid-mode"]:checked').value;
    if(m==='uuid') return makeUuid();
    if(m==='fixed') return (document.getElementById('pb-eid-fixed-val').value.trim()||'fixed-event-id');
    return null;
  }
  function buildUrl(){
    const id = document.getElementById('pb-pixel').value.trim();
    const ev = document.getElementById('pb-event').value || 'PageView';
    const fbp = ensureFbp();
    const dl = encodeURIComponent(window.location.href);
    const rl = encodeURIComponent(document.referrer||'');
    const ts = Math.floor(Date.now()/1000);
    const r = Math.random().toString(36).slice(2);
    let url = `https://www.facebook.com/tr?id=${encodeURIComponent(id)}&ev=${encodeURIComponent(ev)}&dl=${dl}&rl=${rl}&ts=${ts}&fbp=${encodeURIComponent(fbp)}&r=${r}`;
    if(ev==='Purchase'){
      const val = parseFloat(document.getElementById('pb-val').value||'0')||0;
      const cur = (document.getElementById('pb-cur').value||'USD').trim();
      url += `&cd[value]=${encodeURIComponent(val)}&cd[currency]=${encodeURIComponent(cur)}`;
    }
    const eid = eventId(); if(eid) url += `&eid=${encodeURIComponent(eid)}`;
    return url;
  }
  function tick(){
    if(!running) return;
    try{
      const qps = Math.max(1, Math.min(10, parseInt(document.getElementById('pb-qps').value||'1',10)));
      const attempts = Math.max(1, Math.round(qps / 5)); // 200ms tick
      for(let i=0;i<attempts;i++){
        if(!running) break;
        if(!tokenBucketOk(qps)) break;
        const img = new Image();
        img.onload = ()=>{ sent++; document.getElementById('pb-sent').textContent=sent; };
        img.onerror = ()=>{ err++; document.getElementById('pb-err').textContent=err; };
        img.src = buildUrl() + `&cb=${Math.random().toString(36).slice(2)}`;
      }
    }catch(e){ /* ignore */ }
  }
  return {
    start(){
      if(running) return;
      running=true; badge();
      if(h) clearInterval(h); bucket=[];
      h = setInterval(tick, 200);
      tick();
      const dur = Math.max(1, parseInt(document.getElementById('pb-dur').value||'60',10));
      setTimeout(()=>{ if(running) PB.stop(); }, dur*1000);
    },
    stop(){
      running=false; badge(); if(h){ clearInterval(h); h=null; }
    }
  }
})();
