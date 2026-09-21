(() => {
  'use strict';
  const data = window.PATIO_CONTENT;
  if (!data) return;
  const root = new URL(document.body.dataset.storeRoot || './', location.href);
  const link = path => new URL(path, root).href;
  const products = new Map(data.products.map(p => [p.id, {...p}]));
  const cartKey = 'patio.cart.v2', pendingKey = 'patio.order.pending.v1', receiptKey = 'patio.order.receipt.v1';
  const money = n => new Intl.NumberFormat('es-CL', {style:'currency', currency:'CLP', maximumFractionDigits:0}).format(n);
  const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const $ = s => document.querySelector(s);
  const section = document.body.dataset.patioSection;
  const payments = window.PATIO_PAYMENTS;
  let volatileCart = [], storageOK = true, busy = false, catalogVersion = null;
  let toastTimer;

  function read(key, session=false) {
    try { return JSON.parse((session ? sessionStorage : localStorage).getItem(key) || 'null'); }
    catch (_) { if (!session) storageOK = false; return null; }
  }
  function write(key, value, session=false) {
    try { (session ? sessionStorage : localStorage).setItem(key, JSON.stringify(value)); return true; }
    catch (_) { if (!session) storageOK = false; return false; }
  }
  function removeStored(key) { try { sessionStorage.removeItem(key); } catch (_) {} }
  function cart() {
    if (!storageOK) return volatileCart;
    const saved = read(cartKey);
    const source = Array.isArray(saved) ? saved : volatileCart;
    const valid = new Map();
    source.forEach(item => {
      if (item && products.has(item.id) && Number.isInteger(item.qty) && item.qty > 0) {
        valid.set(item.id, {id:item.id, qty:Math.min(item.qty,20)});
      }
    });
    return [...valid.values()];
  }
  function save(items) {
    volatileCart = items;
    write(cartKey, items);
    updateCount();
    if (!storageOK) toast('Tu navegador no permite guardar el carrito. Se conservará sólo en esta página.');
  }
  function updateCount() {
    const count = cart().reduce((sum,i) => sum+i.qty,0);
    document.querySelectorAll('[data-cart-count]').forEach(el => el.textContent = count);
    document.querySelectorAll('.store-cart-link').forEach(el => el.setAttribute('aria-label', `Ver carrito, ${count} unidades`));
  }
  function toast(message, withLink=false) {
    const el = $('.store-toast');
    if (!el) return;
    clearTimeout(toastTimer);
    el.innerHTML = `<span>${esc(message)}</span>${withLink ? `<a href="${link('carrito/')}">Ver carrito ↗</a>` : ''}`;
    el.hidden = false;
    toastTimer = setTimeout(() => el.hidden = true, 5000);
  }
  function add(id, qty=1) {
    if (!products.has(id)) return;
    if (!Number.isInteger(qty) || qty < 1 || qty > 20) return toast('Elige una cantidad entre 1 y 20.');
    const items = cart(), found = items.find(i => i.id === id);
    const before = found?.qty || 0;
    if (found) found.qty = Math.min(20,found.qty+qty); else items.push({id,qty});
    save(items);
    const added = Math.min(qty,20-before);
    if (!added) return toast('Ya tienes el máximo de 20 unidades de esta pieza.');
    window.PATIO_ANALYTICS?.events.addToCart(id,added);
    toast(`${products.get(id).name} ya está en tu carrito.${added < qty ? ' Máximo: 20 unidades.' : ''}`, true);
  }
  function setQuantity(id, qty) {
    if (!Number.isInteger(qty) || qty < 1 || qty > 20) { toast('La cantidad debe ser un número entero entre 1 y 20.'); renderCart(); return; }
    const items = cart();
    const item = items.find(i => i.id === id);
    if (item) item.qty = qty;
    save(items); renderCart();
  }
  function subtotal(items) { return items.reduce((sum,i) => sum + products.get(i.id).price*i.qty,0); }
  function summary(items, checkout=false) {
    const total = subtotal(items);
    return `<p class="eyebrow">TU RINCÓN, EN RESUMEN</p><h2>Todo <em>encaja.</em></h2>${checkout ? `<div class="summary-items">${items.map(i=>`<div><img src="${link(products.get(i.id).image)}" alt="" width="60" height="75"><span>${esc(products.get(i.id).name)}<small>${i.qty} ${i.qty===1?'unidad':'unidades'}</small></span><b>${money(products.get(i.id).price*i.qty)}</b></div>`).join('')}</div>` : ''}<dl class="order-totals"><div><dt>Subtotal referencial</dt><dd>${money(total)}</dd></div><div><dt>Retiro simulado</dt><dd>$0</dd></div><div class="grand-total"><dt>Total de prueba</dt><dd>${money(total)}</dd></div></dl><p class="summary-note">Pesos chilenos · Sin cobro ni reserva de stock.</p>${checkout ? `<a class="text-link" href="${link('carrito/')}">Editar mi carrito ↗</a>` : `<a class="button button-pine" href="${link('finalizar/')}">Preparar pedido <span aria-hidden="true">↗</span></a><p class="summary-foot">Sin tarjetas, sin datos de despacho.<br>Un recorrido para imaginar tu espacio.</p>`}`;
  }
  function empty() {
    return `<div class="empty-cart"><span class="empty-mark" aria-hidden="true">✳</span><h2>Hagamos <em>lugar.</em></h2><p>Tu carrito todavía está vacío.<br>Una pieza puede ser el comienzo de un rincón nuevo.</p><a class="button button-pine" href="${link('productos/')}">Explorar la colección <span aria-hidden="true">↗</span></a></div>`;
  }
  function renderCart() {
    const target = $('#cart-view');
    if (!target) return;
    const items = cart();
    target.innerHTML = !items.length ? empty() : `<div class="cart-layout"><section class="cart-lines" aria-label="Productos del carrito"><div class="cart-table-heading"><span>LA PIEZA</span><span>CANTIDAD / IMPORTE</span></div>${items.map(i => {
      const p = products.get(i.id);
      return `<article class="cart-line"><a href="${link('productos/'+i.id+'/')}"><img src="${link(p.image)}" alt="${esc(p.name)}" width="150" height="188"></a><div class="cart-description"><p class="eyebrow">${esc(p.category)}</p><h2><a href="${link('productos/'+i.id+'/')}">${esc(p.name)}</a></h2><p>${esc(p.subtitle)}</p><small>${money(p.price)} por unidad</small><button type="button" class="remove-item" data-remove="${i.id}">Quitar</button></div><div class="cart-line-end"><div class="quantity-control"><button type="button" data-delta="-1" data-id="${i.id}" aria-label="Reducir cantidad de ${esc(p.name)}" ${i.qty===1?'disabled':''}>−</button><input type="number" min="1" max="20" step="1" value="${i.qty}" data-quantity="${i.id}" aria-label="Cantidad de ${esc(p.name)}"><button type="button" data-delta="1" data-id="${i.id}" aria-label="Aumentar cantidad de ${esc(p.name)}" ${i.qty===20?'disabled':''}>+</button></div><strong>${money(p.price*i.qty)}</strong></div></article>`;
    }).join('')}<p class="cart-smallprint">Guardado en este navegador. Puedes volver más tarde y seguir donde estabas.</p></section><aside class="order-summary">${summary(items)}</aside></div>`;
  }

  const checkoutStatus = message => { if ($('#checkout-status')) $('#checkout-status').textContent=message; };
  async function request(path, options={}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(path,{...options,signal:controller.signal,cache:'no-store'});
      const body = await response.json().catch(()=>null);
      if (!response.ok) {
        const error = new Error(body?.error?.message || 'El ERP local no está disponible para guardar pedidos.');
        error.status = response.status; error.code = body?.error?.code;
        throw error;
      }
      if (!body) throw new Error('El servidor no devolvió una respuesta válida.');
      return body;
    } finally { clearTimeout(timer); }
  }
  function validLines(items) {
    return Array.isArray(items) && items.length>0 && items.every(i=>i && products.has(i.id) && Number.isInteger(i.qty) && i.qty>=1 && i.qty<=20) && new Set(items.map(i=>i.id)).size===items.length;
  }
  let pending = read(pendingKey,true);
  if (pending && (typeof pending.requestId!=='string' || typeof pending.catalogVersion!=='string' || !validLines(pending.items) || typeof pending.customer?.name!=='string' || pending.delivery!=='demo_pickup')) {
    pending=null; removeStored(pendingKey);
  }

  function freezeCheckout(frozen) {
    if (!$('#checkout-form')) return;
    $('#customer-name').readOnly = frozen;
    $('#checkout-form').querySelector('[name=accept]').disabled = frozen;
  }
  async function prepareCheckout() {
    const form = $('#checkout-form');
    if (!form) return;
    const items = pending?.items || payments?.pending()?.items || cart();
    if (!items.length) { $('.checkout-grid').innerHTML = empty(); return; }
    $('#checkout-summary').innerHTML = summary(items,true);
    if (pending) {
      $('#customer-name').value = pending.customer.name;
      form.querySelector('[name=accept]').checked = true;
      freezeCheckout(true);
      $('#place-order').disabled = false;
      $('#place-order').textContent = 'Comprobar y recuperar mi pedido ↗';
      checkoutStatus('Hay un envío pendiente de confirmar. Comprobaremos el mismo pedido sin duplicarlo.');
      return;
    }
    if (payments?.locked()) {
      freezeCheckout(true);
      $('#place-order').disabled = true;
      checkoutStatus('Conservamos un intento de Mercado Pago en esta sesión. Recupéralo desde el panel de abajo antes de guardar otro pedido.');
      payments.refresh();
      return;
    }
    try {
      const catalog = await request('/api/patio/catalog');
      if (catalog.mode !== 'demo' || catalog.currency !== 'CLP' || !catalog.version) throw new Error('El catálogo de prueba no está disponible.');
      let changed=false;
      for (const item of items) {
        const p=catalog.products.find(p=>p.id===item.id);
        if (!p || !Number.isSafeInteger(p.price) || p.price<0) throw new Error('Una pieza ya no está en el catálogo. Revisa el carrito.');
        if (products.get(item.id).price !== p.price) changed=true;
        products.get(item.id).price=p.price;
      }
      catalogVersion=catalog.version;
      $('#checkout-summary').innerHTML=summary(items,true);
      $('#place-order').disabled=catalog.demoOrdersAvailable===false;
      checkoutStatus(catalog.demoOrdersAvailable===false ? 'Catálogo de prueba verificado. El acceso a Mercado Pago está reservado a pruebas privadas.' :
        changed ? 'Los precios se actualizaron desde el ERP. Revisa el resumen antes de guardar.' : 'Catálogo local verificado. Se guardará un pedido de prueba.');
    } catch (_) {
      $('#place-order').disabled=true;
      checkoutStatus('Guardar pedidos requiere el ERP local encendido. Puedes seguir usando el carrito y volver a intentar al recargar esta página.');
    }
    payments?.refresh();
  }
  function receipt(order) {
    return `<div class="receipt-heading"><span class="receipt-mark" aria-hidden="true">✓</span><p class="eyebrow">03 / UN RINCÓN EN CAMINO DE IMAGINARSE</p><h1>Ya tiene<br><em>su lugar.</em></h1><p>Pedido de prueba guardado, ${esc(order.customer.name)}.<br>No se ha realizado un cobro, reserva ni despacho.</p></div><section class="receipt-card"><div class="receipt-meta"><span>PEDIDO DE PRUEBA</span><strong>${esc(order.id)}</strong><time>${esc(new Date(order.createdAt).toLocaleString('es-CL'))}</time></div><div class="receipt-lines">${order.items.map(i=>`<div><span>${esc(i.name)} × ${i.qty}</span><b>${money(i.lineTotal)}</b></div>`).join('')}</div><dl class="order-totals"><div><dt>Retiro simulado</dt><dd>${money(order.shipping)}</dd></div><div class="grand-total"><dt>Total referencial</dt><dd>${money(order.total)}</dd></div></dl><p class="summary-note">Estado de pago: sin cobro. Guardado en el ERP de este equipo.</p><button class="button button-outline" data-download-order>Descargar comprobante ↓</button></section><div class="receipt-bottom"><a class="text-link" href="${link('productos/')}">Volver a la colección ↗</a><a class="text-link" href="${link('blog/')}">Ideas para tu espacio ↗</a></div>`;
  }
  let currentReceipt = read(receiptKey,true);
  if (currentReceipt && (currentReceipt.mode!=='demo' || currentReceipt.paymentStatus!=='not_charged' || typeof currentReceipt.customer?.name!=='string' || !validLines(currentReceipt.items) || !Number.isSafeInteger(currentReceipt.total))) {
    currentReceipt=null; removeStored(receiptKey);
  }
  function renderReceipt() {
    const target=$('#order-receipt');
    if (!target) return;
    target.innerHTML=currentReceipt ? receipt(currentReceipt) : `<div class="empty-cart"><h1>Este rincón<br><em>está por empezar.</em></h1><p>No hay un comprobante en esta sesión.<br>Los pedidos guardados permanecen en el ERP local.</p><a class="button button-pine" href="${link('productos/')}">Ver colección ↗</a></div>`;
  }
  async function submitOrder(event) {
    event.preventDefault();
    if (busy || payments?.locked() || $('#place-order')?.disabled) return;
    if (!pending) {
      if (!catalogVersion || !cart().length) return;
      const name=$('#customer-name').value.trim();
      if (!name || !$('#checkout-form').reportValidity()) return;
      pending={requestId:crypto.randomUUID(),catalogVersion,items:cart(),customer:{name},delivery:'demo_pickup'};
      if (!write(pendingKey,pending,true)) {
        pending=null;
        checkoutStatus('Permite el almacenamiento de sesión para guardar el pedido y recuperar un intento interrumpido.');
        return;
      }
    }
    busy=true; freezeCheckout(true); $('#place-order').disabled=true;
    payments?.refresh();
    checkoutStatus('Guardando y comprobando tu pedido…');
    try {
      const result=await request('/api/patio/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pending)});
      const order=result.order;
      if (!order || order.mode !== 'demo' || order.paymentStatus !== 'not_charged' || !Array.isArray(order.items)) throw new Error('No fue posible comprobar el pedido.');
      currentReceipt=order;
      const saved=write(receiptKey,order,true);
      const items=cart().map(i=>({...i,qty:Math.max(0,i.qty-(order.items.find(x=>x.id===i.id)?.qty || 0))})).filter(i=>i.qty>0);
      save(items); removeStored(pendingKey); pending=null;
      if (saved) location.assign(link('pedido/'));
      else { $('#contenido').innerHTML=receipt(order); window.scrollTo(0,0); }
    } catch (error) {
      // Unknown outcome keeps the exact operation identity. Never silently create another order.
      if (error.status >= 400 && error.status < 500) {
        removeStored(pendingKey); pending=null; freezeCheckout(false);
        checkoutStatus(error.message+' Revisa los datos y vuelve a intentarlo.');
        if (error.status===409) { catalogVersion=null; await prepareCheckout(); }
      } else {
        checkoutStatus('No pudimos confirmar el resultado. Reintenta para recuperar el mismo pedido, sin duplicarlo.');
        $('#place-order').textContent='Comprobar y recuperar mi pedido ↗';
      }
      $('#place-order').disabled=!pending && !catalogVersion;
    } finally { busy=false; payments?.refresh(); }
  }
  function filterCatalog() {
    const grid=$('#product-grid'); if(!grid) return;
    const filter=$('[data-filter][aria-pressed="true"]')?.dataset.filter || 'Todos';
    const sort=$('#sort-products')?.value;
    const cards=[...grid.querySelectorAll('[data-catalog-product]')];
    cards.sort((a,b)=>sort==='low' ? Number(a.dataset.price)-Number(b.dataset.price) : sort==='high' ? Number(b.dataset.price)-Number(a.dataset.price) : data.products.findIndex(p=>p.id===a.dataset.catalogProduct)-data.products.findIndex(p=>p.id===b.dataset.catalogProduct));
    cards.forEach(el=>{el.hidden=filter!=='Todos' && el.dataset.category!==filter;grid.append(el);});
    if($('#catalog-status')) $('#catalog-status').textContent=`${cards.filter(el=>!el.hidden).length} piezas en la colección`;
  }
  document.addEventListener('click', event=>{
    const el=event.target.closest('button'); if(!el) return;
    if(el.dataset.add) add(el.dataset.add,el.hasAttribute('data-use-quantity') ? Number($('#product-quantity').value) : 1);
    if(el.dataset.remove) {save(cart().filter(i=>i.id!==el.dataset.remove));renderCart();toast('Pieza retirada del carrito.');}
    if(el.dataset.delta) {const i=cart().find(i=>i.id===el.dataset.id);if(i) setQuantity(i.id,i.qty+Number(el.dataset.delta));}
    if(el.dataset.filter) {document.querySelectorAll('[data-filter]').forEach(b=>{b.classList.toggle('active',b===el);b.setAttribute('aria-pressed',String(b===el));});filterCatalog();}
    if(el.hasAttribute('data-menu')) {const nav=$('.store-mobile-nav');nav.hidden=!nav.hidden;el.setAttribute('aria-expanded',String(!nav.hidden));}
    if(el.hasAttribute('data-download-order') && currentReceipt) {
      const o=currentReceipt;
      const text=`PATIO · Pedido de prueba\n${o.id}\n${o.createdAt}\nNombre: ${o.customer.name}\n\n${o.items.map(i=>`${i.name} × ${i.qty}: ${money(i.lineTotal)}`).join('\n')}\n\nTotal referencial: ${money(o.total)} CLP\nSin cobro, reserva de stock ni despacho.\n`;
      const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));
      const a=document.createElement('a');a.href=url;a.download=`PATIO-pedido-${o.id}.txt`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
  });
  document.addEventListener('change',event=>{
    if(event.target.dataset.quantity) setQuantity(event.target.dataset.quantity,Number(event.target.value));
    if(event.target.id==='sort-products') filterCatalog();
  });
  window.addEventListener('storage',event=>{
    if(event.key===cartKey || event.key===null) {updateCount();renderCart();if(section==='checkout' && !busy && !pending && !payments?.locked()) {catalogVersion=null;$('#place-order').disabled=true;prepareCheckout();}}
  });
  $('#checkout-form')?.addEventListener('submit',submitOrder);
  if ($('#checkout-form')) payments?.mountCheckout({
    form:$('#checkout-form'),demoBusy:()=>busy,demoPending:()=>!!pending,
    context:()=>({catalogVersion,items:cart(),name:$('#customer-name').value}),
    lock:()=>{freezeCheckout(true);$('#place-order').disabled=true;},
    reset:async()=>{catalogVersion=null;freezeCheckout(false);$('#checkout-form').querySelector('[name=accept]').checked=false;await prepareCheckout();}
  });
  updateCount();renderCart();prepareCheckout();renderReceipt();
  const id=document.body.dataset.patioId, events=window.PATIO_ANALYTICS?.events;
  events?.pageView({path:location.pathname,title:document.title});
  if(section==='product') events?.viewItem(id);
  if(section==='article') events?.viewArticle(id);
})();
