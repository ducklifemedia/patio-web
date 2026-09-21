"""Only the payment/catalog error contract; no ERP records or routes."""
MAX_AMOUNT=1_000_000_000_000

class DomainError(Exception):
    def __init__(self,code,message,status=422):
        super().__init__(message)
        self.code,self.message,self.status=code,message,status
