/* PATIO · medición mínima con consentimiento por finalidad. Sin SDK hasta aceptar. */
(() => {
  'use strict';
  if (window.PATIO_ANALYTICS) return;
  const cfg = window.PATIO_ANALYTICS_CONFIG || {};
  const originAllowed = new URL(location.href).protocol === 'https:' && Array.isArray(cfg.productionOrigins) && cfg.productionOrigins.includes(location.origin);
  const content = window.PATIO_CONTENT || {};
  const products = new Map((content.products || []).map(p => [p.id, p]));
  const articles = new Map((content.articles || []).map(a => [a.id, a]));
  const gaId = originAllowed && /^G-[A-Z0-9]{6,20}$/.test(cfg.ga4MeasurementId || '') ? cfg.ga4MeasurementId : '';
  const metaId = originAllowed && /^\d{5,25}$/.test(cfg.metaPixelId || '') ? cfg.metaPixelId : '';
  const key = 'patio.consent.v1';
  const signature = `${cfg.consentVersion || 1}:${gaId}:${metaId}`;
  const basePath = new URL(document.currentScript?.src || './analytics.js', location.href).pathname.replace(/analytics\.js$/, '');
  const globalPrivacyControl = navigator.globalPrivacyControl === true;
  const state = {analytics:false, marketing:false, remember:false, chosen:false,
    google:!originAllowed ? 'inactive_origin' : gaId ? 'not_loaded' : 'unconfigured',
    meta:!originAllowed ? 'inactive_origin' : metaId ? 'not_loaded' : 'unconfigured'};
  const sentPage = {google:null, meta:null};
  let currentPage = null;
  let banner, dialog, lastFocus;

  function readPreferences() {
    for (const storageName of ['sessionStorage', 'localStorage']) {
      try {
        const storage = window[storageName];
        const p = JSON.parse(storage.getItem(key) || 'null');
        if (!p || p.signature !== signature || !Number.isFinite(p.expires) || p.expires < Date.now()) continue;
        return {analytics:p.analytics === true, marketing:p.marketing === true, remember:p.remember === true, chosen:true};
      } catch (_) { /* El sitio sigue funcionando sin almacenamiento. */ }
    }
    return {};
  }
  Object.assign(state, readPreferences());
  state.analytics = Boolean(gaId && state.analytics);
  state.marketing = Boolean(metaId && state.marketing && !globalPrivacyControl);

  function campaignParams() {
    const incoming = new URL(location.href).searchParams, clean = new URLSearchParams();
    const allowed = cfg.allowedUtm || {};
    for (const key of ['utm_source','utm_medium','utm_campaign','utm_content']) {
      const value = incoming.get(key);
      if (value && /^[a-z0-9_-]{1,64}$/.test(value) && Array.isArray(allowed[key]) && allowed[key].includes(value)) clean.set(key, value);
    }
    return clean;
  }
  function canonicalPage(path) {
    try {
      const u = new URL(path || location.pathname, location.origin);
      if (u.origin !== location.origin) return null;
      let route = u.pathname;
      if (basePath !== '/' && route.startsWith(basePath)) route = '/' + route.slice(basePath.length);
      route = route.replace(/\/index\.html$/, '/').replace(/\/+$/, '') || '/';
      const fixed = {'/':'PATIO · Un poco de afuera', '/productos':'La colección · PATIO', '/blog':'El diario · PATIO'};
      let title = fixed[route];
      if (!title) {
        const match = route.match(/^\/(productos|blog)\/([a-z0-9-]+)$/);
        if (!match) return null;
        const item = (match[1] === 'productos' ? products : articles).get(match[2]);
        if (!item) return null;
        title = `${item.name || item.title} · PATIO`;
      }
      const canonical = route === '/' ? '/' : route + '/';
      const query = campaignParams().toString();
      return {path:canonical, title, url:location.origin + basePath.replace(/\/$/, '') + canonical + (query ? '?' + query : '')};
    } catch (_) { return null; }
  }
  // Meta lee la URL actual por su cuenta. No cargamos SDK sobre una URL arbitraria.
  function prepareProviderUrl() {
    const safe = canonicalPage(location.pathname);
    if (!safe) return false;
    const hash = /^#(inicio|coleccion|espacios|nosotros|diario|ayuda)$/.test(location.hash) ? location.hash : '';
    const clean = new URL(safe.url); clean.hash = hash;
    const selectedProduct = new URL(location.href).searchParams.get('product');
    if (safe.path === '/' && products.has(selectedProduct)) clean.searchParams.set('product', selectedProduct);
    const selectedArticle = new URL(location.href).searchParams.get('article');
    if (safe.path === '/' && articles.has(selectedArticle)) clean.searchParams.set('article', selectedArticle);
    if (clean.href !== location.href) {
      try { history.replaceState(history.state, '', clean.href); } catch (_) { return false; }
    }
    return true;
  }
  function loadScript(id, src, provider) {
    const script = document.createElement('script');
    script.id = id; script.async = true; script.src = src;
    script.referrerPolicy = 'no-referrer';
    script.onload = () => {state[provider] = 'loaded';};
    script.onerror = () => {state[provider] = 'blocked';};
    state[provider] = 'loading';
    document.head.append(script);
  }
  function startGoogle() {
    if (!gaId || !state.analytics || state.google !== 'not_loaded' || !prepareProviderUrl()) return;
    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
    window['ga-disable-' + gaId] = false;
    window.gtag('consent', 'default', {analytics_storage:'denied', ad_storage:'denied', ad_user_data:'denied', ad_personalization:'denied'});
    window.gtag('consent', 'update', {analytics_storage:'granted', ad_storage:'denied', ad_user_data:'denied', ad_personalization:'denied'});
    window.gtag('set', 'ads_data_redaction', true);
    window.gtag('set', 'url_passthrough', false);
    window.gtag('js', new Date());
    const page = currentPage || canonicalPage(location.pathname);
    window.gtag('config', gaId, {
      send_page_view:false, allow_google_signals:false, allow_ad_personalization_signals:false,
      page_location:page.url, page_title:page.title, page_referrer:'', cookie_flags:'SameSite=Lax;Secure',
      ...(cfg.debug === true ? {debug_mode:true} : {})
    });
    loadScript('patio-ga4', 'https://www.googletagmanager.com/gtag/js?id=' + gaId, 'google');
  }
  function startMeta() {
    if (!metaId || !state.marketing || state.meta !== 'not_loaded' || !prepareProviderUrl()) return;
    if (!window.fbq) {
      const fbq = function () { if (fbq.callMethod) fbq.callMethod.apply(fbq, arguments); else fbq.queue.push(arguments); };
      fbq.push = fbq; fbq.loaded = true; fbq.version = '2.0'; fbq.queue = [];
      window.fbq = fbq; window._fbq = fbq;
    }
    window.fbq.disablePushState = true;
    window.fbq('consent', 'grant');
    window.fbq('set', 'autoConfig', false, metaId);
    window.fbq('init', metaId); // Sin advanced matching, emails, teléfonos ni datos de cliente.
    loadScript('patio-meta', 'https://connect.facebook.net/en_US/fbevents.js', 'meta');
  }
  function ga(name, params) {
    if (!state.analytics || !gaId || !['loading','loaded'].includes(state.google)) return false;
    const page = currentPage || canonicalPage(location.pathname);
    if (!page || !prepareProviderUrl()) return false;
    window.gtag('event', name, {send_to:gaId, page_location:page.url, page_title:page.title, page_referrer:'', ...params});
    return true;
  }
  function meta(name, params, custom=false) {
    if (!state.marketing || !metaId || !['loading','loaded'].includes(state.meta) || !prepareProviderUrl()) return false;
    window.fbq(custom ? 'trackSingleCustom' : 'trackSingle', metaId, name, params);
    return true;
  }
  function sendCurrentPage() {
    if (!currentPage) return;
    if (sentPage.google !== currentPage.path && ga('page_view', {})) sentPage.google = currentPage.path;
    if (sentPage.meta !== currentPage.path && meta('PageView', {})) sentPage.meta = currentPage.path;
  }
  function itemEvent(name, id, quantity) {
    const p = products.get(id);
    if (!p || !Number.isInteger(quantity) || quantity < 1 || quantity > 20 || !Number.isFinite(p.price) || p.price < 0) return false;
    const item = {item_id:p.id, item_name:p.name, item_brand:'PATIO', item_category:p.category, price:p.price, quantity};
    const value = Math.round(p.price * quantity);
    ga(name, {currency:'CLP', value, items:[item]});
    meta(name === 'view_item' ? 'ViewContent' : 'AddToCart', {
      content_ids:[p.id], content_type:'product', content_name:p.name,
      contents:[{id:p.id, quantity, item_price:p.price}], currency:'CLP', value
    });
    return true;
  }
  const events = Object.freeze({
    pageView: (details={}) => {
      const page = canonicalPage(details.path);
      if (!page) return false;
      currentPage = page;
      startGoogle(); startMeta(); sendCurrentPage();
      return true;
    },
    viewItem: id => itemEvent('view_item', id, 1),
    addToCart: (id, quantity=1) => itemEvent('add_to_cart', id, quantity),
    viewArticle: id => {
      const a = articles.get(id); if (!a) return false;
      ga('view_article', {content_id:a.id, content_group:a.category});
      meta('ReadArticle', {content_id:a.id, content_category:a.category}, true);
      return true;
    }
  });
  function clearCookies(kind) {
    const match = kind === 'google' ? /^(_ga(?:_|$)|_gid$|_gat(?:_|$))/ : /^_fb[pc]$/;
    const host = location.hostname;
    const pieces = host.split('.');
    const domains = ['', host, ...pieces.slice(0,-1).map((_, i) => '.' + pieces.slice(i).join('.'))];
    for (const pair of document.cookie.split(';')) {
      const name = pair.trim().split('=')[0];
      if (!match.test(name)) continue;
      for (const domain of domains) document.cookie = `${name}=; Max-Age=0; Path=/; SameSite=Lax${domain ? '; Domain=' + domain : ''}`;
    }
  }
  function consent(next={}) {
    const previous = {...state};
    state.analytics = Boolean(gaId && next.analytics === true);
    state.marketing = Boolean(metaId && next.marketing === true && !globalPrivacyControl);
    state.remember = next.remember === true;
    state.chosen = true;
    const record = {analytics:state.analytics, marketing:state.marketing, remember:state.remember, signature, expires:Date.now() + Math.max(1, Math.min(Number(cfg.preferenceDays) || 90, 180)) * 86400000};
    for (const storageName of ['localStorage', 'sessionStorage']) { try {window[storageName].removeItem(key);} catch (_) {} }
    try {window[state.remember ? 'localStorage' : 'sessionStorage'].setItem(key, JSON.stringify(record));} catch (_) {}
    if (previous.analytics && !state.analytics) {
      window['ga-disable-' + gaId] = true;
      // Borra nuestros eventos en cola si la persona revoca antes de terminar la descarga.
      if (state.google === 'loading' && Array.isArray(window.dataLayer)) {
        for (let i=window.dataLayer.length-1; i>=0; i--) if (window.dataLayer[i]?.[0] === 'event') window.dataLayer.splice(i,1);
      }
      window.gtag?.('consent', 'update', {analytics_storage:'denied', ad_storage:'denied', ad_user_data:'denied', ad_personalization:'denied'});
      clearCookies('google');
    }
    if (previous.marketing && !state.marketing) {
      if (state.meta === 'loading' && Array.isArray(window.fbq?.queue)) window.fbq.queue = window.fbq.queue.filter(args => !String(args[0]).startsWith('track'));
      window.fbq?.('consent', 'revoke');
      clearCookies('meta');
    }
    if (state.analytics && ['loading','loaded'].includes(state.google)) {
      window['ga-disable-' + gaId] = false;
      window.gtag('consent','update',{analytics_storage:'granted',ad_storage:'denied',ad_user_data:'denied',ad_personalization:'denied'});
    }
    if (state.marketing && ['loading','loaded'].includes(state.meta)) window.fbq('consent','grant');
    startGoogle(); startMeta(); sendCurrentPage();
    if (banner) banner.hidden = true;
    if (dialog?.open) dialog.close();
    return status();
  }
  function status() {
    return {environment:{origin:location.origin, allowed:originAllowed, reason:originAllowed ? 'Origen HTTPS autorizado.' : 'Medición desactivada fuera de los orígenes HTTPS de producción autorizados.'}, configured:{ga4:Boolean(gaId), meta:Boolean(metaId)}, consent:{analytics:state.analytics, marketing:state.marketing, remember:state.remember}, sdk:{ga4:state.google, meta:state.meta}, globalPrivacyControl, verification:'SDK preparado no acredita recepción de eventos.'};
  }
  function showPreferences() {
    if (!dialog) buildUI();
    dialog.querySelector('[name="patio-analytics"]').checked = state.analytics;
    dialog.querySelector('[name="patio-marketing"]').checked = state.marketing;
    dialog.querySelector('[name="patio-remember"]').checked = state.remember;
    lastFocus = document.activeElement;
    if (!dialog.open) dialog.showModal();
    dialog.querySelector('[data-patio-close]').focus();
  }
  function buildUI() {
    if (dialog || !document.body) return;
    banner = document.createElement('section');
    banner.className = 'patio-consent-banner'; banner.setAttribute('aria-label', 'Tu privacidad en PATIO');
    banner.hidden = state.chosen || (!gaId && !metaId);
    banner.innerHTML = '<div><span class="patio-consent-kicker">TU ESPACIO, TUS DECISIONES</span><h2>Un poco de privacidad.</h2><p>Podemos medir qué contenidos ayudan y cómo llegan las visitas desde redes. Tú eliges. Tu bolsa funciona igual.</p></div><div class="patio-consent-actions"><button type="button" data-patio-choice="reject">Sólo lo necesario</button><button type="button" data-patio-choice="preferences">Elegir</button><button type="button" class="patio-consent-accept" data-patio-choice="accept">Aceptar ambas</button></div>';
    dialog = document.createElement('dialog');
    dialog.className = 'patio-consent-dialog';
    dialog.setAttribute('aria-labelledby', 'patio-consent-title');
    dialog.setAttribute('aria-describedby', 'patio-consent-description');
    dialog.innerHTML = `<button type="button" class="patio-consent-close" data-patio-close aria-label="Cerrar preferencias">×</button><span class="patio-consent-kicker">TU ESPACIO, TUS DECISIONES</span><h2 id="patio-consent-title">A tu manera.</h2><p id="patio-consent-description">La bolsa y los favoritos se guardan en tu navegador. La medición es opcional y puedes cambiarla aquí cuando quieras.</p><form><label class="patio-consent-option"><input type="checkbox" name="patio-analytics" ${gaId?'':'disabled'}><span><strong>Entender las visitas</strong><small>Google Analytics: páginas, productos y selección local. ${gaId?'Sin nombres ni datos de tu selección.':'Todavía no está activo.'}</small></span></label><label class="patio-consent-option"><input type="checkbox" name="patio-marketing" ${metaId && !globalPrivacyControl?'':'disabled'}><span><strong>Medir contenido en redes</strong><small>Meta: visitas e interés desde Facebook e Instagram. ${globalPrivacyControl?'Desactivado por la señal de privacidad de tu navegador.':metaId?'No permite cobrarte ni enviar mensajes.':'Todavía no está activo.'}</small></span></label><label class="patio-consent-remember"><input type="checkbox" name="patio-remember"><span>Recordar mi elección en este equipo por ${Math.max(1,Math.min(Number(cfg.preferenceDays)||90,180))} días.</span></label><p class="patio-consent-note">Si no lo marcas, conservamos la elección sólo en esta pestaña durante la sesión. Puedes retirar permisos; los datos ya enviados no se recuperan desde aquí.</p><div class="patio-consent-actions"><button type="button" data-patio-choice="reject">Sólo lo necesario</button><button type="submit" class="patio-consent-accept">Guardar mi elección</button></div></form>`;
    document.body.append(banner, dialog);
    banner.addEventListener('click', choice);
    dialog.addEventListener('click', choice);
    dialog.querySelector('[data-patio-close]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => lastFocus?.focus());
    dialog.querySelector('form').addEventListener('submit', event => {
      event.preventDefault();
      consent({analytics:dialog.querySelector('[name="patio-analytics"]').checked, marketing:dialog.querySelector('[name="patio-marketing"]').checked, remember:dialog.querySelector('[name="patio-remember"]').checked});
    });
  }
  function choice(event) {
    const selected = event.target.closest('[data-patio-choice]')?.dataset.patioChoice;
    if (selected === 'preferences') showPreferences();
    if (selected === 'reject') consent({analytics:false, marketing:false, remember:dialog?.open ? dialog.querySelector('[name="patio-remember"]').checked : false});
    if (selected === 'accept') consent({analytics:true, marketing:true, remember:false});
  }
  document.addEventListener('click', event => {if (event.target.closest('[data-patio-consent]')) {event.preventDefault(); showPreferences();}});
  document.addEventListener('patio:page_view', event => events.pageView(event.detail || {}));
  document.addEventListener('patio:view_item', event => events.viewItem(event.detail?.id));
  document.addEventListener('patio:add_to_cart', event => events.addToCart(event.detail?.id, event.detail?.quantity));
  document.addEventListener('patio:view_article', event => events.viewArticle(event.detail?.id));
  window.PATIO_ANALYTICS = Object.freeze({events, consent, showPreferences, status});
  // No reproducir historial previo al consentimiento: sólo la página actual al aceptarlo.
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', buildUI, {once:true}); else buildUI();
})();
