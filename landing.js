(() => {
  'use strict';
  const events = window.PATIO_ANALYTICS?.events;
  if (!events) return;
  events.pageView({path:location.pathname,title:document.title});
  const {patioSection, patioId} = document.body.dataset;
  if (!patioId) return;
  if (patioSection === 'product' && window.PATIO_CONTENT?.products.some(item=>item.id===patioId)) events.viewItem(patioId);
  if (patioSection === 'article' && window.PATIO_CONTENT?.articles.some(item=>item.id===patioId)) events.viewArticle(patioId);
})();
