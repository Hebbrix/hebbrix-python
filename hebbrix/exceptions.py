"""
Hebbrix SDK Exceptions
"""


class HebbrixError(Exception):
    """Base exception for Hebbrix SDK."""

    def __init__(self, message: str, status_code: int = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class AuthenticationError(HebbrixError):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status_code=401)


class ValidationError(HebbrixError):
    """Raised when request validation fails."""

    def __init__(self, message: str, errors: list = None):
        self.errors = errors or []
        super().__init__(message, status_code=422)


class NotFoundError(HebbrixError):
    """Raised when a resource is not found."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)


class RateLimitError(HebbrixError):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, status_code=429)


class ServerError(HebbrixError):
    """Raised when server returns 5xx error."""

    def __init__(self, message: str = "Internal server error"):
        super().__init__(message, status_code=500)
