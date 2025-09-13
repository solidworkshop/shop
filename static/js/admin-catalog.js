(function(){
  const $ = (sel)=>document.querySelector(sel);
  const $$ = (sel)=>Array.from(document.querySelectorAll(sel));

  function rowToObj(tr){
    const tds = tr.querySelectorAll('td');
    return {
      id: parseInt(tr.dataset.id || '0',10) || null,
      sku: tds[1].textContent.trim(),
      name: tds[2].textContent.trim(),
      price: parseFloat(tds[3].textContent.trim() || '0') || 0,
      cost: parseFloat(tds[4].textContent.trim() || '0') || 0,
      currency: tds[5].textContent.trim() || null,
      image_url: tds[7].textContent.trim(),
      description: tds[8].textContent // may contain HTML
    };
  }

  function formatPreview(price, currency){
    const loc = $('#catalogLocale')?.value || 'en-US';
    try{
      return new Intl.NumberFormat(loc, { style:'currency', currency: currency || 'USD' }).format(price || 0);
    }catch(e){
      return (currency||'USD') + ' ' + (price||0).toFixed(2);
    }
  }

  function refreshPreviews(){
    $$('#prodTable tbody tr').forEach(tr=>{
      const obj = rowToObj(tr);
      tr.querySelector('.preview').textContent = formatPreview(obj.price, obj.currency);
    });
  }

  $('#saveSettings')?.addEventListener('click', async ()=>{
    const payload = {
      item_count: parseInt($('#itemCount').value||'1',10),
      currency_mode: $('#currencyMode').value,
      currency_specific: $('#currencySpecific').value,
      locale: $('#catalogLocale').value
    };
    await fetch('/admin/api/catalog/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
    refreshPreviews();
  });

  $('#seedBtn')?.addEventListener('click', async ()=>{
    const count = parseInt($('#itemCount').value||'1',10);
    await fetch('/admin/api/catalog/seed', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({count})});
    location.reload();
  });

  $('#addRow')?.addEventListener('click', ()=>{
    const tbody = $('#prodTable tbody');
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>—</td>
      <td contenteditable="true">SKU-${Math.floor(Math.random()*90000+10000)}</td>
      <td contenteditable="true">New Product</td>
      <td contenteditable="true">19.99</td>
      <td contenteditable="true">9.99</td>
      <td contenteditable="true"></td>
      <td class="text-muted small preview"></td>
      <td contenteditable="true"></td>
      <td contenteditable="true"><p>Short description</p></td>
      <td class="text-end">
        <button class="btn btn-primary btn-sm saveRow">Save</button>
        <button class="btn btn-outline-danger btn-sm delRow">Delete</button>
      </td>
    `;
    tbody.prepend(tr);
    refreshPreviews();
  });

  document.addEventListener('click', async (e)=>{
    if (e.target.classList.contains('saveRow')){
      const tr = e.target.closest('tr');
      const obj = rowToObj(tr);
      const r = await fetch('/admin/api/catalog', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(obj)});
      const j = await r.json();
      if (j.ok && j.product){
        tr.dataset.id = j.product.id;
        tr.children[0].textContent = j.product.id;
      }
    }
    if (e.target.classList.contains('delRow')){
      const tr = e.target.closest('tr');
      const id = tr.dataset.id;
      if (id){
        await fetch('/admin/api/catalog/'+id, {method:'DELETE'});
        tr.remove();
      }else{
        tr.remove();
      }
    }
  });

  document.addEventListener('input', (e)=>{
    if (e.target.closest('#prodTable')){
      refreshPreviews();
    }
  });

  refreshPreviews();
})();
