# PATIO · Un poco de afuera

Tienda de una marca conceptual de Ducklify: seis productos, tres guías, carrito persistente y pedidos de prueba en el ERP local. No acepta pagos reales, no reserva stock ni activa despachos. Mercado Pago queda preparado exclusivamente en modo de prueba y deshabilitado sin configuración.

Sitio: https://red-cliff-062c48b0f.4.azurestaticapps.net

Versión de trabajo: http://127.0.0.1:8765/artefactos/patio-web/ . El servidor del ERP (`app/run.py --port 8765` desde la raíz del ERP) proporciona el catálogo versionado y guarda los pedidos de prueba en `app/.data/commerce.sqlite3`, separado de los casos operativos.

El origen público indicado arriba conserva la entrega anterior hasta un despliegue explícito. Una publicación de estos archivos estáticos permitiría navegar y usar el carrito, pero no guardar pedidos: ese paso necesita la API de negocio. El frontend deshabilita la confirmación cuando no encuentra la API local. Nunca simula una respuesta de venta exitosa.

`assets/catalog.json` es la fuente de contenido. `python scripts/render_store.py` genera HTML inicial de productos, blog, portada y recorrido; también genera `assets/products.js`, sitemap y robots. No editar las páginas generadas por separado. La plantilla editorial de portada vive en `scripts/templates/home.html`. `python scripts/build_release.py` regenera y prepara únicamente los archivos públicos en `_site`.

`store.js` es la interacción vigente; los antiguos `app.js` y `landing.js` se conservan como antecedente, no se cargan ni entran en el paquete de publicación. El carrito nuevo usa `patio.cart.v2`; no migra la selección de la prueba anterior. Un pedido pendiente y su último comprobante se guardan en sesión para recuperarse de respuestas interrumpidas.

Las páginas de catálogo y diario tienen contenido legible sin JS, enlaces reales, canonical y JSON-LD fiel al contenido. Carrito, finalizar, comprobante y regreso de pago declaran noindex y quedan fuera del sitemap. Los productos conceptuales no declaran ofertas, stock o reseñas comerciales. Esto prepara el contenido para rastreo y extracción, sin garantizar presencia en buscadores o respuestas de IA.

La rama `main` publica por GitHub Actions en Azure Static Web Apps Free. El secreto `AZURE_STATIC_WEB_APPS_API_TOKEN` se guarda únicamente en GitHub Secrets. El workflow genera `_site` con una selección explícita de archivos públicos; no publica scripts de construcción, Git o documentos del ERP.

La medición sólo carga servicios si existen identificadores reales y se otorga consentimiento a cada finalidad. El catálogo sigue funcionando sin esos servicios. No hay cobros reales ni eventos de compra ficticios.

Validación y límites de esta etapa: `docs/casos/ERP-033-tienda-patio-geo/` en el ERP. Antes de vender: validar productos/precios/disponibilidad, definir despacho y postventa, implementar pago real y desplegar una API con acceso apropiado. La API de este piloto sólo escucha en loopback; no exponer todo el ERP a Internet.

Los activos de marca no incluyen licencia abierta para su reutilización. Las fuentes incluyen sus respectivas licencias en `assets/fonts`.

## Mercado Pago preparado (ERP-035)

`payments.js` integra el contrato `/api/patio/payments/`: configuración, creación de Checkout Pro, estado y reconciliación. La API de negocio mantiene precios, moneda y referencias; el navegador no acredita un pago con los parámetros de regreso. No hace falta SDK ni clave pública en el sitio. No hay credenciales en archivos públicos.

Sin configuración de prueba, Mercado Pago permanece deshabilitado y el pedido local demo sigue disponible. Un intento y su clave aleatoria se guardan antes del POST en `sessionStorage`; ante una respuesta incierta se conserva exactamente el mismo cuerpo. Sólo los errores garantizados por el backend como anteriores a la creación permiten liberar el intento y renovar el catálogo. La clave no se añade a URLs o analítica.

`/pago/` consulta el backend con la clave de sesión. Mantiene el carrito y permite cerrar explícitamente una prueba terminal confirmada; no libera intentos inciertos, en disputa o con devolución parcial. El estado de prueba nunca autoriza despacho ni activa Purchase. Los registros de sesión permanecen para la consulta del comprobante.

Pruebas de escritorio con servidor estático aislado y respuestas interceptadas: `docs/casos/ERP-035-mercadopago-patio/qa_frontend.py` desde la raíz del ERP. Evidencia en `qa-frontend/`. Las respuestas simuladas no acreditan una prueba oficial de Mercado Pago. Faltan credenciales/cuentas de prueba y un backend HTTPS publicado con retorno en el mismo origen de la tienda; publicar sólo esta web no habilita los pagos.

## Continuación ERP-039

El directorio `api/` prepara la API administrada de la misma Azure Static Web App, Python 3.11 y Azure Table Storage. El build estático no incluye `api/`; el workflow la construye y publica como Functions por separado en el mismo origen. `api/sources.json` fija las copias del núcleo de pagos y catálogo exportadas desde el ERP mediante `docs/casos/ERP-039-mercadopago-integracion/package_api.py`. No copiar `app/run.py`, datos, credenciales o módulos de Atención.

Las operaciones de prueba requieren `PATIO_MP_OPERATOR_KEY` además de la capacidad privada de cada pedido. La clave de operador se ingresa en el checkout y queda sólo en la sesión; no va en enlaces. El catálogo público indica `demoOrdersAvailable=false`, porque esta API no publica la creación de pedidos del ERP local. Sólo se admite modo `test`; toda configuración incompleta queda cerrada.

La cuenta test se comprobó por API el 21-09-2026. La publicación y las compras oficiales de prueba **aún no están acreditadas en este corte de preparación**; su evidencia se conserva en ERP-039. La propuesta de recurso/costo y el plan de operación están en `docs/casos/ERP-039-mercadopago-integracion/ARQUITECTURA.md` del ERP.
