(function(){
  const url = "/pixel-collect";
  function send(evtName, meta){
    const data = Object.assign({
      event_name: evtName || "PageView",
      event_id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random()
    }, meta || {});
    try {
      if (navigator.sendBeacon){
        const blob = new Blob([JSON.stringify(data)], {type: "application/json"});
        navigator.sendBeacon(url, blob);
      } else {
        fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(data)});
      }
    } catch(e){ /* swallow */ }
  }
  window.demoPixel = send;
  // Auto-fire PageView after fetching settings (to respect toggles remotely)
  try {
    fetch('/admin/api/settings').then(r=>r.json()).then(s=>{
      if (s.pixel_enabled && s.ev_PageView){
        send("PageView", {path: location.pathname});
      }
    });
  } catch(e){ /* ignore */ }
})();
