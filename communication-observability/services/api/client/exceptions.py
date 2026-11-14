"""Typed exceptions and error contracts for Zabbix JSON-RPC client."""

from typing import Any, Optional


class ZabbixError(Exception):
    """Base exception for all Zabbix-related errors."""
    pass


class ZabbixConnectionError(ZabbixError):
    """Raised when connection to Zabbix API cannot be established."""
    pass


class ZabbixTimeoutError(ZabbixConnectionError):
    """Raised when request to Zabbix API times out."""
    pass


class ZabbixAuthError(ZabbixError):
    """Raised when authentication with Zabbix API fails."""
    pass


class ZabbixAPIError(ZabbixError):
    """Raised when Zabbix API returns a JSON-RPC error response."""

    def __init__(self, code: int, message: str, data: Optional[Any] = None):
        self.code = code
        self.message = message
        self.data = data
        detail = f" [Data: {data}]" if data else ""
        super().__init__(f"Zabbix API Error {code}: {message}{detail}")


class ZabbixNotFoundError(ZabbixAPIError):
    """Raised when a requested Zabbix entity is not found."""
    pass


class ZabbixValidationError(ZabbixAPIError):
    """Raised when Zabbix rejects parameters due to validation failure."""
    pass

