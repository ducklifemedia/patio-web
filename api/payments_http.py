"""Isolated PATIO test-payment HTTP contract. Never mounts the ERP handler.

The cloud adapter supplies raw method/path/headers/body to this module. No HTTP
server, tunnel, environment loading or resource creation occurs on import.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hmac
import json
import re
from urllib.parse import urlsplit

from commerce import CommerceStore
from domain import DomainError
from payments import PaymentConfig, request_budget

MAX_BODY=65_536
OPERATOR_HEADER='x-patio-test-key'
_KEY=re.compile(r'[0-9a-f]{64}\Z')
_ACTIONS={'checkout','status','reconcile','webhook'}


class ReadOnlyCatalog(CommerceStore):
    """Only the inherited catalog reader; no demo database is constructed."""
    def __init__(self,catalog_path):
        from pathlib import Path
        self.catalog_path=Path(catalog_path)


@dataclass(frozen=True)
class PaymentHTTPConfig:
    origin: str
    operator_key: str=field(default='',repr=False)

    def __post_init__(self):
        u=urlsplit(self.origin)
        if u.scheme!='https' or not u.hostname or u.username or u.password or u.path or u.query or u.fragment or u.port not in (None,443):
            raise ValueError('An exact HTTPS storefront origin is required')


class PaymentApplication:
    def __init__(self,payments,catalog,config):
        self.payments=payments;self.catalog=catalog;self.config=config

    @staticmethod
    def response(status,payload):
        return status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store',
            'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'},json.dumps(payload,ensure_ascii=False).encode('utf-8')

    def dispatch(self,method,url,headers,raw=b''):
        try:
            with request_budget(18): return self._dispatch(method,url,headers,raw)
        except DomainError as exc:
            return self.response(exc.status,{'error':{'code':exc.code,'message':exc.message}})
        except Exception:
            # Provider/SDK exceptions can contain signed URLs, keys or user data.
            return self.response(503,{'error':{'code':'payments_unavailable','message':'No pudimos comprobar el estado. Conserva el mismo intento.'}})

    def _dispatch(self,method,url,headers,raw):
        pairs=list(headers.items()) if hasattr(headers,'items') else list(headers)
        values={}
        for k,v in pairs: values.setdefault(k.lower(),[]).append(v)
        critical={'origin','content-type','content-length',OPERATOR_HEADER,'x-signature','x-request-id'}
        if any(len(v)!=1 for k,v in values.items() if k in critical):
            raise DomainError('ambiguous_headers','Cabeceras ambiguas.',400)
        h={k:v[0] for k,v in values.items()}
        parts=urlsplit(url);path=parts.path
        if path not in {'/api/patio/catalog','/api/patio/payments/config',*('/api/patio/payments/'+a for a in _ACTIONS)}:
            raise DomainError('not_found','Ruta no encontrada.',404)
        expected='GET' if path.endswith(('/catalog','/config')) else 'POST'
        if method!=expected: raise DomainError('method_not_allowed','Método no permitido.',405)
        if h.get('origin') not in (None,self.config.origin):
            raise DomainError('invalid_origin','Origen no permitido.',403)
        if parts.query and not path.endswith('/webhook'):
            raise DomainError('invalid_query','Esta ruta no admite parámetros de consulta.',400)
        authenticated=bool(_KEY.fullmatch(self.config.operator_key) and _KEY.fullmatch(h.get(OPERATOR_HEADER,''))
            and hmac.compare_digest(self.config.operator_key,h[OPERATOR_HEADER]))
        if path.endswith('/catalog'):
            return self.response(200,{**self.catalog.catalog(),'demoOrdersAvailable':False})
        if path.endswith('/config'):
            config=self.payments.configuration() if self.payments else PaymentConfig().public()
            if not authenticated:
                config={**config,'available':False,'mode':'disabled','message':'Integración de prueba privada; requiere acceso del operador.'}
            return self.response(200,{**config,'requiresOperator':True,'operatorAuthorized':authenticated,'demoOrdersAvailable':False})
        webhook=path.endswith('/webhook')
        if not webhook and not authenticated:
            raise DomainError('test_access_required','Ingresa la clave privada de esta ronda de pruebas.',401)
        if not self.payments: raise DomainError('payments_unavailable','Mercado Pago todavía no está configurado para pruebas.',503)
        if h.get('content-type','').split(';')[0].strip()!='application/json':
            raise DomainError('invalid_content_type','Envía JSON.',415)
        if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BODY:
            raise DomainError('invalid_body','Tamaño de solicitud inválido.',413)
        try:
            def unique(pairs):
                result={}
                for key,value in pairs:
                    if key in result: raise ValueError('duplicate JSON property')
                    result[key]=value
                return result
            body=json.loads(raw.decode('utf-8'),object_pairs_hook=unique,
                parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        except (ValueError,UnicodeError): raise DomainError('invalid_json','JSON inválido.',400)
        if not isinstance(body,dict): raise DomainError('invalid_request','Se requiere un objeto JSON.',400)
        if webhook:
            if any(k not in h for k in ('x-signature','x-request-id')):
                raise DomainError('invalid_webhook','Firma ausente.',401)
            return self.response(200,self.payments.webhook(parts.query,h,body))
        action=path.rsplit('/',1)[1]
        result=getattr(self.payments,{'checkout':'create'}.get(action,action))(body)
        return self.response(201 if action=='checkout' and not result['replayed'] else 200,result)
