(function(){
  function uuid(){ return 'xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx'.replace(/[xy]/g, c=>{const r=Math.random()*16|0,v=c=='x'?r:(r&0x3|0x8);return v.toString(16);}); }
  function post(url, obj){ return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)}).catch(()=>{}); }
  const api = { track: function(name, params){ try{ const payload=Object.assign({event_name:name,event_id:uuid(),ts:Date.now(),path:location.pathname}, params||{}); post('/beacon', payload);}catch(e){} } };
  window.demopixel = api; api.track('PageView');
})();