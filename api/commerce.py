"""Pedidos de prueba de PATIO; sin cobro, reserva de stock ni despacho real."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
import uuid

from domain import DomainError, MAX_AMOUNT


_PRODUCT_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_VERSION = re.compile(r"[0-9a-f]{64}\Z")
_ORDER_FIELDS = {"requestId", "catalogVersion", "items", "customer", "delivery"}


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _valid_text(value, maximum: int) -> bool:
    return (isinstance(value, str) and 1 <= len(value) <= maximum
            and bool(value.strip())
            and not any(unicodedata.category(char) in {"Cc", "Cs"} for char in value))


def _object(value, fields: set[str], label: str):
    if not isinstance(value, dict) or set(value) != fields:
        raise DomainError("invalid_order", f"{label}: faltan campos o hay campos no permitidos.", 400)


class CommerceStore:
    """Almacén SQLite separado del ERP; una conexión corta por operación."""

    def __init__(self, path, catalog_path):
        self.path = Path(path)
        self.catalog_path = Path(catalog_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS patio_demo_orders (
                    request_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    order_id TEXT NOT NULL UNIQUE,
                    snapshot TEXT NOT NULL
                )
            """)

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        return connection

    def catalog(self) -> dict:
        """Proyecta sólo datos comerciales; cambios editoriales no vencen el carrito."""
        try:
            source = json.loads(self.catalog_path.read_text(encoding="utf-8-sig"))
            if (not isinstance(source, dict) or source.get("currency", "CLP") != "CLP"
                    or source.get("mode", "demo") != "demo"):
                raise ValueError("invalid catalog metadata")
            rows = source.get("products")
            if not isinstance(rows, list) or not rows:
                raise ValueError("invalid catalog products")
            products, known = [], set()
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("invalid product")
                product_id, name, price = row.get("id"), row.get("name"), row.get("price")
                if (not isinstance(product_id, str) or not _PRODUCT_ID.fullmatch(product_id)
                        or product_id in known or not _valid_text(name, 200)
                        or type(price) is not int or not 0 <= price <= MAX_AMOUNT):
                    raise ValueError("invalid product fields")
                known.add(product_id)
                products.append({"id": product_id, "name": name, "price": price})
            commercial = {"currency": "CLP", "mode": "demo",
                          "products": sorted(products, key=lambda product: product["id"])}
            version = hashlib.sha256(_json(commercial).encode("utf-8")).hexdigest()
            return {"version": version, "currency": "CLP", "mode": "demo", "products": products}
        except (OSError, ValueError, UnicodeError) as error:
            raise DomainError("catalog_unavailable", "El catálogo no está disponible. Intenta nuevamente.", 503) from error

    @staticmethod
    def _validate(body) -> tuple[str, str]:
        _object(body, _ORDER_FIELDS, "Pedido")
        request_id = body["requestId"]
        if not isinstance(request_id, str):
            raise DomainError("invalid_order", "El identificador de la solicitud debe ser un UUID.", 400)
        try:
            parsed_id = uuid.UUID(request_id)
        except (ValueError, AttributeError) as error:
            raise DomainError("invalid_order", "El identificador de la solicitud debe ser un UUID.", 400) from error
        if request_id.lower() != str(parsed_id):
            raise DomainError("invalid_order", "Usa el UUID completo de la solicitud, con guiones.", 400)
        if not isinstance(body["catalogVersion"], str) or not _VERSION.fullmatch(body["catalogVersion"]):
            raise DomainError("invalid_order", "La versión del catálogo no es válida.", 400)
        if body["delivery"] != "demo_pickup":
            raise DomainError("invalid_order", "Esta prueba sólo admite retiro simulado.", 400)
        _object(body["customer"], {"name"}, "Cliente")
        if not _valid_text(body["customer"]["name"], 80):
            raise DomainError("invalid_order", "Escribe un nombre o alias de 1 a 80 caracteres, sin caracteres de control.", 400)
        items = body["items"]
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise DomainError("invalid_order", "El pedido debe contener entre 1 y 100 productos distintos.", 400)
        known = set()
        for item in items:
            _object(item, {"id", "qty"}, "Producto")
            product_id, qty = item["id"], item["qty"]
            if not isinstance(product_id, str) or not _PRODUCT_ID.fullmatch(product_id):
                raise DomainError("invalid_order", "El identificador de producto no es válido.", 400)
            if product_id in known:
                raise DomainError("invalid_order", "Cada producto debe aparecer una sola vez en el pedido.", 400)
            if type(qty) is not int or not 1 <= qty <= 20:
                raise DomainError("invalid_order", "Cada cantidad debe ser un entero entre 1 y 20.", 400)
            known.add(product_id)
        # Conserva valores y orden de líneas: cambiar el pedido requiere otra clave.
        fingerprint = hashlib.sha256(_json(body).encode("utf-8")).hexdigest()
        return str(parsed_id), fingerprint

    def create_order(self, body) -> dict:
        request_id, fingerprint = self._validate(body)
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    saved = connection.execute(
                        "SELECT fingerprint, snapshot FROM patio_demo_orders WHERE request_id = ?",
                        (request_id,),
                    ).fetchone()
                    if saved:
                        if saved["fingerprint"] != fingerprint:
                            raise DomainError("idempotency_conflict", "Esta solicitud ya se usó para otro pedido. Revisa el carrito e inicia otra solicitud.", 409)
                        # Un reintento conserva el precio aceptado, incluso sin catálogo actual.
                        result = {"replayed": True, "order": json.loads(saved["snapshot"])}
                        connection.commit()
                        return result

                    catalog = self.catalog()
                    if body["catalogVersion"] != catalog["version"]:
                        raise DomainError("catalog_changed", "El catálogo cambió. Actualiza los precios y revisa el pedido antes de continuar.", 409)
                    products = {product["id"]: product for product in catalog["products"]}
                    lines = []
                    for item in body["items"]:
                        product = products.get(item["id"])
                        if product is None:
                            raise DomainError("unknown_product", "Uno de los productos ya no está en el catálogo. Revisa el carrito.", 400)
                        lines.append({"id": product["id"], "name": product["name"], "qty": item["qty"],
                                      "unitPrice": product["price"], "lineTotal": product["price"] * item["qty"]})
                    subtotal = sum(line["lineTotal"] for line in lines)
                    order = {"id": str(uuid.uuid4()),
                             "createdAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                             "mode": "demo", "paymentStatus": "not_charged", "currency": "CLP",
                             "items": lines, "subtotal": subtotal, "shipping": 0, "total": subtotal,
                             "customer": {"name": body["customer"]["name"].strip()}, "delivery": "demo_pickup"}
                    connection.execute(
                        "INSERT INTO patio_demo_orders(request_id, fingerprint, order_id, snapshot) VALUES (?, ?, ?, ?)",
                        (request_id, fingerprint, order["id"], _json(order)),
                    )
                    connection.commit()
                    return {"replayed": False, "order": order}
                except Exception:
                    connection.rollback()
                    raise
        except sqlite3.Error as error:
            raise DomainError("order_unavailable", "No pudimos guardar el pedido. Reintenta con la misma solicitud.", 503) from error
