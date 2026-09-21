(() => {
  'use strict';
  const pendingKey = 'patio.payment.pending.v1', sessionsKey = 'patio.payment.sessions.v1', operatorKey = 'patio.payment.operator.v1';
  const root = new URL(document.body.dataset.storeRoot || './', location.href);
  const link = path => new URL(path, root).href;
  const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = n => new Intl.NumberFormat('es-CL', {style:'currency',currency:'CLP',maximumFractionDigits:0}).format(n);
  const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
  const keyPattern = /^[a-f0-9]{64}$/;
  let storageCorrupt = false, checkoutBusy = false, config = null, bridge = null;
  function read(key) {
    try { return JSON.parse(sessionStorage.getItem(key) || 'null'); }
    catch (_) { storageCorrupt = true; return null; }
  }
  function save(key, value) {
    try { sessionStorage.setItem(key, JSON.stringify(value)); return true; }
    catch (_) { return false; }
  }
  let pending = read(pendingKey);
  if (pending && (!uuid.test(pending.requestId) || !keyPattern.test(pending.accessKey) ||
      typeof pending.catalogVersion !== 'string' || !Array.isArray(pending.items) || !pending.items.length ||
      !pending.items.every(i => i && window.PATIO_CONTENT?.products.some(p=>p.id===i.id) && Number.isInteger(i.qty) && i.qty > 0 && i.qty <= 20) ||
      typeof pending.customer?.name !== 'string' || pending.delivery !== 'demo_pickup')) {
    storageCorrupt = true; pending = null; // Preserve the stored evidence; never silently replace an uncertain operation.
  }
  async function request(path, body) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 20000);
    try {
      const operator = read(operatorKey);
      const headers = {...(body ? {'Content-Type':'application/json'} : {}),
        ...(typeof operator === 'string' && keyPattern.test(operator) ? {'X-PATIO-Test-Key':operator} : {})};
      const response = await fetch(path, {method:body ? 'POST' : 'GET',cache:'no-store',signal:controller.signal,headers,
        ...(body ? {body:JSON.stringify(body)} : {})});
      const result = await response.json().catch(() => null);
      if (!response.ok || !result) {
        const error = new Error(result?.error?.message || 'No pudimos comprobar la respuesta del servidor.');
        error.code = result?.error?.code; error.status = response.status; throw error;
      }
      return result;
    } finally { clearTimeout(timer); }
  }
  function checkoutUrl(value) {
    try {
      const u = new URL(value);
      return u.protocol === 'https:' && ['www.mercadopago.cl','mercadopago.cl','www.mercadopago.com','mercadopago.com'].includes(u.hostname) &&
        !u.username && !u.password && !u.hash && (!u.port || u.port === '443') && u.pathname.includes('/checkout/') ? u.href : null;
    } catch (_) { return null; }
  }
  function setNote(message) {
    const el = document.querySelector('#mp-checkout-status'); if (el) el.textContent = message;
  }
  function refresh() {
    const button = document.querySelector('#mp-checkout');
    if (!button || !bridge) return;
    const ready = config?.available === true && config.mode === 'test' && config.livePaymentsAllowed === false;
    button.disabled = !ready || storageCorrupt || checkoutBusy || bridge.demoBusy() || bridge.demoPending() || (!pending && !bridge.context().catalogVersion);
    button.textContent = pending ? 'Recuperar el mismo checkout ↗' : 'Abrir Mercado Pago · prueba ↗';
    if (pending || storageCorrupt) bridge.lock();
  }
  async function submit() {
    refresh();
    if (document.querySelector('#mp-checkout')?.disabled) return;
    if (!pending) {
      const context = bridge.context();
      if (!context.items.length || !bridge.form.reportValidity()) return;
      const bytes = crypto.getRandomValues(new Uint8Array(32));
      pending = {requestId:crypto.randomUUID(),catalogVersion:context.catalogVersion,items:context.items,
        customer:{name:context.name.trim()},delivery:'demo_pickup',accessKey:[...bytes].map(x=>x.toString(16).padStart(2,'0')).join('')};
      if (!save(pendingKey,pending)) {
        pending = null;
        setNote('Permite el almacenamiento de sesión para conservar este intento antes de contactar a Mercado Pago. No se envió ninguna solicitud.');
        return;
      }
    }
    checkoutBusy = true; refresh();
    setNote('Preparando el checkout de prueba. Conservaremos este intento si se interrumpe la conexión.');
    try {
      const result = await request('/api/patio/payments/checkout',pending), checkout = result.checkout;
      const url = checkoutUrl(checkout?.checkoutUrl);
      if (!checkout || checkout.mode !== 'test' || checkout.currency !== 'CLP' || !uuid.test(checkout.orderId) ||
          !Number.isSafeInteger(checkout.total) || checkout.total <= 0 || !url) throw new Error('El checkout recibido no cumple las condiciones de esta prueba.');
      const sessions = read(sessionsKey) || {};
      if (storageCorrupt || Array.isArray(sessions) || typeof sessions !== 'object') throw new Error('No pudimos conservar la sesión para comprobar el regreso.');
      sessions[checkout.orderId] = {orderId:checkout.orderId,accessKey:pending.accessKey,checkoutUrl:url};
      if (!save(sessionsKey,sessions)) throw new Error('No pudimos conservar la sesión para comprobar el regreso.');
      setNote('Abriendo Mercado Pago. Usa exclusivamente la cuenta compradora y los medios de prueba.');
      location.assign(url);
    } catch (error) {
      // These codes are guaranteed by the backend to precede both persistence and provider POST.
      // Any ambiguous response, idempotency conflict or configuration change retains the identity.
      if (['catalog_changed','invalid_product','test_limit','invalid_order','invalid_access_key'].includes(error.code)) {
        try {
          sessionStorage.removeItem(pendingKey);
          pending = null;
          await bridge.reset();
          setNote(`${error.message} No se creó un checkout. Revisa la selección actualizada y confirma nuevamente antes de continuar.`);
          return;
        } catch (_) {
          setNote('No pudimos actualizar la sesión. Conserva este intento para revisarlo antes de continuar.');
          return;
        }
      }
      setNote(error.code === 'checkout_uncertain'
        ? 'Este intento necesita revisión: no sabemos si Mercado Pago creó el checkout. Conservamos su identidad y no abriremos uno nuevo. Puedes comprobar de nuevo este mismo intento después de la revisión.'
        : `${error.message || 'No pudimos confirmar el resultado.'} Conservamos el intento: vuelve a comprobarlo sin crear otro.`);
    } finally { checkoutBusy = false; refresh(); }
  }
  function mountCheckout(options) {
    bridge = options;
    document.querySelector('#mp-checkout')?.addEventListener('click',submit);
    if (pending) {
      bridge.form.querySelector('[name=name]').value = pending.customer.name;
      bridge.form.querySelector('[name=accept]').checked = true;
    }
    refresh();
    request('/api/patio/payments/config').then(value => {
      config = value;
      if (config.requiresOperator && !config.operatorAuthorized) mountOperatorAccess();
      setNote(storageCorrupt ? 'No podemos leer el intento guardado. Conserva esta sesión para revisarla antes de iniciar otro.' :
        pending ? 'Hay un intento de Mercado Pago guardado. Sólo recuperaremos ese mismo checkout; no crearemos otro pedido.' :
        config.requiresOperator && !config.operatorAuthorized ? 'El checkout está reservado a una prueba privada. Ingresa la clave de esta ronda para habilitarlo.' :
        config.available && config.mode === 'test' && config.livePaymentsAllowed === false ?
        'Sólo cuentas y medios de prueba. La cuenta vendedora se comprobará en el servidor antes de abrir el checkout. No uses tarjetas reales.' :
        'Mercado Pago no está habilitado para esta ronda. Conserva tu carrito y vuelve a comprobar más tarde.');
      refresh();
    }).catch(() => {
      setNote('Mercado Pago no está disponible en este momento. Conserva tu carrito y vuelve a comprobar más tarde.');
      refresh();
    });
  }
  function mountOperatorAccess() {
    if (document.querySelector('#mp-operator-access')) return;
    const box=document.createElement('div');box.id='mp-operator-access';box.className='payment-operator-access';
    const label=document.createElement('label');label.htmlFor='mp-operator-key';label.textContent='Acceso privado de pruebas';
    const input=document.createElement('input');input.type='password';input.id='mp-operator-key';input.autocomplete='off';
    input.placeholder='Clave de esta ronda';input.maxLength=64;
    const button=document.createElement('button');button.type='button';button.className='button button-outline';button.textContent='Habilitar prueba privada';
    input.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();if(!button.disabled) button.click();}});
    button.addEventListener('click',async()=>{
      const key=input.value.trim();
      if (!keyPattern.test(key)) {setNote('Ingresa la clave privada de 64 caracteres de esta ronda.');return;}
      if (!save(operatorKey,key)) {setNote('Permite el almacenamiento de sesión para esta prueba.');return;}
      button.disabled=true;
      try {
        config=await request('/api/patio/payments/config');
        if (!config.operatorAuthorized) {setNote('La clave no corresponde a esta ronda.');return;}
        input.value='';box.remove();setNote(config.message);refresh();
      } catch (_) {setNote('No pudimos verificar el acceso. Conserva tu intento y vuelve a comprobar.');}
      finally {button.disabled=false;}
    });
    box.append(label,input,button);
    document.querySelector('#mp-checkout')?.before(box);
  }
  const states = {
    awaiting_payment:['Esperando confirmación.','Todavía no hay un pago de prueba confirmado para este pedido.'],
    needs_review:['Revisemos este intento.','El intento requiere revisión antes de continuar. No crees otro checkout para reemplazarlo.'],
    test_approved:['Prueba aprobada.','El servidor comprobó un pago en modo de prueba. No es una compra real ni autoriza un despacho.'],
    test_pending:['La prueba sigue pendiente.','Mercado Pago todavía no confirma la aprobación de este pago de prueba.'],
    test_rejected:['Prueba no aprobada.','El pago de prueba fue rechazado o cancelado. No hay una compra confirmada.'],
    test_refunded:['Prueba reembolsada.','El servidor registró la devolución completa del pago de prueba.'],
    test_partially_refunded:['Devolución parcial de prueba.','El servidor registró una devolución parcial. Esta prueba no autoriza un despacho.'],
    test_disputed:['Prueba en revisión.','El pago de prueba tiene una disputa o contracargo registrado. No autoriza un despacho.']
  };
  async function mountReturn() {
    const target = document.querySelector('#payment-result'); if (!target) return;
    const params = new URLSearchParams(location.search), previousReturn = read('patio.payment.return.v1');
    const orderId = params.has('order') ? params.get('order') : previousReturn?.orderId;
    const rawId = params.has('order') ? (params.get('payment_id') || params.get('collection_id')) : previousReturn?.paymentId;
    const paymentId = rawId && /^\d+$/.test(rawId) ? rawId : null;
    const sessions = read(sessionsKey), context = sessions && uuid.test(orderId || '') ? sessions[orderId] : null;
    // Return parameters only identify a resource to verify. status / collection_status never authorize success.
    history.replaceState(null,'',location.pathname);
    if (!context || context.orderId !== orderId || !keyPattern.test(context.accessKey)) {
      target.innerHTML = `<div class="receipt-heading"><span class="payment-mark" aria-hidden="true">↗</span><p class="eyebrow">MERCADO PAGO · PRUEBA</p><h1>Volvamos a<br><em>conectar.</em></h1><p>No encontramos este intento en la sesión del navegador.<br>El enlace de regreso no confirma un pago por sí solo.</p></div><div class="payment-return-note"><p>Vuelve desde la misma pestaña donde abriste el checkout. Si cerraste esa sesión, el intento debe revisarlo el operador de la prueba.</p><a class="text-link" href="${link('finalizar/')}">Volver al pedido ↗</a></div>`;
      return;
    }
    save('patio.payment.return.v1',{orderId,paymentId});
    target.innerHTML = `<div class="receipt-heading"><span class="payment-mark" aria-hidden="true">↗</span><p class="eyebrow">MERCADO PAGO · PRUEBA</p><h1 id="payment-title">Comprobando<br><em>tu regreso.</em></h1><p id="payment-message">Consultando el estado en el servidor. El regreso del checkout todavía no confirma un pago.</p></div><section class="receipt-card"><div class="receipt-meta"><span>INTENTO DE PRUEBA</span><strong>${esc(orderId)}</strong></div><div id="payment-lines"></div><p class="summary-note">Sin compra real ni despacho. Tu carrito se conserva.</p><p id="payment-check-status" class="payment-check-status" role="status" aria-live="polite"></p><button type="button" class="button button-pine" id="payment-refresh">Comprobar estado ↗</button></section><div class="receipt-bottom"><a class="text-link" href="${link('carrito/')}">Volver a mi carrito ↗</a><a class="text-link" href="${link('ayuda/')}">Cómo funciona la prueba ↗</a></div>`;
    let refreshing = false, lastChecked = null;
    const actions = document.createElement('div');
    actions.id = 'payment-actions';
    document.querySelector('#payment-refresh').after(actions);
    async function check() {
      if (refreshing) return;
      refreshing = true;
      const button = document.querySelector('#payment-refresh'), note = document.querySelector('#payment-check-status');
      button.disabled = true; actions.replaceChildren(); note.textContent = 'Comprobando el estado…';
      try {
        const body = {orderId,accessKey:context.accessKey};
        const result = await request('/api/patio/payments/'+(paymentId ? 'reconcile' : 'status'),paymentId ? {...body,paymentId} : body);
        const p = result.payment;
        if (!p || p.orderId !== orderId || p.mode !== 'test' || p.currency !== 'CLP' || p.realPayment !== false ||
            p.fulfillmentAllowed !== false || !states[p.status] || !Number.isSafeInteger(p.total) || !Array.isArray(p.items) ||
            !p.items.every(i=>typeof i.name === 'string' && Number.isInteger(i.qty) && Number.isSafeInteger(i.lineTotal))) {
          throw new Error('La respuesta no permite confirmar el estado de esta prueba.');
        }
        const [title,message] = states[p.status];
        lastChecked = {title,checkedAt:p.checkedAt};
        document.querySelector('#payment-title').textContent = title;
        document.querySelector('#payment-message').textContent = message;
        document.querySelector('#payment-lines').innerHTML = `<div class="receipt-lines">${p.items.map(i=>`<div><span>${esc(i.name)} × ${i.qty}</span><b>${money(i.lineTotal)}</b></div>`).join('')}</div><dl class="order-totals"><div class="grand-total"><dt>Total de prueba</dt><dd>${money(p.total)}</dd></div></dl>`;
        note.textContent = p.checkedAt && !Number.isNaN(Date.parse(p.checkedAt)) ? `Última comprobación del pago: ${new Date(p.checkedAt).toLocaleString('es-CL')}.` : 'Estado del intento consultado. Todavía no hay una comprobación de pago registrada.';
        if (['test_approved','test_rejected','test_refunded'].includes(p.status) && pending?.accessKey === context.accessKey) {
          const close = document.createElement('button');
          close.type = 'button'; close.className = 'button button-outline'; close.id = 'payment-close';
          close.textContent = 'Cerrar esta prueba y volver a elegir ↗';
          close.addEventListener('click',()=>{
            const current = read(pendingKey);
            if (!current || current.accessKey !== context.accessKey) {
              note.textContent = 'La sesión cambió. No modificamos otro intento. Vuelve a comprobar el estado.';
              return;
            }
            try {
              sessionStorage.removeItem(pendingKey); pending = null;
              location.assign(link('productos/'));
            } catch (_) { note.textContent = 'No pudimos cerrar la prueba en esta sesión. El registro sigue conservado.'; }
          });
          actions.append(close);
        }
      } catch (error) {
        document.querySelector('#payment-title').textContent = lastChecked ? 'Estado sin actualizar.' : 'Aún sin confirmar.';
        if (lastChecked) document.querySelector('#payment-message').textContent = `La última comprobación indicaba «${lastChecked.title}». La consulta actual no se pudo completar; ese resultado anterior no confirma el estado actual.`;
        note.textContent = `${error.message || 'No pudimos consultar el estado.'} No podemos confirmar un pago con el enlace de regreso. Puedes volver a comprobarlo.`;
      } finally { refreshing = false; button.disabled = false; }
    }
    document.querySelector('#payment-refresh').addEventListener('click',check);
    await check(); // One bounded verification per visit; subsequent checks are explicit.
  }
  window.PATIO_PAYMENTS = {pending:()=>pending,locked:()=>!!pending || storageCorrupt,mountCheckout,refresh};
  mountReturn();
})();
