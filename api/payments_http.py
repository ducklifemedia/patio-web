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
BRIDGE_HEADER='x-patio-bridge-key'
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
    bridge_key: str=field(default='',repr=False)

    def __post_init__(self):
        u=urlsplit(self.origin)
        if u.scheme!='https' or not u.hostname or u.username or u.password or u.path or u.query or u.fragment or u.port not in (None,443):
            raise ValueError('An exact HTTPS storefront origin is required')
        if self.bridge_key and self.bridge_key == self.operator_key:
            raise ValueError('The bridge requires a separate private key')


class PaymentApplication:
    def __init__(self,payments,catalog,config,*,bridge=None):
        self.payments=payments;self.catalog=catalog;self.config=config;self.bridge=bridge

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
        critical={'origin','content-type','content-length',OPERATOR_HEADER,BRIDGE_HEADER,'x-signature','x-request-id'}
        if any(len(v)!=1 for k,v in values.items() if k in critical):
            raise DomainError('ambiguous_headers','Cabeceras ambiguas.',400)
        h={k:v[0] for k,v in values.items()}
        parts=urlsplit(url);path=parts.path
        bridge_path=path in {'/api/patio/orders-bridge/pull','/api/patio/orders-bridge/ack'}
        if path not in {'/api/patio/catalog','/api/patio/payments/config',*('/api/patio/payments/'+a for a in _ACTIONS)} and not bridge_path:
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
        if bridge_path:
            bridge_authenticated=bool(_KEY.fullmatch(self.config.bridge_key) and _KEY.fullmatch(h.get(BRIDGE_HEADER,''))
                                     and hmac.compare_digest(self.config.bridge_key,h[BRIDGE_HEADER]))
            if not bridge_authenticated:
                raise DomainError('bridge_access_required','El puente requiere su acceso privado.',401)
            if self.bridge is None:
                raise DomainError('bridge_unavailable','El puente de pedidos está deshabilitado.',503)
        elif not webhook and not authenticated:
            raise DomainError('test_access_required','Ingresa la clave privada de esta ronda de pruebas.',401)
        if not bridge_path and not self.payments: raise DomainError('payments_unavailable','Mercado Pago todavía no está configurado para pruebas.',503)
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
        if bridge_path:
            if path.endswith('/pull'):
                if set(body)-{'limit','cursor'}: raise DomainError('invalid_request','Campos de lectura del puente inválidos.',400)
                result=self.bridge.pull_bridge_events(limit=body.get('limit',30),cursor=body.get('cursor'))
            else:
                if set(body)!={'eventIds'}: raise DomainError('invalid_request','Campos de reconocimiento del puente inválidos.',400)
                result=self.bridge.ack_bridge_events(body['eventIds'])
            return self.response(200,result)
        if webhook:
            if any(k not in h for k in ('x-signature','x-request-id')):
                raise DomainError('invalid_webhook','Firma ausente.',401)
            return self.response(200,self.payments.webhook(parts.query,h,body))
        action=path.rsplit('/',1)[1]
        result=getattr(self.payments,{'checkout':'create'}.get(action,action))(body)
        return self.response(201 if action=='checkout' and not result['replayed'] else 200,result)
