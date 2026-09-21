(() => {
  'use strict';
  const content = window.PATIO_CONTENT;
  if (!content || !Array.isArray(content.products)) return;
  const products = content.products;
  const byId = new Map(products.map(p => [p.id, p]));
  const $ = s => document.querySelector(s);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = value => new Intl.NumberFormat('es-CL', {style:'currency', currency:'CLP', maximumFractionDigits:0}).format(value);
  const normalize = value => String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const storageKey = 'patio.selection.v1';
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(storageKey) || '{}') || {}; } catch (_) {}
  const state = {
    bag: Array.isArray(saved.bag) ? saved.bag.filter(x => x && byId.has(x.id) && Number.isInteger(x.qty) && x.qty > 0).map(x => ({id:x.id, qty:Math.min(x.qty,20)})) : [],
    favorites: new Set(Array.isArray(saved.favorites) ? saved.favorites.filter(id => byId.has(id)) : []),
    filter:'Todos', sort:'featured', collection:null, panel:null, product:null, qty:1
  };
  const heart = '<svg viewBox="0 0 24 24"><path d="M20.1 5.7a5.2 5.2 0 0 0-7.3 0L12 6.5l-.8-.8a5.2 5.2 0 0 0-7.3 7.4L12 21l8.1-7.9a5.2 5.2 0 0 0 0-7.4Z"/></svg>';
  const panel = $('#panel'), body = $('#panel-body');
  panel.setAttribute('aria-labelledby', 'panel-label');
  let toastTimer;
  function toast(message) { const t=$('#toast'); t.textContent=message; t.classList.add('visible'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>t.classList.remove('visible'),2700); }
  function persist() { try { localStorage.setItem(storageKey, JSON.stringify({bag:state.bag, favorites:[...state.favorites]})); } catch (_) {} updateBagCount(); }
  function updateBagCount() { const count=state.bag.reduce((s,x)=>s+x.qty,0); $('#bag-count').textContent=count; $('.bag-trigger').setAttribute('aria-label',`Abrir bolsa, ${count} productos`); }
  function favoriteButton(p) { const selected=state.favorites.has(p.id); return `<button class="icon-button favorite-button ${selected?'selected':''}" data-favorite="${p.id}" aria-label="${selected?'Quitar':'Guardar'} ${esc(p.name)} ${selected?'de':'en'} favoritos" aria-pressed="${selected}">${heart}</button>`; }
  function renderCatalog() {
    let list=products.filter(p=>state.filter==='Todos' || p.category===state.filter);
    if(state.collection)list=list.filter(p=>state.collection.productIds.includes(p.id));
    if(state.sort==='low')list.sort((a,b)=>a.price-b.price);
    if(state.sort==='high')list.sort((a,b)=>b.price-a.price);
    $('#product-grid').innerHTML=list.length?list.map(p=>`<article class="product-card fade-in" data-id="${p.id}"><div class="product-image-wrap"><button class="product-open" data-product="${p.id}" aria-label="Ver ${esc(p.name)}, ${esc(p.subtitle)}"><img src="${esc(p.image)}" alt="${esc(p.subtitle)} ${esc(p.name)}" width="1122" height="1402" loading="lazy"></button><span class="product-tag">${esc(p.tag)}</span>${favoriteButton(p)}<button class="quick-add" data-add="${p.id}" aria-label="Agregar ${esc(p.name)} a la bolsa">+</button></div><div class="product-info"><div><button class="product-name" data-product="${p.id}">${esc(p.name)}</button><p class="product-subtitle">${esc(p.subtitle)}</p><span class="color-swatch" style="background:${esc(p.colors[0].hex)}" title="${esc(p.colors[0].name)}"></span></div><span class="product-price">${money(p.price)}</span></div></article>`).join(''):'<p class="no-results">Prueba otra selección. Hay más por descubrir.</p>';
    document.querySelectorAll('.filter').forEach(b=>{const active=b.dataset.filter===state.filter;b.classList.toggle('active',active);b.setAttribute('aria-pressed',active);});
    $('#catalog-status').textContent=`${list.length} productos${state.collection?' para '+state.collection.name:''}`;
    $('.collection-note span:last-child').textContent=state.collection?`${state.collection.name.toUpperCase()} · ${list.length} PIEZAS`:`${String(list.length).padStart(2,'0')} PIEZAS / COLECCIÓN ESENCIAL`;
  }
  function openPanel(type,label,html,drawer=false) {
    state.panel=type; panel.classList.toggle('drawer',drawer); $('#panel-label').textContent=label; body.innerHTML=html;
    if(!panel.open)panel.showModal(); document.body.classList.add('dialog-open'); panel.scrollTop=0;
    requestAnimationFrame(()=> { if(type==='search')$('#search-query')?.focus(); else $('.close-panel').focus(); });
  }
  function closePanel() { panel.close(); }
  panel.addEventListener('close',()=>{document.body.classList.remove('dialog-open');state.panel=null;});
  panel.addEventListener('keydown',event=>{
    if(event.key!=='Tab')return;
    const stops=[...panel.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')].filter(el=>el.getClientRects().length);
    if(!stops.length)return;
    const first=stops[0],last=stops[stops.length-1];
    if(event.shiftKey && (document.activeElement===first || !panel.contains(document.activeElement))){event.preventDefault();last.focus();}
    else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first.focus();}
  });
  panel.addEventListener('click',event=>{if(event.target===panel){const r=panel.getBoundingClientRect();if(event.clientX<r.left || event.clientX>r.right || event.clientY<r.top || event.clientY>r.bottom)closePanel();}});
  $('.close-panel').addEventListener('click',closePanel);
  function openProduct(id) {
    const p=byId.get(id);if(!p)return;state.product=id;state.qty=1;
    window.PATIO_ANALYTICS?.events.viewItem(id);
    openPanel('product','La colección / '+p.name,`<div class="detail-grid"><img class="detail-photo" src="${esc(p.image)}" alt="${esc(p.subtitle)} ${esc(p.name)}" width="1122" height="1402"><div class="detail-copy"><p class="eyebrow">${esc(p.category)}</p><h2>${esc(p.name)}</h2><p class="product-subtitle">${esc(p.subtitle)}</p><p class="detail-price">${money(p.price)}</p><p class="detail-description">${esc(p.description)}</p><p class="detail-color"><i style="background:${esc(p.colors[0].hex)}"></i>${esc(p.colors[0].name)}</p><div class="detail-actions"><div class="quantity-control" aria-label="Cantidad"><button data-detail-qty="-1" aria-label="Reducir cantidad" disabled>−</button><span id="detail-qty">1</span><button data-detail-qty="1" aria-label="Aumentar cantidad">+</button></div><button class="button button-pine" data-add-detail="${p.id}">Agregar a mi bolsa <span aria-hidden="true">+</span></button></div><p class="detail-note">${esc(p.leadTime)} · Valores en CLP</p><details open><summary>Los detalles hacen la diferencia</summary><ul class="detail-list">${p.details.map(d=>`<li>${esc(d)}</li>`).join('')}</ul></details><details><summary>Para que te acompañe más tiempo</summary><p>${esc(p.care)}</p></details></div></div>`);
  }
  function addToBag(id,qty=1) {
    if(!byId.has(id))return;
    const row=state.bag.find(x=>x.id===id),previous=row?.qty||0;
    if(previous===20){toast('Puedes guardar hasta 20 unidades de cada pieza.');return;}
    const next=Math.min(previous+qty,20);if(row)row.qty=next;else state.bag.push({id,qty:next});
    persist();window.PATIO_ANALYTICS?.events.addToCart(id,next-previous);toast(`${byId.get(id).name} está en tu bolsa`);
    if(state.panel==='bag')renderBag();
  }
  function emptyState(title,message) {return `<div class="empty-state"><span aria-hidden="true">afuera.</span><h3>${title}</h3><p>${message}</p><button class="button button-pine" data-action="continue">Explorar la colección <span aria-hidden="true">↗</span></button></div>`;}
  function renderBag() {
    const total=state.bag.reduce((s,x)=>s+byId.get(x.id).price*x.qty,0);
    const html=state.bag.length?`<div class="drawer-content"><h2 class="panel-title">Tu próximo rincón.</h2><p class="panel-lead">Una selección para hacer lugar a lo que te gusta.</p><div class="bag-items">${state.bag.map(row=>{const p=byId.get(row.id);return `<div class="bag-item" data-bag-row="${p.id}"><button data-product="${p.id}" aria-label="Ver ${esc(p.name)}"><img class="bag-image" src="${esc(p.image)}" alt="${esc(p.name)}" width="89" height="113"></button><div><h3>${esc(p.name)} <span style="float:right">${money(p.price*row.qty)}</span></h3><p>${esc(p.subtitle)}</p><div class="quantity-control"><button data-bag-qty="-1" data-id="${p.id}" aria-label="Reducir ${esc(p.name)}" ${row.qty===1?'disabled':''}>−</button><span>${row.qty}</span><button data-bag-qty="1" data-id="${p.id}" aria-label="Aumentar ${esc(p.name)}" ${row.qty===20?'disabled':''}>+</button></div><button class="remove-item" data-remove="${p.id}">Quitar</button></div></div>`;}).join('')}</div><div class="bag-bottom"><div class="bag-total"><span>Total de tu selección</span><strong>${money(total)}</strong></div><p>Guarda tus piezas favoritas juntas. Puedes descargar la selección y volver a ella cuando quieras.</p><button class="button button-pine" data-action="prepare">Preparar mi selección <span aria-hidden="true">↗</span></button><button class="button button-outline" data-action="continue">Seguir mirando</button></div></div>`:emptyState('Aquí empieza tu rincón.','Agrega una pieza de la colección. Lo demás puede venir después.');
    if(state.panel==='bag' && panel.open){body.innerHTML=html;return;}
    openPanel('bag','Mi bolsa',html,true);
  }
  function openFavorites() {
    const items=products.filter(p=>state.favorites.has(p.id));
    openPanel('favorites','Mis favoritos',items.length?`<div class="drawer-content"><h2 class="panel-title">Para volver después.</h2><p class="panel-lead">Esas piezas que te hicieron detenerte un momento.</p><div class="result-list">${items.map(resultItem).join('')}</div><p class="detail-note" style="margin-top:25px">Tus favoritos quedan guardados en este navegador.</p></div>`:emptyState('Algo te va a gustar.','Toca el corazón de una pieza para encontrarla aquí cuando vuelvas.'),true);
  }
  function resultItem(p) {return `<button class="result-item" data-product="${p.id}"><img src="${esc(p.image)}" alt="" width="68" height="80"><span><strong>${esc(p.name)}</strong><small>${esc(p.subtitle)}</small><small>${money(p.price)}</small></span><span aria-hidden="true">↗</span></button>`;}
  function openSearch() {openPanel('search','Encuentra tu próxima pieza',`<div class="drawer-content"><label class="sr-only" for="search-query">Buscar en la colección</label><input id="search-query" type="search" class="search-input" placeholder="¿Qué estás buscando?" autocomplete="off"><p class="search-count" id="search-count" aria-live="polite">${products.length} piezas para descubrir</p><div class="result-list" id="search-results">${products.map(resultItem).join('')}</div></div>`,true);}
  function openArticle(id) {const a=content.articles.find(x=>x.id===id);if(!a)return;openPanel('article','El diario de PATIO',`<img class="article-cover" src="${esc(a.image)}" alt="${esc(a.title)}"><article class="article-body"><p class="eyebrow">${esc(a.category)} · ${esc(a.readTime)}</p><h2>${esc(a.title)}</h2>${a.body.map(s=>`<p>${esc(s)}</p>`).join('')}<button class="text-link" data-action="continue">Encuentra piezas para tu espacio <span aria-hidden="true">↗</span></button></article>`);}
  function prepareSelection() {openPanel('prepare','Tu selección PATIO',`<div class="drawer-content"><h2 class="panel-title">Hazle un lugar.</h2><p class="panel-lead">Dale un nombre a tu rincón y guarda la lista de piezas con sus cantidades y valores.</p><form class="selection-form" id="selection-form"><label for="selection-name">Nombre de tu selección</label><input id="selection-name" name="selection-name" value="Mi rincón afuera" maxlength="70" required autocomplete="off"><p class="detail-note">El archivo se descargará en tu dispositivo. Tu bolsa seguirá aquí.</p><button type="submit" class="button button-pine">Descargar selección <span aria-hidden="true">↓</span></button><button type="button" class="text-link" data-action="bag">Volver a mi bolsa <span aria-hidden="true">↗</span></button></form></div>`,true);}
  function downloadSelection(name) {
    if(!state.bag.length){renderBag();return;}
    const lines=['PATIO','Un poco de afuera.','',name,new Intl.DateTimeFormat('es-CL',{dateStyle:'long'}).format(new Date()),'','TU SELECCIÓN',''];
    state.bag.forEach(row=>{const p=byId.get(row.id);lines.push(`${row.qty} × ${p.name} — ${p.subtitle}`,`${p.colors[0].name} · ${money(p.price)} por unidad · ${money(row.qty*p.price)}`,'');});
    lines.push('TOTAL '+money(state.bag.reduce((s,x)=>s+byId.get(x.id).price*x.qty,0)),'Valores en pesos chilenos.','', 'Objetos para vivir afuera.','PATIO');
    const url=URL.createObjectURL(new Blob(['\uFEFF'+lines.join('\r\n')],{type:'text/plain;charset=utf-8'}));
    const link=document.createElement('a');link.href=url;link.download='PATIO-mi-seleccion.txt';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);
    toast('Tu selección está lista.');
  }
  function renderEditorial() {
    $('#space-options').innerHTML=content.collections.map((c,i)=>`<button class="space-option" data-collection="${esc(c.id)}"><span class="space-number">0${i+1}</span><span><strong>${esc(c.name)}</strong><small>${esc(c.eyebrow)}</small></span><span aria-hidden="true">↗</span></button>`).join('');
    $('#journal-grid').innerHTML=content.articles.map(a=>`<button class="journal-card" data-article="${esc(a.id)}"><div class="journal-image"><img src="${esc(a.image)}" alt="${esc(a.title)}" loading="lazy" width="900" height="700"></div><div class="journal-meta"><span>${esc(a.category)}</span><span>${esc(a.readTime)}</span></div><h3>${esc(a.title)}</h3><span class="read-link">Leer la historia ↗</span></button>`).join('');
    $('#faq-list').innerHTML=content.faq.map(f=>`<details><summary>${esc(f.question)}</summary><p>${esc(f.answer)}</p></details>`).join('');
  }
  const actions={
    search:openSearch, favorites:openFavorites, bag:()=>{state.panel=null;renderBag();}, prepare:prepareSelection,
    continue:()=>{closePanel();$('#coleccion').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});},
    menu:()=>openPanel('menu','Haz un poco de lugar',`<nav class="mobile-menu" aria-label="Menú móvil"><a href="#coleccion">La colección</a><a href="#espacios">Tus espacios</a><a href="#nosotros">Nuestra forma</a><a href="#diario">Diario</a><a href="#ayuda">Ayuda</a><button class="text-link" data-action="favorites">Mis favoritos <span aria-hidden="true">↗</span></button></nav>`,true),
    privacy:()=>openPanel('privacy','Privacidad',`<article class="privacy-body"><h2>Tu espacio también<br>es privado.</h2><p>La bolsa y los favoritos se guardan en el almacenamiento local de este navegador para que puedas volver a tu selección. No necesitas crear una cuenta.</p><p>El nombre de tu selección se utiliza sólo para preparar el archivo que descargas. No se envía a un servidor. La medición opcional con Google Analytics y Meta sólo se activa si está configurada y aceptas la finalidad correspondiente. Puedes cambiar tus preferencias en cualquier momento desde el pie de página.</p><p>Puedes eliminar la selección guardada desde aquí. Esto borra la bolsa y los favoritos de este navegador.</p><button class="button button-outline" data-action="clear-storage">Borrar mi selección guardada</button></article>`),
    'clear-storage':()=>{state.bag=[];state.favorites.clear();persist();renderCatalog();toast('Tu bolsa y favoritos se borraron de este navegador.');}
  };
  document.addEventListener('click',event=>{
    const button=event.target.closest('button,a');if(!button)return;
    const d=button.dataset;
    if(d.action && actions[d.action]){event.preventDefault();actions[d.action]();return;}
    if(d.product){openProduct(d.product);return;}
    if(d.favorite){const id=d.favorite;if(state.favorites.has(id))state.favorites.delete(id);else state.favorites.add(id);persist();const on=state.favorites.has(id);button.classList.toggle('selected',on);button.setAttribute('aria-pressed',on);button.setAttribute('aria-label',`${on?'Quitar':'Guardar'} ${byId.get(id).name} ${on?'de':'en'} favoritos`);toast(on?'Guardado en tus favoritos.':'Quitado de tus favoritos.');return;}
    if(d.add){addToBag(d.add);return;}if(d.addDetail){addToBag(d.addDetail,state.qty);return;}
    if(d.detailQty){state.qty=Math.max(1,Math.min(20,state.qty+Number(d.detailQty)));$('#detail-qty').textContent=state.qty;$('[data-detail-qty="-1"]').disabled=state.qty===1;$('[data-detail-qty="1"]').disabled=state.qty===20;return;}
    if(d.bagQty){const row=state.bag.find(x=>x.id===d.id),previous=row?.qty||0;if(row)row.qty=Math.max(1,Math.min(20,row.qty+Number(d.bagQty)));persist();if(row&&row.qty>previous)window.PATIO_ANALYTICS?.events.addToCart(row.id,row.qty-previous);renderBag();body.querySelector(`[data-bag-qty="${d.bagQty}"][data-id="${d.id}"]`)?.focus();return;}
    if(d.remove){state.bag=state.bag.filter(x=>x.id!==d.remove);persist();renderBag();return;}
    if(d.filter){state.filter=d.filter;state.collection=null;renderCatalog();return;}
    if(d.collection){state.collection=content.collections.find(x=>x.id===d.collection);state.filter='Todos';renderCatalog();$('#coleccion').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});toast(state.collection.name+' · selección PATIO');return;}
    if(d.article){window.PATIO_ANALYTICS?.events.viewArticle(d.article);openArticle(d.article);return;}
    if(button.matches('.mobile-menu a'))closePanel();
  });
  document.addEventListener('input',event=>{if(event.target.id!=='search-query')return;const q=normalize(event.target.value.trim());const list=products.filter(p=>normalize([p.name,p.subtitle,p.category,p.description].join(' ')).includes(q));$('#search-results').innerHTML=list.length?list.map(resultItem).join(''):'<p class="panel-lead">No encontramos esa pieza. Prueba con «luz», «madera» o «textiles».</p>';$('#search-count').textContent=`${list.length} ${list.length===1?'pieza':'piezas'} ${q?'encontradas':'para descubrir'}`;});
  document.addEventListener('submit',event=>{if(event.target.id!=='selection-form')return;event.preventDefault();const input=$('#selection-name');const name=input.value.trim();if(!name){input.setCustomValidity('Escribe un nombre para tu selección.');input.reportValidity();return;}input.setCustomValidity('');downloadSelection(name);});
  document.addEventListener('input',event=>{if(event.target.id==='selection-name')event.target.setCustomValidity('');});
  $('#sort-products').addEventListener('change',event=>{state.sort=event.target.value;renderCatalog();});
  renderCatalog();renderEditorial();updateBagCount();
  window.PATIO_ANALYTICS?.events.pageView({path:location.pathname,title:document.title});
  const entry = new URLSearchParams(location.search);
  if(byId.has(entry.get('product')))openProduct(entry.get('product'));
  else if(content.articles.some(a=>a.id===entry.get('article'))){openArticle(entry.get('article'));window.PATIO_ANALYTICS?.events.viewArticle(entry.get('article'));}
})();
