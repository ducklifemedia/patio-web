"""Azure Functions adapter for the isolated, private PATIO payment trial."""
import os
from pathlib import Path
import sys

import azure.functions as func

API_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(API_ROOT))
from payments import PaymentConfig,PaymentStore
from payments_http import PaymentApplication,PaymentHTTPConfig,ReadOnlyCatalog


def main(req:func.HttpRequest)->func.HttpResponse:
    # Do not cache access keys/config across changes; do not create resources here.
    config=PaymentConfig.from_env()
    catalog=ReadOnlyCatalog(API_ROOT/'catalog.json')
    try:
        bridge_key=os.environ.get('PATIO_ORDERS_BRIDGE_KEY','')
        http_config=PaymentHTTPConfig(os.environ['PATIO_MP_PUBLIC_ORIGIN'],os.environ.get('PATIO_MP_OPERATOR_KEY',''),bridge_key)
        store=None
        repository=None
        if bridge_key or (config.mode=='test' and not config.problems()):
            from payments_table import AzureTablePaymentRepository
            repository=AzureTablePaymentRepository.from_env()
        if config.mode=='test' and not config.problems():
            store=PaymentStore(None,catalog,config,repository=repository)
        app=PaymentApplication(store,catalog,http_config,bridge=repository)
        status,headers,body=app.dispatch(req.method,req.url,req.headers,req.get_body())
    except Exception:
        status,headers,body=PaymentApplication.response(503,{'error':{'code':'payments_unavailable','message':'La integración de prueba no está disponible.'}})
    return func.HttpResponse(body,status_code=status,headers=headers)
