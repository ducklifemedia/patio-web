# PATIO · Un poco de afuera

Sitio de una marca conceptual de Ducklify: catálogo, piezas para inspirar y un diario para vivir mejor los espacios pequeños. No acepta pedidos ni pagos.

Sitio: https://red-cliff-062c48b0f.4.azurestaticapps.net

Archivos estáticos sin instalación de dependencias. Para consulta local: `python -m http.server 8174 --bind 127.0.0.1`.

La rama `main` publica por GitHub Actions en Azure Static Web Apps Free. El secreto `AZURE_STATIC_WEB_APPS_API_TOKEN` se guarda únicamente en GitHub Secrets. El workflow genera `_site` con una selección explícita de archivos públicos; no publica scripts de construcción, Git o documentos del ERP.

La medición sólo carga servicios si existen identificadores reales y se otorga consentimiento a cada finalidad. El catálogo sigue funcionando sin esos servicios. No hay procesamiento de pagos ni eventos de compra ficticios.

Los activos de marca no incluyen licencia abierta para su reutilización. Las fuentes incluyen sus respectivas licencias en `assets/fonts`.
