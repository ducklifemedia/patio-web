"""Render crawlable PATIO pages from the public, conceptual catalog (stdlib only)."""
from html import escape
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'https://red-cliff-062c48b0f.4.azurestaticapps.net'
e = lambda value: escape(str(value), quote=True)
money = lambda value: '$' + f'{value:,}'.replace(',', '.')


def render():
    content = json.loads((ROOT / 'assets/catalog.json').read_text(encoding='utf-8'))
    products, articles = content['products'], content['articles']
    product_map = {p['id']: p for p in products}
    article_map = {a['id']: a for a in articles}
    pages = []
    # One source for build-time HTML, browser interactions and server prices.
    (ROOT / 'assets/products.js').write_text('window.PATIO_CONTENT = ' + json.dumps(content, ensure_ascii=False, indent=2) + ';\n', encoding='utf-8')

    def href(route, prefix):
        return prefix + route

    def header(prefix):
        return f'''<a class="skip-link" href="#contenido">Ir al contenido</a>
<div class="announcement"><span>UN POCO DE AFUERA</span><a href="{prefix}ayuda/">Colección conceptual · pedidos de prueba, sin cobros ↗</a></div>
<header class="site-header"><a class="brand" href="{prefix}" aria-label="PATIO, inicio"><img src="{prefix}assets/logo-pino.svg" width="176" height="62" alt="PATIO"></a>
<nav class="desktop-nav" aria-label="Navegación principal"><a href="{prefix}productos/">La colección</a><a href="{prefix}espacios/">Tus espacios</a><a href="{prefix}blog/">El diario</a><a href="{prefix}ayuda/">Ayuda y cuidados</a></nav>
<div class="header-actions"><a class="store-cart-link" href="{prefix}carrito/" aria-label="Ver carrito"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 8h14l1 13H4L5 8Z M8 8V6a4 4 0 0 1 8 0v2"/></svg><span>Mi carrito</span><b data-cart-count>0</b></a><button type="button" class="icon-button menu-trigger" data-menu aria-label="Abrir menú" aria-expanded="false">☰</button></div></header>
<nav class="store-mobile-nav" aria-label="Menú móvil" hidden><a href="{prefix}productos/">La colección</a><a href="{prefix}espacios/">Tus espacios</a><a href="{prefix}blog/">El diario</a><a href="{prefix}ayuda/">Ayuda y cuidados</a></nav>'''

    def footer(prefix):
        return f'''<footer class="site-footer"><div class="footer-top"><a href="{prefix}" aria-label="PATIO, inicio"><img src="{prefix}assets/logo-crema.svg" width="234" height="83" alt="PATIO"></a><p>Tu rincón favorito<br><em>todavía puede estar afuera.</em></p></div><div class="footer-links"><span>OBJETOS PARA VIVIR AFUERA</span><nav aria-label="Navegación del pie"><a href="{prefix}productos/">La colección</a><a href="{prefix}blog/">El diario</a><a href="{prefix}ayuda/">Ayuda y cuidados</a><a href="{prefix}privacidad/">Privacidad</a><a href="https://www.instagram.com/patio.por.ducklify/" rel="noopener noreferrer" target="_blank">Instagram ↗</a><a href="https://www.facebook.com/profile.php?id=61594524695593" rel="noopener noreferrer" target="_blank">Facebook ↗</a><button data-patio-consent>Preferencias de cookies</button></nav></div><div class="footer-bottom"><span>© 2026 PATIO · Una marca conceptual de Ducklify</span><span>Diseñado para disfrutar. Chile.</span><a href="#contenido">Volver arriba ↑</a></div></footer>'''

    def document(route, title, description, body, *, image='assets/images/hero.webp', schemas=(), section='', item_id='', noindex=False):
        prefix = '../' * len(route.strip('/').split('/')) if route else './'
        canonical = ORIGIN + '/' + route
        graph = [
            {'@type': 'Organization', '@id': ORIGIN + '/#organization', 'name': 'PATIO', 'url': ORIGIN + '/', 'description': 'Marca conceptual de Ducklify: ideas y objetos para balcones y terrazas techadas.', 'logo': ORIGIN + '/assets/logo-pino.svg', 'sameAs': ['https://www.instagram.com/patio.por.ducklify/', 'https://www.facebook.com/profile.php?id=61594524695593']},
            {'@type': 'WebSite', '@id': ORIGIN + '/#website', 'url': ORIGIN + '/', 'name': 'PATIO', 'inLanguage': 'es-CL', 'publisher': {'@id': ORIGIN + '/#organization'}},
            *schemas,
        ]
        structured = json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False).replace('<', '\\u003c')
        html = f'''<!doctype html>
<html lang="es-CL"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(description)}"><link rel="canonical" href="{canonical}">
<meta name="robots" content="{'noindex,follow' if noindex else 'index,follow,max-image-preview:large'}">
<meta property="og:type" content="{'article' if section == 'article' else 'website'}"><meta property="og:locale" content="es_CL"><meta property="og:site_name" content="PATIO"><meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(description)}"><meta property="og:url" content="{canonical}"><meta property="og:image" content="{ORIGIN}/{image}"><meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#24382f"><link rel="icon" href="{prefix}assets/favicon.svg" type="image/svg+xml"><link rel="preload" href="{prefix}assets/fonts/Manrope.woff" as="font" type="font/woff" crossorigin>
<link rel="stylesheet" href="{prefix}styles.css"><link rel="stylesheet" href="{prefix}landing.css"><link rel="stylesheet" href="{prefix}store.css"><link rel="stylesheet" href="{prefix}geo.css"><link rel="stylesheet" href="{prefix}payments.css"><link rel="stylesheet" href="{prefix}analytics.css">
<script type="application/ld+json">{structured}</script></head>
<body class="{'home-page' if not route else 'landing-page'}" data-store-root="{prefix}" data-patio-section="{section}" data-patio-id="{item_id}">
{header(prefix)}{body}{footer(prefix)}
<div class="store-toast" role="status" aria-live="polite" hidden></div>
<noscript><p class="noscript">Puedes leer toda la colección y el diario. Activa JavaScript para usar el carrito y preparar un pedido.</p></noscript>
<script defer src="{prefix}assets/products.js"></script><script defer src="{prefix}payments.js"></script><script defer src="{prefix}analytics-config.js"></script><script defer src="{prefix}analytics.js"></script><script defer src="{prefix}store.js"></script>
</body></html>'''
        target = ROOT / route / 'index.html'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html + '\n', encoding='utf-8')
        if not noindex:
            pages.append(canonical)

    def breadcrumbs(parts, prefix):
        links = [('Inicio', '')] + parts
        html = '<nav class="breadcrumbs" aria-label="Ruta de navegación"><ol>' + ''.join(f'<li><a href="{prefix}{path}">{e(label)}</a></li>' if i < len(links)-1 else f'<li aria-current="page">{e(label)}</li>' for i, (label, path) in enumerate(links)) + '</ol></nav>'
        schema = {'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': i+1, 'name': label, 'item': ORIGIN + '/' + path} for i, (label, path) in enumerate(links)]}
        return html, schema

    def card(p, prefix):
        return f'''<article class="product-card" data-category="{e(p['category'])}" data-price="{p['price']}" data-catalog-product="{p['id']}"><div class="product-image-wrap"><a class="product-open" href="{prefix}productos/{p['id']}/"><img src="{prefix}{p['image']}" alt="{e(p['name'] + ', ' + p['subtitle'])}" width="1024" height="1280" loading="lazy"></a><span class="product-tag">{e(p['tag'])}</span><button type="button" class="quick-add" data-add="{p['id']}" aria-label="Agregar {e(p['name'])} al carrito">+</button></div><div class="product-info"><div><h3 class="product-name"><a href="{prefix}productos/{p['id']}/">{e(p['name'])}</a></h3><p class="product-subtitle">{e(p['subtitle'])}</p></div><span class="product-price">{money(p['price'])}</span></div></article>'''

    def story(a, prefix):
        return f'''<article class="landing-story-card"><a class="landing-story-photo" href="{prefix}blog/{a['id']}/"><img src="{prefix}{a['image']}" alt="{e(a['title'])}" width="1200" height="900" loading="lazy"></a><div class="landing-meta"><span>{e(a['category'])}</span><span>{e(a['readTime'])} de lectura</span></div><h3><a href="{prefix}blog/{a['id']}/">{e(a['title'])}</a></h3><p class="landing-excerpt">{e(a['excerpt'])}</p><a class="text-link" href="{prefix}blog/{a['id']}/">Leer la guía <span aria-hidden="true">↗</span></a></article>'''

    def faq(items):
        return '<div class="faq-list">' + ''.join(f'<details><summary>{e(i.get("question", i.get("q", "")))}</summary><p>{e(i.get("answer", i.get("a", "")))}</p></details>' for i in items) + '</div>'

    def toolbar():
        return '<div class="catalog-toolbar"><div class="filters" role="group" aria-label="Filtrar colección">' + ''.join(f'<button class="filter {"active" if c == "Todos" else ""}" data-filter="{c}" aria-pressed="{"true" if c == "Todos" else "false"}">{"Todo" if c == "Todos" else c}</button>' for c in ['Todos', 'Muebles', 'Iluminación', 'Objetos', 'Textiles']) + '</div><label class="sort-label">Ordenar <select id="sort-products"><option value="featured">Selección PATIO</option><option value="low">Precio: menor a mayor</option><option value="high">Precio: mayor a menor</option></select></label></div>'

    home = (ROOT / 'scripts/templates/home.html').read_text(encoding='utf-8').replace('<main>', '<main id="contenido">')
    home = home.replace('<div class="product-grid" id="product-grid"></div>', '<div class="product-grid" id="product-grid">' + ''.join(card(p, './') for p in products) + '</div>')
    home = home.replace('<div class="journal-grid" id="journal-grid"></div>', '<div class="landing-story-grid">' + ''.join(story(a, './') for a in articles) + '</div>')
    home = home.replace('<div id="faq-list" class="faq-list"></div>', faq(content['faq']))
    home = home.replace('<div class="space-options" id="space-options"></div>', '<div class="space-options">' + ''.join(f'<a class="space-option" href="./espacios/#{c["id"]}"><span>{e(c["eyebrow"])}<small>{e(c["name"])}</small></span><span aria-hidden="true">↗</span></a>' for c in content['collections']) + '</div>')
    home = home.replace('<button class="hero-product" data-product="nido">', '<a class="hero-product" href="./productos/nido/">').replace('<span aria-hidden="true">↗</span></button>', '<span aria-hidden="true">↗</span></a>')
    document('', 'PATIO · Objetos para balcones y terrazas techadas', 'Ideas, muebles, iluminación y textiles para hacer lugar en un balcón o terraza techada. Descubre la colección PATIO y sus guías de cuidado.', home)

    crumbs, bc = breadcrumbs([('La colección', 'productos/')], '../')
    body = f'''<main id="contenido" class="landing-wrap">{crumbs}<div class="catalog-intro"><div><p class="eyebrow">LA COLECCIÓN ESENCIAL · 01—06</p><h1>Hazle lugar<br>a <em>lo cotidiano.</em></h1></div><div><p>Seis piezas para tu pausa de todos los días. Elige por uso, material o por ese rincón que ya tienes en mente.</p><p class="landing-aside-note">Precios de referencia en CLP. Colección conceptual: no hay venta ni stock confirmado.</p></div></div>{toolbar()}<p class="sr-only" id="catalog-status" aria-live="polite"></p><div class="product-grid catalog-grid-section" id="product-grid">{''.join(card(p, '../') for p in products)}</div></main>'''
    document('productos/', 'La colección · Muebles, luz y textiles | PATIO', 'Explora seis piezas PATIO para interiores y terrazas techadas. Materiales, medidas, cuidados y precios de referencia en pesos chilenos.', body, schemas=[bc, {'@type':'ItemList','itemListElement':[{'@type':'ListItem','position':i+1,'url':ORIGIN+'/productos/'+p['id']+'/'} for i,p in enumerate(products)]}])

    # A single useful hub for the existing curated sets, instead of thin duplicate pages.
    crumbs, bc = breadcrumbs([('Tus espacios', 'espacios/')], '../')
    groups = []
    for n, c in enumerate(content['collections'], 1):
        g = c['guide']
        links = ' + '.join(f'<a href="../productos/{pid}/">{e(product_map[pid]["name"])}</a>' for pid in c['productIds'])
        budget = sum(product_map[pid]['price'] for pid in c['productIds'])
        links += f'</p><p class="space-budget">{money(budget)}<small>Suma referencial: una unidad de cada pieza, en CLP. Sin descuento ni despacho; no es una oferta comercial.</small>'
        groups.append(f'''<section class="space-guide" id="{c['id']}"><div><p class="eyebrow">0{n} / {e(c['eyebrow'])}</p><h2>{e(c['name'])}</h2><p class="space-guide-pieces">{links}</p></div><div><h3>{e(g['question'])}</h3><p class="space-answer">{e(g['answer'])}</p><ol>{''.join(f'<li>{e(step)}</li>' for step in g['steps'])}</ol><p class="space-limit">{e(g['limit'])}</p><a class="text-link" href="../blog/{g['relatedArticle']}/">Leer la guía completa ↗</a></div></section>''')
    rows = []
    for p in products:
        measurements = ' '.join(f"{f['label']}: {f['value']}" for f in p['facts'] if f['label'] in p['measureFactLabels'])
        material_labels = {'Material', 'Materiales', 'Estructura', 'Asiento y respaldo', 'Funda', 'Composición'}
        materials = ' '.join(f"{f['label']}: {f['value']}" for f in p['facts'] if f['label'] in material_labels)
        rows.append(f'''<tr><th scope="row"><a href="../productos/{p['id']}/"><img src="../{p['image']}" alt="" width="54" height="68" loading="lazy"><span>{e(p['name'])}<small>{e(p['subtitle'])}</small></span></a></th><td>{e(p['selectionRole'])}<small class="comparison-materials">{e(materials)}</small></td><td>{e(measurements)}</td><td>{e(p['usageSummary'])}</td><td>{money(p['price'])}</td></tr>''')
    body = f'''<main id="contenido" class="landing-wrap space-index">{crumbs}<header class="catalog-intro"><div><p class="eyebrow">TUS ESPACIOS / UNA GUÍA PARA ELEGIR</p><h1>Elige por<br><em>cómo lo vives.</em></h1></div><p>Muebles y objetos para balcones y terrazas techadas. Empieza por el momento que quieres disfrutar; después, por las piezas que de verdad te sirven.</p></header><div class="space-intro"><img src="../assets/images/story.webp" alt="Muebles y textiles en una terraza techada PATIO" width="1024" height="1536" fetchpriority="high"><div><p class="eyebrow">ANTES DE LLENAR, IMAGINA</p><h2>Un propósito.<br><em>Tres maneras.</em></h2><p>¿Un café en el balcón, una pausa bajo techo o una conversación al atardecer? Estos conjuntos reúnen piezas de la colección para ayudarte a elegir. No son packs ni ofertas.</p><nav aria-label="Elegir por espacio">{''.join(f'<a href="#{c["id"]}">{e(c["eyebrow"])} <span aria-hidden="true">↓</span></a>' for c in content['collections'])}<a href="#comparar">Comparar las seis piezas <span aria-hidden="true">↓</span></a></nav></div></div>{''.join(groups)}<section class="space-comparison" id="comparar"><div class="landing-section-heading"><div><p class="eyebrow">LAS SEIS PIEZAS, EN PERSPECTIVA</p><h2>Lo que cambia<br><em>entre una y otra.</em></h2></div><p>Medidas y usos del catálogo conceptual.<br>Precios de referencia en CLP.</p></div><div class="comparison-scroll" role="region" aria-label="Comparación de productos PATIO" tabindex="0"><table class="comparison-table"><caption>Función, materiales, medidas y límites de las piezas PATIO</caption><thead><tr><th scope="col">Pieza</th><th scope="col">Función y materiales</th><th scope="col">Medidas</th><th scope="col">Uso y cuidado</th><th scope="col">Precio referencial</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div><div class="comparison-notes"><div><h3>La medida no es todo el espacio.</h3><p>Marca el tamaño de la pieza en el suelo y prueba abrir la puerta, sentarte y circular. No sumes anchos como si eso garantizara que un conjunto cabe.</p><a class="text-link" href="../blog/balcon-pequeno/">Cómo medir y distribuir ↗</a></div><div><h3>Si queda expuesto a la lluvia.</h3><p>Esta selección no se presenta como un conjunto apto para intemperie permanente. Para un balcón abierto, comprueba la resistencia indicada por el fabricante antes de elegir. Duna no tiene grado IP informado.</p><a class="text-link" href="../ayuda/">Uso, cuidados y alcance del catálogo ↗</a></div></div></section></main>'''
    hub_schema = {'@type':'CollectionPage','@id':ORIGIN+'/espacios/#page','url':ORIGIN+'/espacios/','name':'Muebles y objetos para balcones y terrazas techadas','description':'Guía de elección y comparación de seis piezas conceptuales PATIO.','inLanguage':'es-CL','isPartOf':{'@id':ORIGIN+'/#website'},'mainEntity':{'@type':'ItemList','itemListElement':[{'@type':'ListItem','position':i+1,'url':ORIGIN+'/productos/'+p['id']+'/'} for i,p in enumerate(products)]}}
    document('espacios/', 'Muebles y objetos para balcones y terrazas techadas | PATIO', 'Elige piezas por uso: balcón pequeño, terraza techada o atardecer. Compara función, materiales, medidas y cuidados de los seis productos PATIO.', body, image='assets/images/story.webp',schemas=[bc,hub_schema])

    for p in products:
        route, prefix = f'productos/{p["id"]}/', '../../'
        crumbs, bc = breadcrumbs([('La colección','productos/'), (p['name'], route)], prefix)
        facts = p.get('facts', [])
        fact_html = '<dl class="spec-table">' + ''.join(f'<div><dt>{e(f["label"])}</dt><dd>{e(f["value"])}</dd></div>' for f in facts) + '</dl>' if facts else '<ul>' + ''.join(f'<li>{e(x)}</li>' for x in p['details']) + '</ul>'
        guides = [article_map[x] for x in p.get('relatedArticles', []) if x in article_map] or articles[:1]
        fit = f'<p class="fit-note"><strong>Ideal para</strong> {e(p["fits"])}</p>' if p.get('fits') else ''
        avoid = f'<p class="fit-note"><strong>Ten en cuenta</strong> {e(p["avoid"])}</p>' if p.get('avoid') else ''
        body = f'''<main id="contenido" class="landing-wrap">{crumbs}<section class="product-hero"><figure class="product-main-photo"><img src="{prefix}{p['image']}" width="1024" height="1280" alt="{e(p['name'] + ': ' + p['subtitle'])}" fetchpriority="high"><figcaption>{e(p['tag'])}</figcaption></figure><div class="product-copy"><p class="eyebrow">PATIO / {e(p['category'])}</p><h1>{e(p['name'])}<em>{e(p['subtitle'])}</em></h1><p class="product-lead">{e(p['description'])}</p><p class="product-reference-price">{money(p['price'])}<span>CLP · Precio de referencia</span></p><div class="buy-row"><label class="quantity-field">Cantidad<input id="product-quantity" type="number" min="1" max="20" step="1" value="1" inputmode="numeric"></label><button type="button" class="button button-pine" data-add="{p['id']}" data-use-quantity>Agregar al carrito <span aria-hidden="true">+</span></button></div><p class="product-disclaimer">Pedido de prueba, sin cobro ni reserva de stock. <a href="{prefix}ayuda/">Cómo funciona ↗</a></p><p class="product-colors">Color: {e(', '.join(c['name'] for c in p['colors']))}</p>{fit}{avoid}<div class="product-facts"><h2>En detalle</h2>{fact_html}</div></div></section><section class="product-care"><div><p class="eyebrow">PARA QUE TE ACOMPAÑE</p><h2>Un poco de <em>cuidado.</em></h2></div><p>{e(p['care'])}</p></section><section class="product-questions"><div><p class="eyebrow">ANTES DE ELEGIR</p><h2>Buenas<br><em>preguntas.</em></h2></div>{faq(p.get('faq', []))}</section><section class="landing-related"><div class="landing-section-heading"><div><p class="eyebrow">DALE CONTEXTO</p><h2>Ideas para <em>acompañarlo.</em></h2></div><a class="text-link" href="{prefix}blog/">El diario ↗</a></div><div class="landing-story-grid two-stories">{''.join(story(a,prefix) for a in guides)}</div></section><section class="landing-related"><div class="landing-section-heading"><div><p class="eyebrow">OBJETOS QUE CONVERSAN</p><h2>Se llevan <em>bien.</em></h2></div></div><div class="product-grid">{''.join(card(x,prefix) for x in [x for x in products if x['id'] != p['id']][:3])}</div></section></main>'''
        product_schema = {'@type':'Product','@id':ORIGIN+'/'+route+'#product','url':ORIGIN+'/'+route,'name':p['name']+' · '+p['subtitle'],'description':p['description']+' Colección conceptual, no disponible para venta.','image':ORIGIN+'/'+p['image'],'brand':{'@type':'Brand','name':'PATIO'},'color':', '.join(c['name'] for c in p['colors']),'additionalProperty':[{'@type':'PropertyValue','name':f['label'],'value':f['value']} for f in facts]}
        collection_links = ' · '.join(f'<a href="{prefix}espacios/#{c["id"]}">{e(c["eyebrow"])}</a>' for c in content['collections'] if p['id'] in c['productIds'])
        body = body.replace('<div class="product-facts">', f'<p class="product-context-links">Imagínalo en: {collection_links}. <a href="{prefix}espacios/#comparar">Comparar piezas ↗</a></p><div class="product-facts">')
        document(route, p['name']+' · '+p['subtitle']+' | PATIO', p['description'], body, image=p['image'], schemas=[bc,product_schema], section='product', item_id=p['id'])

    crumbs, bc = breadcrumbs([('El diario', 'blog/')], '../')
    document('blog/', 'El diario de PATIO · Guías para balcones y terrazas', 'Ideas prácticas para organizar un balcón pequeño, elegir luz y cuidar muebles y textiles en terrazas techadas.', f'<main id="contenido" class="landing-wrap">{crumbs}<div class="catalog-intro"><div><p class="eyebrow">EL DIARIO DE PATIO</p><h1>Un lugar pequeño.<br><em>Muchas ideas.</em></h1></div><p>Guías concretas para elegir mejor, cuidar lo que tienes y disfrutar un poco más de afuera.</p></div><div class="landing-story-grid journal-index">'+''.join(story(a,'../') for a in articles)+'</div></main>', schemas=[bc])

    for a in articles:
        route, prefix = f'blog/{a["id"]}/', '../../'
        crumbs, bc = breadcrumbs([('El diario','blog/'), (a['title'],route)], prefix)
        sections = a.get('sections') or [{'id':f'paso-{i+1}','title':f'Paso {i+1}','paragraphs':[p]} for i,p in enumerate(a['body'])]
        prose = ''
        for i, s in enumerate(sections):
            prose += f'<section id="{e(s["id"])}"><span class="article-section-number">0{i+1}</span><h2>{e(s["title"])}</h2>' + ''.join(f'<p>{e(p)}</p>' for p in s['paragraphs'])
            if s.get('bullets'):
                prose += '<ul>'+''.join(f'<li>{e(x)}</li>' for x in s['bullets'])+'</ul>'
            prose += '</section>'
        checklist = '<aside class="article-checklist"><p class="eyebrow">PARA LLEVAR A LA PRÁCTICA</p><h2>Antes de empezar</h2><ul>'+''.join(f'<li>{e(x)}</li>' for x in a.get('checklist', []))+'</ul></aside>' if a.get('checklist') else ''
        related = [product_map[x] for x in a.get('relatedProducts',[]) if x in product_map] or products[:3]
        body = f'''<main id="contenido" class="landing-wrap">{crumbs}<header class="article-heading"><p class="eyebrow">EL DIARIO / {e(a['category'])}</p><h1>{e(a['title'])}</h1><p class="article-deck">{e(a['excerpt'])}</p><p class="article-byline"><span>Por Editorial PATIO</span><span>21 septiembre 2026</span><span>{e(a['readTime'])} de lectura</span></p></header><figure class="article-hero"><img src="{prefix}{a['image']}" alt="{e(a['title'])}" width="1536" height="1024" fetchpriority="high"><figcaption>Una idea de la colección conceptual PATIO para llevar a tu propio espacio.</figcaption></figure><div class="article-layout"><aside class="article-toc"><p class="eyebrow">EN ESTA GUÍA</p><ol>{''.join(f'<li><a href="#{e(s["id"])}">{e(s["title"])}</a></li>' for s in sections)}</ol><a class="text-link" href="{prefix}productos/">Explorar la colección ↗</a></aside><div class="article-prose">{prose}{checklist}{faq(a.get('faq',[]))}<p class="editorial-note">Criterio editorial de PATIO. Comprueba siempre las medidas y las instrucciones del fabricante de los objetos que uses. La colección mostrada es conceptual.</p></div></div><section class="landing-related"><div class="landing-section-heading"><div><p class="eyebrow">DE LA IDEA AL RINCÓN</p><h2>Piezas para <em>imaginarlo.</em></h2></div></div><div class="product-grid">{''.join(card(p,prefix) for p in related[:3])}</div></section><section class="further-reading"><div class="landing-section-heading"><h2>Una idea <em>más.</em></h2></div><div class="landing-story-grid two-stories">{''.join(story(x,prefix) for x in articles if x['id'] != a['id'])}</div></section></main>'''
        schema = {'@type':'BlogPosting','@id':ORIGIN+'/'+route+'#article','headline':a['title'],'description':a['excerpt'],'image':[ORIGIN+'/'+a['image']],'mainEntityOfPage':ORIGIN+'/'+route,'inLanguage':'es-CL','author':{'@type':'Organization','name':'Editorial PATIO','url':ORIGIN+'/ayuda/#editorial'},'publisher':{'@id':ORIGIN+'/#organization'}}
        matching_collection = next(c for c in content['collections'] if c['guide']['relatedArticle'] == a['id'])
        body = body.replace('<p class="editorial-note">', f'<p class="article-choice-link"><a class="text-link" href="{prefix}espacios/#{matching_collection["id"]}">Ver piezas y medidas para este espacio ↗</a></p><p class="editorial-note">')
        document(route, a['title']+' | PATIO', a['excerpt'], body, image=a['image'], schemas=[bc,schema], section='article',item_id=a['id'])

    crumbs, bc = breadcrumbs([('Mi carrito','carrito/')], '../')
    document('carrito/', 'Mi carrito | PATIO', 'Revisa las piezas de tu carrito PATIO y prepara un pedido de prueba.', f'''<main id="contenido" class="landing-wrap store-flow">{crumbs}<div class="flow-heading"><p class="eyebrow">01 / ELIGE TU RINCÓN</p><h1>Un lugar para<br><em>tus favoritos.</em></h1><a class="text-link" href="../productos/">Seguir mirando ↗</a></div><div id="cart-view" aria-live="polite"><p>Cargando tu carrito…</p></div></main>''', noindex=True,section='cart')
    crumbs, bc = breadcrumbs([('Mi carrito','carrito/'),('Preparar pedido','finalizar/')], '../')
    document('finalizar/', 'Preparar pedido | PATIO', 'Completa el recorrido de prueba de PATIO sin realizar un pago.', f'''<main id="contenido" class="landing-wrap store-flow">{crumbs}<div class="flow-heading"><p class="eyebrow">02 / TODO EN SU LUGAR</p><h1>Tu próxima<br><em>pausa.</em></h1><p>Este recorrido permite preparar un pedido y probar el pago.<br>No cobra dinero, no reserva stock ni solicita un despacho.</p></div><div class="checkout-grid"><section class="checkout-form"><div class="step-title"><span>01</span><h2>Dale un nombre</h2></div><form id="checkout-form"><label for="customer-name">Tu nombre o un alias</label><input id="customer-name" name="name" required maxlength="80" autocomplete="off" placeholder="Por ejemplo, Mi terraza"><p class="field-hint">Para reconocer el pedido. No necesitamos tu correo ni dirección.</p><div class="step-title"><span>02</span><h2>La entrega</h2></div><div class="delivery-option"><strong>Retiro simulado · $0</strong><p>Sin dirección, fecha ni entrega real. El despacho comercial se definirá al activar la tienda.</p></div><div class="step-title"><span>03</span><h2>El cierre</h2></div><div class="delivery-option"><strong>Pedido de prueba · sin cobro real</strong><p>La prueba de Mercado Pago requiere acceso privado. Guarda el intento y comprueba el resultado sin generar una compra real.</p></div><label class="checkbox-label"><input type="checkbox" name="accept" required><span>Entiendo que este pedido es de prueba y que el nombre o alias se guardará junto al intento. <a href="../privacidad/">Ver privacidad</a>.</span></label><p id="checkout-status" role="status" aria-live="polite">Verificando el catálogo…</p><button class="button button-pine" id="place-order" disabled>Guardar pedido de prueba <span aria-hidden="true">↗</span></button><section class="payment-option" aria-labelledby="mp-heading"><p class="eyebrow">OTRA FORMA DE PROBAR EL RECORRIDO</p><h3 id="mp-heading">Mercado Pago</h3><span class="payment-tag">SÓLO MODO DE PRUEBA</span><p>Abre el checkout externo con una cuenta compradora de prueba. No uses tarjetas reales. Esta prueba no genera una venta, reserva de stock ni despacho.</p><button type="button" class="button button-outline" id="mp-checkout" disabled>Abrir Mercado Pago · prueba ↗</button><p id="mp-checkout-status" role="status" aria-live="polite">Comprobando la conexión de prueba…</p></section></form></section><aside id="checkout-summary" class="order-summary"></aside></div></main>''', noindex=True,section='checkout')
    document('pedido/', 'Tu pedido de prueba | PATIO', 'Comprobante local del pedido de prueba PATIO.', '<main id="contenido" class="landing-wrap store-flow"><div id="order-receipt"><p>Cargando el comprobante de esta sesión…</p></div></main>',noindex=True,section='receipt')

    document('pago/', 'Mercado Pago · prueba | PATIO', 'Consulta segura del estado de un intento de pago de prueba PATIO.', '<main id="contenido" class="landing-wrap store-flow"><div id="payment-result"><p>Comprobando la sesión de tu intento de prueba…</p></div></main>', noindex=True,section='payment')

    crumbs, bc = breadcrumbs([('Ayuda y cuidados','ayuda/')], '../')
    helpbody = f'''<main id="contenido" class="landing-wrap help-page">{crumbs}<div class="catalog-intro"><div><p class="eyebrow">ANTES DE HACER LUGAR</p><h1>Elegir bien.<br><em>Disfrutar más.</em></h1></div><p>Lo que necesitas saber sobre la colección, el recorrido de compra y el cuidado de las piezas.</p></div><div class="help-columns"><section><h2>Sobre PATIO</h2><p>PATIO es una marca conceptual de Ducklify dedicada a imaginar objetos para interiores, balcones y terrazas techadas. Las imágenes, especificaciones y precios forman una colección de ejemplo. No acreditan stock, proveedores ni productos disponibles para comprar.</p><h2>Cómo funciona el pedido</h2><p>Agrega piezas al carrito, revisa cantidades y completa el recorrido con un nombre o alias. La prueba conserva el intento con sus productos, precios e importe. No genera una compra real, no reserva mercadería ni autoriza un despacho.</p><p>El carrito funciona en el navegador. El pago de prueba requiere la API disponible y el acceso privado de la ronda; la tienda pública no acepta ventas reales. Todos los importes están en pesos chilenos (CLP).</p><h2>Mercado Pago · prueba</h2><p>El checkout externo está reservado a pruebas privadas. Sólo se debe usar una cuenta compradora y medios de pago de prueba. El servidor comprueba la cuenta vendedora de prueba antes de preparar el checkout. Nunca uses una tarjeta real en este recorrido.</p><p>Al solicitar abrir el checkout, enviamos a Mercado Pago la referencia del intento, los productos, sus cantidades e importes en CLP; no enviamos tu nombre o alias. El regreso del proveedor no acredita un pago: el servidor consulta y comprueba su estado. Conservamos el intento en esta sesión para recuperar respuestas interrumpidas. Un pago de prueba aprobado no autoriza una compra ni un despacho, y no borra tu carrito. <a href="../privacidad/">Cómo se conservan estos datos</a>.</p><h2>Entrega y postventa</h2><p>El retiro de $0 es una opción simulada. Dirección, tarifas de despacho, medios de pago y condiciones de cambios y devoluciones deberán definirse con la operación comercial antes de habilitar ventas reales.</p><h2 id="editorial">Editorial PATIO</h2><p>Nuestro diario reúne ideas prácticas de distribución, luz y cuidado. Es contenido editorial de la marca: no son testimonios de clientes ni pruebas de resistencia de productos. Las fichas explicitan materiales y límites de uso; consulta también las indicaciones del fabricante de cada pieza real.</p><a class="text-link" href="../blog/">Ir al diario ↗</a></section><section>{faq(content['faq'])}</section></div></main>'''
    document('ayuda/', 'Ayuda, pedidos y cuidado de la colección | PATIO', 'Conoce PATIO, el alcance de sus pedidos de prueba, el cuidado de los materiales y el criterio de su diario editorial.', helpbody, schemas=[bc])

    (ROOT/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+''.join(f'  <url><loc>{url}</loc></url>\n' for url in pages)+'  <url><loc>'+ORIGIN+'/privacidad/</loc></url>\n</urlset>\n',encoding='utf-8')
    (ROOT/'robots.txt').write_text('User-agent: *\nAllow: /\n\nSitemap: '+ORIGIN+'/sitemap.xml\n',encoding='utf-8')
    print(f'Rendered {len(pages)+3} pages; {len(products)} products and {len(articles)} articles.')


if __name__ == '__main__':
    render()
