"""Robust, production-grade Zabbix 7.4 JSON-RPC 2.0 client."""

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from services.api.client.exceptions import (
    ZabbixAPIError,
    ZabbixAuthError,
    ZabbixConnectionError,
    ZabbixError,
    ZabbixNotFoundError,
    ZabbixTimeoutError,
    ZabbixValidationError,
)
from services.api.client.models import HostGroup, Template
from services.api.config import ZabbixSettings

logger = logging.getLogger("nawari.zabbix")


class ZabbixClient:
    """Zabbix 7.4 JSON-RPC API client with retry backoff and typed models."""

    def __init__(self, settings: ZabbixSettings):
        self.settings = settings
        self.url = settings.url
        self.token = settings.token
        self.user = settings.user
        self.password = settings.password
        self.timeout = settings.timeout_seconds
        self.max_retries = settings.max_retries
        self.backoff_factor = settings.backoff_factor

        self._session_auth: Optional[str] = None
        self._request_id = 0

    @property
    def is_token_auth(self) -> bool:
        return bool(self.token)

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def connect(self) -> str:
        """Establish authentication if using user/password, or verify token."""
        if self.token:
            # Token auth: verify token by fetching API version (apiinfo.version needs no auth)
            # and then calling hostgroup.get
            self.call("hostgroup.get", {"limit": 1})
            logger.info("Connected to Zabbix using API Bearer token.")
            return self.token

        # User/password auth via user.login
        logger.info(f"Authenticating with Zabbix as user '{self.user}'...")
        res = self.call(
            "user.login",
            {"username": self.user, "password": self.password},
            requires_auth=False
        )
        if not res or not isinstance(res, str):
            raise ZabbixAuthError("Failed to obtain authentication token from Zabbix user.login")
        self._session_auth = res
        logger.info("Zabbix user.login successful; session established.")
        return self._session_auth

    def disconnect(self) -> None:
        """Logout active session if applicable."""
        if self._session_auth and not self.token:
            try:
                self.call("user.logout", {})
            except Exception as e:
                logger.debug(f"Ignored error during Zabbix logout: {e}")
            finally:
                self._session_auth = None

    def call(self, method: str, params: Any, requires_auth: bool = True) -> Any:
        """Execute a JSON-RPC 2.0 call with retries and exponential backoff."""
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._next_id(),
        }

        headers = {"Content-Type": "application/json-rpc"}

        if requires_auth:
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            elif self._session_auth:
                headers["Authorization"] = f"Bearer {self._session_auth}"
            else:
                # Attempt lazy login
                self.connect()
                if self._session_auth:
                    headers["Authorization"] = f"Bearer {self._session_auth}"

        data = json.dumps(payload).encode("utf-8")
        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                req = urllib.request.Request(self.url, data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    raw_body = response.read().decode("utf-8")
                    resp_json = json.loads(raw_body)

                if "error" in resp_json:
                    err = resp_json["error"]
                    code = err.get("code", 0)
                    msg = err.get("message", "Unknown error")
                    err_data = err.get("data")

                    if code == -32602:
                        raise ZabbixValidationError(code, msg, err_data)
                    elif code == -32500 and "auth" in msg.lower():
                        raise ZabbixAuthError(f"{msg}: {err_data}")
                    else:
                        raise ZabbixAPIError(code, msg, err_data)

                return resp_json.get("result")

            except (urllib.error.URLError, TimeoutError, ConnectionResetError) as e:
                last_exception = e
                if isinstance(e, urllib.error.HTTPError):
                    if e.code in [401, 403]:
                        raise ZabbixAuthError(f"HTTP {e.code}: Authentication rejected by Zabbix Web")
                
                logger.warning(
                    f"Zabbix call '{method}' failed on attempt {attempt}/{self.max_retries}: {e}"
                )
                if attempt < self.max_retries:
                    sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                    time.sleep(sleep_time)

        raise ZabbixConnectionError(
            f"Failed to communicate with Zabbix API at {self.url} after {self.max_retries} attempts: {last_exception}"
        )

    # --------------------------------------------------------------------------
    # API Information
    # --------------------------------------------------------------------------
    def get_api_version(self) -> str:
        """Return the Zabbix API version string."""
        return self.call("apiinfo.version", {}, requires_auth=False)

    # --------------------------------------------------------------------------
    # Host Groups
    # --------------------------------------------------------------------------
    def get_host_groups(self, names: Optional[list[str]] = None) -> list[HostGroup]:
        """Fetch host groups, optionally filtered by exact names."""
        params: dict[str, Any] = {"output": ["groupid", "name"]}
        if names:
            params["filter"] = {"name": names}
        result = self.call("hostgroup.get", params)
        return [HostGroup(groupid=item["groupid"], name=item["name"]) for item in result]

    def create_host_group(self, name: str) -> str:
        """Create a new host group and return its groupid."""
        result = self.call("hostgroup.create", {"name": name})
        groupids = result.get("groupids", [])
        if not groupids:
            raise ZabbixAPIError(0, f"Host group creation returned empty groupids for '{name}'")
        return str(groupids[0])

    def ensure_host_group(self, name: str) -> str:
        """Return existing groupid or create if not present."""
        existing = self.get_host_groups(names=[name])
        if existing and existing[0].groupid:
            return existing[0].groupid
        return self.create_host_group(name)

    # --------------------------------------------------------------------------
    # Templates
    # --------------------------------------------------------------------------
    def get_templates(self, names: Optional[list[str]] = None) -> list[Template]:
        """Fetch templates by technical name or visible name."""
        params: dict[str, Any] = {"output": ["templateid", "host", "name"]}
        if names:
            # Query by host (technical name) or name (visible name)
            params["filter"] = {"host": names}
        result = self.call("template.get", params)
        templates = [
            Template(templateid=t["templateid"], host=t["host"], name=t["name"])
            for t in result
        ]
        # If any requested names are missing by host, try visible name lookup
        if names:
            found_hosts = {t.host for t in templates}
            missing = [n for n in names if n not in found_hosts]
            if missing:
                extra = self.call("template.get", {
                    "output": ["templateid", "host", "name"],
                    "filter": {"name": missing}
                })
                for t in extra:
                    templates.append(Template(templateid=t["templateid"], host=t["host"], name=t["name"]))
        return templates

    # --------------------------------------------------------------------------
    # Hosts
    # --------------------------------------------------------------------------
    def get_hosts(
        self,
        hostnames: Optional[list[str]] = None,
        select_interfaces: bool = True,
        select_macros: bool = True,
        select_groups: bool = True,
        select_templates: bool = True,
        select_tags: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch hosts with full sub-entities."""
        params: dict[str, Any] = {
            "output": ["hostid", "host", "name", "status", "description"]
        }
        if hostnames:
            params["filter"] = {"host": hostnames}
        if select_interfaces:
            params["selectInterfaces"] = [
                "interfaceid", "main", "type", "useip", "ip", "dns", "port", "details"
            ]
        if select_macros:
            params["selectMacros"] = ["hostmacroid", "macro", "value", "type", "description"]
        if select_groups:
            params["selectHostGroups"] = ["groupid", "name"]
            params["selectGroups"] = ["groupid", "name"]
        if select_templates:
            params["selectParentTemplates"] = ["templateid", "host", "name"]
        if select_tags:
            params["selectTags"] = ["tag", "value"]

        return self.call("host.get", params)

    def create_host(self, payload: dict[str, Any]) -> str:
        """Create host and return hostid."""
        result = self.call("host.create", payload)
        hostids = result.get("hostids", [])
        if not hostids:
            raise ZabbixAPIError(0, f"Host creation failed to return hostid")
        return str(hostids[0])

    def update_host(self, hostid: str, payload: dict[str, Any]) -> str:
        """Update existing host."""
        data = dict(payload)
        data["hostid"] = hostid
        result = self.call("host.update", data)
        return hostid

    def delete_host(self, hostid: str) -> None:
        """Delete host by hostid."""
        self.call("host.delete", [hostid])

    # --------------------------------------------------------------------------
    # Host Interfaces
    # --------------------------------------------------------------------------
    def create_interface(self, hostid: str, payload: dict[str, Any]) -> str:
        """Create a new interface on host."""
        data = dict(payload)
        data["hostid"] = hostid
        result = self.call("hostinterface.create", data)
        return str(result["interfaceids"][0])

    def update_interface(self, interfaceid: str, payload: dict[str, Any]) -> str:
        """Update an existing interface."""
        data = dict(payload)
        data["interfaceid"] = interfaceid
        self.call("hostinterface.update", data)
        return interfaceid

