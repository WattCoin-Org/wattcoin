class WattCoinError(Exception):
    """Base class for exceptions in this module."""
    pass

class APIError(WattCoinError):
    """Raised when the API returns an error."""
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code

class InsufficientWATT(APIError):
    """Raised when the wallet has insufficient WATT for an operation."""
    pass

class TxNotFound(APIError):
    """Raised when a transaction signature is not found on-chain."""
    pass

class TaskNotFound(APIError):
    """Raised when a specific task ID is not found."""
    pass
