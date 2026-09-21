"""PATIO / Mercado Pago Checkout Pro Preferences. Test accounts only; never live sales.

Local SQLite preparation. A public deployment needs durable storage and a dedicated
payment API; do not expose the ERP HTTP server to receive provider notifications.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, parse_qs, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
import uuid

from commerce import CommerceStore, _json
from domain import DomainError

_KEY = re.compile(r'[0-9a-f]{64}\Z')
_ID = re.compile(r'[0-9]{1,25}\Z')
_PREF = re.compile(r'[A-Za-z0-9-]{1,160}\Z')
_CHECKOUT_HOSTS = {'www.mercadopago.cl', 'www.mercadopago.com', 'mercadopago.cl', 'mercadopago.com'}
_REQUEST_DEADLINE = ContextVar('patio_payment_deadline', default=None)


@contextmanager
def request_budget(seconds=18):
    token=_REQUEST_DEADLINE.set(time.monotonic()+seconds)
    try: yield
    finally: _REQUEST_DEADLINE.reset(token)


def remaining_timeout(maximum=4):
    deadline=_REQUEST_DEADLINE.get()
    remaining=maximum if deadline is None else min(maximum,deadline-time.monotonic())
    if remaining<=0: fail('payment_timeout','La consulta no terminó a tiempo; conserva el intento.',503)
    return remaining


def now():
    return datetime.now(timezone.utc).isoformat()


def fail(code, message, status=400):
    raise DomainError(code, message, status)


def number(value):
    try:
        if isinstance(value, bool): raise ValueError()
        result = Decimal(str(value))
        if not result.is_finite(): raise ValueError()
        return result
    except (InvalidOperation, ValueError):
        fail('provider_mismatch', 'El proveedor devolvió un importe inválido.', 502)


def public_https(value):
    try:
        u = urlsplit(value)
        if (u.scheme != 'https' or not u.hostname or u.username or u.password
                or u.query or u.fragment or u.port not in (None,443)
                or u.hostname in {'localhost','localhost.localdomain'}
                or u.hostname.endswith(('.localhost','.local'))): return False
        try:
            if not ipaddress.ip_address(u.hostname).is_global: return False
        except ValueError: pass
        return True
    except (TypeError, ValueError): return False


def checkout_url(value):
    try:
        u = urlsplit(value)
        return (u.scheme == 'https' and u.hostname in _CHECKOUT_HOSTS
                and not u.username and not u.password and u.port in (None,443)
                and not u.fragment and ('/checkout/' in u.path))
    except (TypeError, ValueError): return False


@dataclass(frozen=True)
class PaymentConfig:
    mode: str = 'disabled'
    access_token: str = field(default='', repr=False)
    webhook_secret: str = field(default='', repr=False)
    seller_id: str = ''
    return_url: str = ''
    notification_url: str = ''

    @classmethod
    def from_env(cls):
        return cls(**{key:os.environ.get('PATIO_MP_'+key.upper(),default) for key,default in
                     [('mode','disabled'),('access_token',''),('webhook_secret',''),('seller_id',''),('return_url',''),('notification_url','')]})

    def problems(self):
        issues=[]
        if self.mode not in {'disabled','test'}: issues.append('mode_test_only')
        if not self.access_token: issues.append('access_token')
        if not self.webhook_secret: issues.append('webhook_secret')
        if not _ID.fullmatch(str(self.seller_id)): issues.append('seller_id')
        if not public_https(self.return_url): issues.append('https_return_url')
        if not public_https(self.notification_url): issues.append('https_notification_url')
        return issues

    def public(self):
        ready=self.mode=='test' and not self.problems()
        return {'provider':'mercadopago','integration':'checkout_pro_preferences','mode':'test' if ready else 'disabled',
                'available':ready,'livePaymentsAllowed':False,
                'message':'Prueba con una cuenta compradora de prueba; no uses una tarjeta real.' if ready else 'Mercado Pago está preparado, pero todavía no está conectado para pruebas.',
                'accountVerified':False}

    def require_test(self):
        if self.mode!='test' or self.problems():
            fail('payments_unavailable','Mercado Pago aún no está conectado para pruebas. No se realizó ningún cobro.',503)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None


class MercadoPagoClient:
    """Fixed hosts/paths, bounded calls, no automatic retries and no credential logs."""
    def __init__(self, config): self.config=config

    def call(self, method, path, payload=None, *, identity=False):
        host='https://api.mercadolibre.com' if identity else 'https://api.mercadopago.com'
        body=None if payload is None else _json(payload).encode('utf-8')
        request=Request(host+path,data=body,method=method,headers={'Authorization':'Bearer '+self.config.access_token,'Content-Type':'application/json','Accept':'application/json','User-Agent':'Ducklife-PATIO-test/0.1'})
        try:
            with build_opener(_NoRedirect()).open(request,timeout=remaining_timeout()) as response:
                raw=response.read(1_048_577)
                remaining_timeout()
                if len(raw)>1_048_576: raise ValueError('oversize')
                result=json.loads(raw.decode('utf-8'))
                if not isinstance(result,dict): raise ValueError('object required')
                return result
        except HTTPError as exc:
            # Do not relay the provider body or request headers to the browser.
            raise DomainError('provider_unavailable','Mercado Pago no pudo completar la consulta. Conserva este intento para revisarlo.',502) from exc
        except (URLError,TimeoutError,OSError,ValueError,UnicodeError) as exc:
            raise DomainError('provider_unavailable','No pudimos confirmar la respuesta de Mercado Pago. Conserva este intento.',502) from exc

    def verify_seller(self):
        # Read-only identity diagnosis also works before URLs/webhook are ready.
        # The mutating entry points independently require the full test config.
        if self.config.mode not in {'disabled','test'} or not self.config.access_token or not _ID.fullmatch(str(self.config.seller_id)):
            fail('payments_unavailable','Falta la identidad de prueba configurada.',503)
        account=self.call('GET','/users/me',identity=True)
        if (str(account.get('id'))!=str(self.config.seller_id) or account.get('site_id')!='MLC'
                or not isinstance(account.get('tags'),list) or 'test_user' not in account['tags']):
            fail('test_account_required','Se requiere la cuenta vendedora de prueba de Chile configurada. Los cobros reales están deshabilitados.',403)
        return account['id']

    def create_preference(self, body): return self.call('POST','/checkout/preferences',body)
    def get_preference(self, pref): return self.call('GET','/checkout/preferences/'+pref)
    def get_payment(self, payment): return self.call('GET','/v1/payments/'+payment)
    def get_merchant_order(self, order): return self.call('GET','/merchant_orders/'+order)


def verify_webhook(query, headers, body, secret, clock=time.time):
    """Strict signed payment topic; query ID wins and body must agree. No IPN."""
    if not secret or not isinstance(body,dict): fail('invalid_webhook','Notificación no autenticada.',401)
    q=parse_qs(query,keep_blank_values=True)
    values=q.get('data.id',[])
    if len(values)!=1 or not _ID.fullmatch(values[0]): fail('invalid_webhook','Identificador firmado inválido.',401)
    payment_id=values[0]
    request_id=headers.get('x-request-id','')
    if not re.fullmatch(r'[A-Za-z0-9-]{1,120}',request_id): fail('invalid_webhook','Solicitud no autenticada.',401)
    fields={}
    for part in headers.get('x-signature','').split(','):
        key,sep,value=part.strip().partition('=')
        if not sep or key in fields or key not in {'ts','v1'}: fail('invalid_webhook','Firma inválida.',401)
        fields[key]=value
    ts=fields.get('ts','');sig=fields.get('v1','')
    if not ts.isdigit() or len(ts) not in {10,13} or not _KEY.fullmatch(sig): fail('invalid_webhook','Firma inválida.',401)
    timestamp=int(ts)/(1000 if len(ts)==13 else 1)
    if abs(clock()-timestamp)>600: fail('expired_webhook','Firma fuera de la ventana aceptada.',401)
    manifest=f'id:{payment_id};request-id:{request_id};ts:{ts};'
    expected=hmac.new(secret.encode(),manifest.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig,expected): fail('invalid_webhook','Firma inválida.',401)
    if (body.get('type')!='payment' or q.get('type',['payment'])!=['payment']
            or not isinstance(body.get('data'),dict) or str(body['data'].get('id'))!=payment_id):
        fail('invalid_webhook','El recurso recibido no coincide con la firma.',400)
    # Payload flags are not trusted: the fetched merchant order must be test-only.
    return payment_id


class SQLitePaymentRepository:
    """Durable local implementation of the payment repository contract."""
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(self.connect()) as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS patio_mp_checkouts(
              request_id TEXT PRIMARY KEY, order_id TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL,
              key_hash TEXT NOT NULL, snapshot TEXT NOT NULL, stage TEXT NOT NULL,
              preference_id TEXT UNIQUE, checkout_url TEXT, seller_id TEXT NOT NULL, created_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS patio_mp_payments(
              payment_id TEXT PRIMARY KEY, order_id TEXT NOT NULL, status TEXT NOT NULL,
              refunded TEXT NOT NULL, provider_updated TEXT NOT NULL, checked_at TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS patio_mp_order_payments ON patio_mp_payments(order_id);''')

    def connect(self):
        db=sqlite3.connect(self.path,timeout=remaining_timeout(2),isolation_level=None);db.row_factory=sqlite3.Row;return db

    def get_checkout(self, *, request_id=None, order_id=None):
        column,value=('request_id',request_id) if request_id is not None else ('order_id',order_id)
        with closing(self.connect()) as db:
            row=db.execute(f'SELECT * FROM patio_mp_checkouts WHERE {column}=?',(value,)).fetchone()
            return dict(row) if row else None

    def reserve_checkout(self,row):
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM patio_mp_checkouts WHERE request_id=?',(row['request_id'],)).fetchone()
            if old:
                db.commit();return dict(old),False
            fields=('request_id','order_id','fingerprint','key_hash','snapshot','stage','preference_id','checkout_url','seller_id','created_at')
            db.execute('INSERT INTO patio_mp_checkouts VALUES(?,?,?,?,?,?,?,?,?,?)',tuple(row[k] for k in fields))
            db.commit();return dict(row),True

    def finish_checkout(self,order_id,preference_id,checkout_url):
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM patio_mp_checkouts WHERE order_id=?',(order_id,)).fetchone()
            if old is None: fail('checkout_not_found','Intento no reconocido.',404)
            if old['stage']=='ready' and old['preference_id']!=preference_id:
                fail('recovery_conflict','El intento ya tiene otra preferencia confirmada.',409)
            db.execute("UPDATE patio_mp_checkouts SET stage='ready',preference_id=?,checkout_url=? WHERE order_id=?",(preference_id,checkout_url,order_id))
            result=dict(db.execute('SELECT * FROM patio_mp_checkouts WHERE order_id=?',(order_id,)).fetchone())
            db.commit();return result

    def mark_uncertain(self,order_id):
        with closing(self.connect()) as db:
            db.execute("UPDATE patio_mp_checkouts SET stage='uncertain' WHERE order_id=? AND stage='creating'",(order_id,))

    def payments_for_order(self,order_id):
        with closing(self.connect()) as db:
            return [dict(p) for p in db.execute('SELECT * FROM patio_mp_payments WHERE order_id=? ORDER BY provider_updated DESC',(order_id,))]

    def upsert_payment_if_newer(self,payment):
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT * FROM patio_mp_payments WHERE payment_id=?',(payment['payment_id'],)).fetchone()
            if previous and previous['order_id']!=payment['order_id']: fail('payment_mismatch','Pago ya vinculado a otro intento.',409)
            if previous and previous['provider_updated']>=payment['provider_updated']:
                db.commit();return
            fields=('payment_id','order_id','status','refunded','provider_updated','checked_at')
            db.execute('INSERT INTO patio_mp_payments VALUES(?,?,?,?,?,?) ON CONFLICT(payment_id) DO UPDATE SET status=excluded.status,refunded=excluded.refunded,provider_updated=excluded.provider_updated,checked_at=excluded.checked_at',tuple(payment[k] for k in fields))
            db.commit()


class PaymentStore:
    def __init__(self,path,commerce,config=None,client=None,*,repository=None):
        self.path=Path(path) if path is not None else None
        self.commerce=commerce;self.config=config or PaymentConfig.from_env()
        self.client=client or MercadoPagoClient(self.config)
        self.repository=repository if repository is not None else SQLitePaymentRepository(self.path)

    def connect(self):
        """Compatibility for local operator checks; unavailable for cloud repositories."""
        return self.repository.connect()

    def configuration(self): return self.config.public()

    @staticmethod
    def key_hash(key):
        if not isinstance(key,str) or not _KEY.fullmatch(key): fail('invalid_access_key','La sesión de pago no es válida.',400)
        return hashlib.sha256(key.encode()).hexdigest()

    def authorized(self,body):
        if not isinstance(body,dict) or set(body)-{'orderId','accessKey','paymentId'} or not {'orderId','accessKey'}<=set(body):
            fail('invalid_request','Solicitud de consulta inválida.')
        digest=self.key_hash(body['accessKey'])
        row=self.repository.get_checkout(order_id=str(body['orderId']))
        if row is None or not hmac.compare_digest(digest,row['key_hash']): fail('checkout_not_found','No se encontró este intento en la sesión.',404)
        return row

    def create(self,body):
        self.config.require_test()
        if not isinstance(body,dict) or 'accessKey' not in body: fail('invalid_request','Falta la sesión del intento.')
        digest=self.key_hash(body['accessKey'])
        order_body={k:v for k,v in body.items() if k!='accessKey'}
        request_id,fingerprint=CommerceStore._validate(order_body)
        # Look up before network/catalog so a retry recovers the immutable accepted snapshot.
        old=self.repository.get_checkout(request_id=request_id)
        if old:
            self._same(old,fingerprint,digest)
            return self._checkout_result(old,True)
        self.client.verify_seller()
        catalog=self.commerce.catalog()
        if catalog['version']!=body['catalogVersion']: fail('catalog_changed','El catálogo cambió. Revisa sus precios antes de continuar.',409)
        products={p['id']:p for p in catalog['products']};lines=[]
        for item in body['items']:
            p=products.get(item['id'])
            if p is None or p['price']<=0: fail('invalid_product','Una pieza no está disponible para esta prueba.')
            lines.append({'id':p['id'],'name':p['name'],'qty':item['qty'],'unitPrice':p['price'],'lineTotal':item['qty']*p['price']})
        total=sum(x['lineTotal'] for x in lines)
        if total>10_000_000: fail('test_limit','El importe excede el límite de esta prueba.')
        order_id=str(uuid.uuid4())
        snapshot={'id':order_id,'createdAt':now(),'mode':'test','currency':'CLP','items':lines,'total':total,'shipping':0,'customer':{'name':body['customer']['name'].strip()},'delivery':'demo_pickup'}
        row,created=self.repository.reserve_checkout({'request_id':request_id,'order_id':order_id,'fingerprint':fingerprint,
            'key_hash':digest,'snapshot':_json(snapshot),'stage':'creating','preference_id':None,'checkout_url':None,
            'seller_id':str(self.config.seller_id),'created_at':now()})
        if not created:
            self._same(row,fingerprint,digest);return self._checkout_result(row,True)
        body=self.preference(snapshot)
        try:
            pref=self.client.create_preference(body)
            self._validate_preference(pref,snapshot)
            row=self.repository.finish_checkout(order_id,pref['id'],pref['init_point'])
            return self._checkout_result(row,False)
        except Exception:
            try: self.repository.mark_uncertain(order_id)
            except Exception: pass  # A durable 'creating' reservation is also uncertain; never repeat the POST.
            # This endpoint has no documented provider idempotency guarantee. Never retry POST automatically.
            fail('checkout_uncertain','No pudimos confirmar la creación del checkout. Conserva este intento para revisarlo; no se repetirá automáticamente.',409)

    @staticmethod
    def _same(row,fingerprint,digest):
        if row['fingerprint']!=fingerprint or not hmac.compare_digest(row['key_hash'],digest):
            fail('idempotency_conflict','El identificador del intento ya pertenece a otra selección o sesión.',409)

    def _checkout_result(self,row,replayed):
        if row['stage']!='ready': fail('checkout_uncertain','Este intento necesita revisión antes de abrir otro checkout. Conserva la misma sesión.',409)
        snapshot=json.loads(row['snapshot'])
        return {'replayed':replayed,'checkout':{'orderId':row['order_id'],'preferenceId':row['preference_id'],'checkoutUrl':row['checkout_url'],'mode':'test','total':snapshot['total'],'currency':'CLP'}}

    def preference(self,snapshot):
        return_url=self.config.return_url+'?'+urlencode({'order':snapshot['id']})
        return {'items':[{'id':i['id'],'title':'PATIO PRUEBA · '+i['name'],'quantity':i['qty'],'unit_price':i['unitPrice'],'currency_id':'CLP'} for i in snapshot['items']],
                'external_reference':snapshot['id'],'metadata':{'patio_order_id':snapshot['id'],'environment':'test'},
                'back_urls':{k:return_url for k in ('success','failure','pending')},'auto_return':'approved',
                'notification_url':self.config.notification_url,'binary_mode':False,
                'expires':True,'expiration_date_to':(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat()}

    def _validate_preference(self,pref,snapshot):
        if (not isinstance(pref,dict) or not _PREF.fullmatch(str(pref.get('id','')))
                or not checkout_url(pref.get('init_point','')) or str(pref.get('collector_id'))!=str(self.config.seller_id)
                or pref.get('external_reference')!=snapshot['id']):
            fail('provider_mismatch','La preferencia recibida no corresponde a este intento de prueba.',502)
        expected=sorted((i['id'],i['qty'],Decimal(i['unitPrice'])) for i in snapshot['items'])
        try: actual=sorted((i['id'],i['quantity'],number(i['unit_price'])) for i in pref['items'] if i['currency_id']=='CLP')
        except (KeyError,TypeError): fail('provider_mismatch','Items de preferencia inválidos.',502)
        if actual!=expected or len(pref['items'])!=len(expected): fail('provider_mismatch','La preferencia no conserva los importes del pedido.',502)

    def status(self,body):
        row=self.authorized(body);snap=json.loads(row['snapshot'])
        payments=self.repository.payments_for_order(row['order_id'])
        approved=[p for p in payments if p['status']=='approved' and number(p['refunded'])<snap['total']]
        active=[p for p in payments if p['status'] in {'pending','in_process','authorized'}]
        returns=[p for p in payments if p['status']=='refunded' or number(p['refunded'])>0]
        if row['stage']!='ready': state='needs_review'
        elif any(p['status'] in {'charged_back','in_mediation'} for p in payments): state='test_disputed'
        elif len(approved)>1: state='needs_review'
        elif active and (approved or returns): state='needs_review'
        elif approved: state='test_partially_refunded' if number(approved[0]['refunded'])>0 else 'test_approved'
        elif any(p['status']=='refunded' or number(p['refunded'])>=snap['total'] for p in payments): state='test_refunded'
        elif any(p['status'] in {'pending','in_process','authorized','in_mediation'} for p in payments): state='test_pending'
        elif payments: state='test_rejected'
        else: state='awaiting_payment'
        return {'payment':{'orderId':row['order_id'],'mode':'test','status':state,'currency':'CLP','total':snap['total'],'items':snap['items'],'fulfillmentAllowed':False,'realPayment':False,'checkedAt':max((p['checked_at'] for p in payments),default=None)}}

    def reconcile(self,body):
        row=self.authorized(body)
        payment_id=body.get('paymentId')
        if not isinstance(payment_id,str) or not _ID.fullmatch(payment_id): fail('invalid_payment_id','Falta un identificador de pago válido.')
        self.config.require_test();self.client.verify_seller()
        self._ingest(payment_id,expected_order=row['order_id'])
        return self.status(body)

    def webhook(self,query,headers,body):
        self.config.require_test()
        payment_id=verify_webhook(query,headers,body,self.config.webhook_secret)
        self.client.verify_seller()
        self._ingest(payment_id)
        return {'received':True}

    def _ingest(self,payment_id,expected_order=None):
        payment=self.client.get_payment(payment_id)
        if str(payment.get('id'))!=payment_id: fail('provider_mismatch','Pago no coincidente.',502)
        order_id=payment.get('external_reference')
        if not isinstance(order_id,str) or (expected_order and order_id!=expected_order): fail('payment_mismatch','Este pago pertenece a otro pedido.',409)
        row=self.repository.get_checkout(order_id=order_id)
        if row is None: fail('checkout_not_found','Intento no reconocido.',404)
        if row['stage']!='ready': fail('checkout_pending','La preferencia aún no está confirmada; la notificación puede reintentarse.',503)
        snap=json.loads(row['snapshot'])
        if (type(payment.get('live_mode')) is not bool or str(payment.get('collector_id'))!=row['seller_id']
                or payment.get('currency_id')!='CLP' or number(payment.get('transaction_amount'))!=snap['total']):
            fail('payment_mismatch','No coinciden el entorno, vendedor, moneda o importe de la prueba.',409)
        merchant=(payment.get('order') or {}).get('id')
        if not _ID.fullmatch(str(merchant or '')): fail('payment_mismatch','Falta la orden comercial asociada.',409)
        mo=self.client.get_merchant_order(str(merchant))
        # Official test accounts can produce payment.live_mode=True. The
        # authenticated merchant order supplies the test classification. Both
        # callers verify the configured seller's MLC/test_user identity first.
        if (mo.get('is_test') is not True
                or str(mo.get('id'))!=str(merchant) or mo.get('preference_id')!=row['preference_id']
                or mo.get('external_reference')!=order_id
                or str((mo.get('collector') or {}).get('id'))!=row['seller_id']
                or not any(str(p.get('id'))==payment_id for p in mo.get('payments',[]))):
            fail('payment_mismatch','El pago no corresponde a la preferencia del pedido.',409)
        state=payment.get('status')
        if state not in {'approved','pending','in_process','authorized','in_mediation','rejected','cancelled','refunded','charged_back'}:
            fail('provider_mismatch','Estado de pago no reconocido.',502)
        refunded=number(payment.get('transaction_amount_refunded',0))
        if not 0<=refunded<=snap['total']: fail('provider_mismatch','Importe devuelto inválido.',502)
        try:
            updated=datetime.fromisoformat(payment['date_last_updated'].replace('Z','+00:00'))
            if updated.tzinfo is None: raise ValueError()
            updated=updated.astimezone(timezone.utc).isoformat()
        except (KeyError,ValueError,TypeError,AttributeError): fail('provider_mismatch','Fecha de pago no verificable.',502)
        self.repository.upsert_payment_if_newer({'payment_id':payment_id,'order_id':order_id,'status':state,
            'refunded':str(refunded),'provider_updated':updated,'checked_at':now()})

    def recover_preference(self,order_id,preference_id):
        """Local operator only after inspecting provider records; deliberately no HTTP endpoint."""
        self.config.require_test();self.client.verify_seller()
        if not _PREF.fullmatch(preference_id): fail('invalid_preference','Identificador de preferencia inválido.')
        row=self.repository.get_checkout(order_id=order_id)
        if row is None or row['stage']=='ready': fail('recovery_unavailable','El intento no requiere esta recuperación.',409)
        pref=self.client.get_preference(preference_id)
        self._validate_preference(pref,json.loads(row['snapshot']))
        self.repository.finish_checkout(order_id,pref['id'],pref['init_point'])
        return {'orderId':order_id,'recovered':True,'mode':'test'}
