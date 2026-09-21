"""Durable PATIO test payments on Azure Storage Table (not Cosmos).

Runtime dependency: azure-data-tables==12.7.0; imported only by from_env/CAS.
Provision the table separately. This repository never creates or deletes it.
All indexes share the seller's test partition so each change is atomic.
Transport errors are ambiguous: do not repeat a mutation or release a reservation.
"""
from __future__ import annotations

import hashlib
from itertools import islice
import json
import os
import re
from urllib.parse import urlsplit

from domain import DomainError
from payments import (fail, remaining_timeout, bridge_enabled, make_bridge_event,
                      validate_bridge_page, validate_bridge_ack)


CHECKOUT_FIELDS = (
    'request_id', 'order_id', 'fingerprint', 'key_hash', 'snapshot', 'stage',
    'preference_id', 'checkout_url', 'seller_id', 'created_at',
)
PAYMENT_FIELDS = (
    'payment_id', 'order_id', 'status', 'refunded', 'provider_updated', 'checked_at',
)
MAX_PAYMENTS_PER_ORDER = 100
_CAS_ATTEMPTS = 3
_NO_RETRY = dict(retry_total=0, retry_connect=0, retry_read=0, retry_status=0,
                 retry_to_secondary=False, logging_enable=False)


def _unavailable():
    raise DomainError('payment_storage_unavailable',
                      'No pudimos confirmar la persistencia del pago. Conserva el intento para revisarlo.', 503) from None


class _StorageConflict(Exception):
    """Only definite HTTP conflicts may cause a fresh read/CAS attempt."""
    def __init__(self, status, code=None):
        self.status = status
        self.code = getattr(code, 'value', code)


class AzureTablePaymentRepository:
    """Same row contract as SQLitePaymentRepository, with conditional transactions.

    client is a TableClient or an injected in-memory double. Tests may inject the
    match_condition token as well, without importing the Azure SDK. In production
    it is always azure.core.MatchConditions.IfNotModified.
    """
    def __init__(self, client, seller_id, *, match_condition=None):
        if not re.fullmatch(r'[0-9]{1,25}', str(seller_id)):
            fail('payment_storage_config', 'Falta el vendedor de prueba para persistir pagos.', 503)
        self.client = client
        self.seller_id = str(seller_id)
        self.partition = 'mp-test-' + self.seller_id
        self._match_condition = match_condition

    @classmethod
    def from_env(cls):
        """Read only dedicated private env vars; never log credentials or raw errors."""
        endpoint = os.environ.get('PATIO_MP_TABLE_ENDPOINT', '')
        table = os.environ.get('PATIO_MP_TABLE_NAME', 'PatioPaymentsTest')
        key = os.environ.get('PATIO_MP_TABLE_KEY', '')
        seller = os.environ.get('PATIO_MP_SELLER_ID', '')
        # Standard public Azure Storage only. No SAS in URLs, redirects or Cosmos.
        if (not re.fullmatch(r'https://[a-z0-9]{3,24}\.table\.core\.windows\.net/?', endpoint)
                or not re.fullmatch(r'[A-Za-z][A-Za-z0-9]{2,62}', table)
                or not key or not re.fullmatch(r'[0-9]{1,25}', seller)):
            fail('payment_storage_config', 'La persistencia de pagos aún no está configurada.', 503)
        try:
            from azure.core import MatchConditions
            from azure.core.credentials import AzureNamedKeyCredential
            from azure.data.tables import TableClient
            account = urlsplit(endpoint).hostname.split('.')[0]
            client = TableClient(endpoint=endpoint, table_name=table,
                                 credential=AzureNamedKeyCredential(account, key),
                                 connection_timeout=1, read_timeout=2,
                                 retry_backoff_factor=0, **_NO_RETRY)
        except Exception:
            raise DomainError('payment_storage_config', 'No se pudo inicializar la persistencia de pagos.', 503) from None
        return cls(client, seller, match_condition=MatchConditions.IfNotModified)

    @staticmethod
    def _key(kind, identity):
        # The original identifier is retained in the row; hashes keep keys and
        # parameterized range filters safe for arbitrary identifiers.
        return kind + '|' + hashlib.sha256(str(identity).encode('utf-8')).hexdigest()

    def _entity(self, key, row):
        return {'PartitionKey': self.partition, 'RowKey': key,
                **{k: v for k, v in row.items() if v is not None}}

    @staticmethod
    def _row(entity, fields):
        return {field: entity.get(field) for field in fields}

    @staticmethod
    def _io_options():
        # Connect + read together fit within the shared request budget. Socket
        # timeouts are not a hard wall clock; the caller checks the budget too.
        budget = remaining_timeout(3)
        return {**_NO_RETRY, 'connection_timeout': min(1, budget / 2),
                'read_timeout': min(2, budget / 2)}

    def _call(self, fn, *args, **kwargs):
        options = self._io_options()
        try:
            result = fn(*args, **kwargs, **options)
        except Exception as exc:
            status = getattr(exc, 'status_code', None)
            if status is None:
                status = getattr(getattr(exc, 'response', None), 'status_code', None)
            if status in (404, 409, 412):
                raise _StorageConflict(status, getattr(exc, 'error_code', None)) from None
            # No raw SDK message: it can include URLs, headers and account details.
            _unavailable()
        remaining_timeout()
        return result

    def _get(self, key):
        try:
            return self._call(self.client.get_entity, partition_key=self.partition, row_key=key)
        except _StorageConflict as exc:
            if exc.status == 404 and exc.code in ('ResourceNotFound', 'EntityNotFound'):
                return None
            _unavailable()

    def _cas(self, entity):
        etag = getattr(entity, 'metadata', {}).get('etag')
        if not etag or etag == '*':
            _unavailable()
        if self._match_condition is None:
            try:
                from azure.core import MatchConditions
                self._match_condition = MatchConditions.IfNotModified
            except ImportError:
                _unavailable()
        return {'mode': 'replace', 'etag': etag, 'match_condition': self._match_condition}

    def _transaction(self, operations):
        try:
            self._call(self.client.submit_transaction, operations)
            return True
        except _StorageConflict as exc:
            if ((exc.status == 409 and exc.code in ('EntityAlreadyExists', 'ResourceAlreadyExists'))
                    or (exc.status == 412 and exc.code in ('UpdateConditionNotSatisfied', 'ConditionNotMet'))):
                return False
            _unavailable()

    def get_checkout(self, *, request_id=None, order_id=None):
        if request_id is not None:
            index = self._get(self._key('request', request_id))
            if index is None:
                return None
            order_id = index['order_id']
        if order_id is None:
            return None
        entity = self._get(self._key('order', order_id))
        if entity is None:
            if request_id is not None:
                _unavailable()  # An index must never outlive its durable reservation.
            return None
        return self._row(entity, CHECKOUT_FIELDS)

    def reserve_checkout(self, row):
        row = {field: row[field] for field in CHECKOUT_FIELDS}
        if (row['seller_id'] != self.seller_id or row['stage'] != 'creating'
                or row['preference_id'] is not None or row['checkout_url'] is not None):
            fail('payment_storage_config', 'Reserva de prueba incompatible con el vendedor.', 503)
        old = self.get_checkout(request_id=row['request_id'])
        if old is not None:
            return old, False
        order = self._entity(self._key('order', row['order_id']), row)
        index = self._entity(self._key('request', row['request_id']),
                             {'request_id': row['request_id'], 'order_id': row['order_id']})
        if self._transaction([('create', index), ('create', order)]):
            return dict(row), True
        old = self.get_checkout(request_id=row['request_id'])
        if old is not None:
            return old, False
        # A collision on order_id cannot be treated as a successful reservation.
        fail('idempotency_conflict', 'El identificador del pedido ya pertenece a otro intento.', 409)

    def finish_checkout(self, order_id, preference_id, checkout_url):
        for _ in range(_CAS_ATTEMPTS):
            entity = self._get(self._key('order', order_id))
            if entity is None:
                fail('checkout_not_found', 'Intento no reconocido.', 404)
            if entity['stage'] == 'ready':
                if entity.get('preference_id') != preference_id:
                    fail('recovery_conflict', 'El intento ya tiene otra preferencia confirmada.', 409)
                return self._row(entity, CHECKOUT_FIELDS)
            alias = self._get(self._key('preference', preference_id))
            if alias is not None:
                if alias['order_id'] != order_id:
                    fail('recovery_conflict', 'La preferencia ya está vinculada a otro intento.', 409)
                # A concurrent commit may have happened after reading the order.
                continue
            row = self._row(entity, CHECKOUT_FIELDS)
            row.update(stage='ready', preference_id=preference_id, checkout_url=checkout_url)
            alias = self._entity(self._key('preference', preference_id),
                                 {'order_id': order_id, 'preference_id': preference_id})
            operations = [('create', alias),
                          ('update', self._entity(entity['RowKey'], row), self._cas(entity))]
            if bridge_enabled(row):
                operations.extend(self._bridge_operations(row, [], 'checkout.ready', None))
            if self._transaction(operations):
                return row
        _unavailable()

    def mark_uncertain(self, order_id):
        for _ in range(_CAS_ATTEMPTS):
            entity = self._get(self._key('order', order_id))
            if entity is None or entity['stage'] != 'creating':
                return
            row = self._row(entity, CHECKOUT_FIELDS)
            row['stage'] = 'uncertain'
            if self._transaction([('update', self._entity(entity['RowKey'], row), self._cas(entity))]):
                return
        _unavailable()

    def _order_payment_key(self, order_id, payment_id):
        return self._key('orderpay', order_id) + '|' + self._key('p', payment_id).split('|')[1]

    def payments_for_order(self, order_id):
        # One bounded range/page, never a global scan or an N+1 lookup per payment.
        prefix = self._key('orderpay', order_id) + '|'
        options = self._io_options()
        try:
            pages = self.client.query_entities(
                query_filter='PartitionKey eq @seller and RowKey ge @lower and RowKey lt @upper',
                parameters={'seller': self.partition, 'lower': prefix, 'upper': prefix[:-1] + '}'},
                results_per_page=MAX_PAYMENTS_PER_ORDER + 1, **options).by_page()
            page = next(pages, ())
            entities = list(islice(page, MAX_PAYMENTS_PER_ORDER + 1))
        except Exception:
            _unavailable()
        remaining_timeout()
        if len(entities) > MAX_PAYMENTS_PER_ORDER or pages.continuation_token:
            fail('payment_history_limit', 'El historial de este intento necesita revisión.', 503)
        rows = [self._row(entity, PAYMENT_FIELDS) for entity in entities]
        return sorted(rows, key=lambda row: row['provider_updated'], reverse=True)

    def upsert_payment_if_newer(self, payment):
        row = {field: payment[field] for field in PAYMENT_FIELDS}
        key = self._key('payment', row['payment_id'])
        orderkey = self._order_payment_key(row['order_id'], row['payment_id'])
        for _ in range(_CAS_ATTEMPTS):
            previous = self._get(key)
            if previous is not None:
                if previous['order_id'] != row['order_id']:
                    fail('payment_mismatch', 'Pago ya vinculado a otro intento.', 409)
                if previous['provider_updated'] >= row['provider_updated']:
                    return
                # CAS on canonical payment gates the index replacement atomically.
                operations = [('update', self._entity(key, row), self._cas(previous)),
                              ('upsert', self._entity(orderkey, row), {'mode': 'replace'})]
            else:
                operations = [('create', self._entity(key, row)),
                              ('create', self._entity(orderkey, row))]
            checkout = self._get(self._key('order', row['order_id']))
            if checkout is not None and bridge_enabled(checkout):
                head = self._get(self._key('bridge-head', row['order_id']))
                if head is None:
                    _unavailable()
                current = self.payments_for_order(row['order_id'])
                current = [p for p in current if p['payment_id'] != row['payment_id']] + [row]
                current.sort(key=lambda p: (p['provider_updated'], p['payment_id']), reverse=True)
                operations.extend(self._bridge_operations(checkout, current, 'payment.observed', head))
            if self._transaction(operations):
                return
        _unavailable()

    def _bridge_operations(self, checkout, payments, kind, head):
        sequence = head['sequence'] + 1 if head is not None else 1
        event = make_bridge_event(checkout, sequence, payments, kind)
        next_head = self._entity(self._key('bridge-head', checkout['order_id']), {'sequence': sequence})
        head_change = ('update', next_head, self._cas(head)) if head is not None else ('create', next_head)
        row = {'event_id': event['id'], 'document': json.dumps(event, ensure_ascii=False, separators=(',', ':')), 'acknowledged': False}
        return [head_change, ('create', self._entity(self._key('bridge-event', event['id']), row)),
                ('create', self._entity('bridge-pending|' + event['id'], row))]

    def pull_bridge_events(self, limit=30, cursor=None):
        validate_bridge_page(limit, cursor)
        prefix = 'bridge-pending|'
        lower = prefix + cursor if cursor else prefix
        comparison = 'gt' if cursor else 'ge'
        try:
            pages = self.client.query_entities(
                query_filter=f'PartitionKey eq @seller and RowKey {comparison} @lower and RowKey lt @upper',
                parameters={'seller': self.partition, 'lower': lower, 'upper': 'bridge-pending}'},
                results_per_page=limit + 1, **self._io_options()).by_page()
            entities = list(islice(next(pages, ()), limit + 1))
        except Exception:
            _unavailable()
        remaining_timeout()
        if not entities and pages.continuation_token:
            _unavailable()
        selected = entities[:limit]
        more = len(entities) > limit or bool(pages.continuation_token)
        return {'events': [json.loads(row['document']) for row in selected],
                'nextCursor': selected[-1]['event_id'] if more and selected else None}

    def ack_bridge_events(self, event_ids):
        validate_bridge_ack(event_ids)
        for _ in range(_CAS_ATTEMPTS):
            operations = []
            for event_id in event_ids:
                canonical = self._get(self._key('bridge-event', event_id))
                if canonical is None:
                    fail('bridge_event_not_found', 'No se encuentra ese evento del puente.', 404)
                if canonical['acknowledged']:
                    continue
                pending = self._get('bridge-pending|' + event_id)
                if pending is None:
                    _unavailable()
                updated = self._entity(canonical['RowKey'], {'event_id': event_id, 'document': canonical['document'], 'acknowledged': True})
                delete_options = {k: v for k, v in self._cas(pending).items() if k != 'mode'}
                operations.extend([('update', updated, self._cas(canonical)), ('delete', pending, delete_options)])
            if not operations or self._transaction(operations):
                return {'acknowledged': event_ids}
        _unavailable()
