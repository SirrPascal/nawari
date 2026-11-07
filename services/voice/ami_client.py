"""Pure Python Asterisk Manager Interface (AMI) Client.

Supports synchronous and asynchronous AMI command execution, action-response matching,
and event stream filtering without external C dependencies.
"""

import asyncio
import socket
import time
import uuid
from typing import Any, Callable, Optional


class AmiError(Exception):
    """General AMI communication or command error."""


class AmiAuthenticationError(AmiError):
    """Failed authentication credentials against AMI."""


class AmiTimeoutError(AmiError):
    """Timeout waiting for AMI response or event."""


class AmiClient:
    """Synchronous line-based AMI client with response correlation and event buffering."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5038,
        username: str = "nawari",
        secret: str = "nawari_ami_dev_secret",
        timeout: float = 10.0,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.secret = secret
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self.buffer = ""
        self.banner: Optional[str] = None
        self.authenticated = False

    def connect(self) -> str:
        """Establish TCP connection and read initial Asterisk Call Manager banner."""
        if self.sock:
            return self.banner or ""

        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)

        # Read banner line terminated by \r\n
        line = self._readline()
        if not line or "Asterisk Call Manager" not in line:
            self.disconnect()
            raise AmiError(f"Unexpected AMI banner: {line}")

        self.banner = line.strip()
        return self.banner

    def disconnect(self) -> None:
        """Gracefully close AMI socket."""
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        self.authenticated = False
        self.buffer = ""

    def __enter__(self) -> "AmiClient":
        self.connect()
        self.login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.authenticated:
            try:
                self.logoff()
            except Exception:
                pass
        self.disconnect()

    def _readline(self) -> str:
        """Read a single line terminated by newline."""
        while "\n" not in self.buffer:
            if not self.sock:
                raise AmiError("Socket closed")
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise AmiError("Connection closed by Asterisk AMI")
                self.buffer += chunk.decode("utf-8", errors="replace")
            except socket.timeout:
                raise AmiTimeoutError("Timed out reading from AMI")

        line, self.buffer = self.buffer.split("\n", 1)
        return line.strip("\r")

    def _read_message(self, timeout: Optional[float] = None) -> dict[str, str]:
        """Read a complete key-value message delimited by double CRLF."""
        if timeout is not None and self.sock:
            self.sock.settimeout(timeout)

        msg: dict[str, str] = {}
        empty_lines = 0

        while True:
            line = self._readline()
            if not line:
                if msg:
                    # End of message
                    break
                empty_lines += 1
                if empty_lines > 10:
                    break
                continue

            if ":" in line:
                key, val = line.split(":", 1)
                msg[key.strip()] = val.strip()

        return msg

    def send_action(
        self,
        action: str,
        params: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> dict[str, str]:
        """Send an action packet and await its correlated Response message."""
        if not self.sock:
            raise AmiError("Not connected to AMI")

        action_id = (params or {}).get("ActionID") or f"nawari-{uuid.uuid4().hex[:8]}"
        payload = [f"Action: {action}", f"ActionID: {action_id}"]

        if params:
            for k, v in params.items():
                if k != "ActionID" and v is not None:
                    payload.append(f"{k}: {v}")

        wire = "\r\n".join(payload) + "\r\n\r\n"
        self.sock.sendall(wire.encode("utf-8"))

        deadline = time.time() + (timeout or self.timeout)
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            msg = self._read_message(timeout=remaining)
            if not msg:
                continue

            if msg.get("ActionID") == action_id and "Response" in msg:
                return msg

        raise AmiTimeoutError(f"Timeout waiting for response to action {action} (ActionID: {action_id})")

    def login(self) -> dict[str, str]:
        """Authenticate with Asterisk using configured credentials."""
        if not self.sock:
            self.connect()

        resp = self.send_action(
            "Login",
            {
                "Username": self.username,
                "Secret": self.secret,
            },
        )
        if resp.get("Response") != "Success":
            raise AmiAuthenticationError(f"AMI login failed: {resp.get('Message', 'Unknown error')}")

        self.authenticated = True
        return resp

    def ping(self) -> dict[str, str]:
        """Send Ping action to verify active session."""
        return self.send_action("Ping")

    def logoff(self) -> dict[str, str]:
        """Send Logoff action."""
        if not self.sock or not self.authenticated:
            return {}
        try:
            return self.send_action("Logoff")
        finally:
            self.authenticated = False

    def originate(
        self,
        channel: str,
        exten: Optional[str] = None,
        context: Optional[str] = None,
        priority: int = 1,
        application: Optional[str] = None,
        app_data: Optional[str] = None,
        timeout_ms: int = 15000,
        caller_id: Optional[str] = None,
        action_id: Optional[str] = None,
        variables: Optional[dict[str, str]] = None,
    ) -> dict[str, str]:
        """Queue or trigger an outbound call origination."""
        params: dict[str, Any] = {
            "Channel": channel,
            "Timeout": str(timeout_ms),
            "Async": "true",
        }
        if exten:
            params["Exten"] = exten
        if context:
            params["Context"] = context
        if priority:
            params["Priority"] = str(priority)
        if application:
            params["Application"] = application
        if app_data:
            params["Data"] = app_data
        if caller_id:
            params["CallerID"] = caller_id
        if action_id:
            params["ActionID"] = action_id
        if variables:
            # Variable: key1=val1\r\nVariable: key2=val2
            for idx, (vk, vv) in enumerate(variables.items()):
                if idx == 0:
                    params["Variable"] = f"{vk}={vv}"
                else:
                    params[f"Variable{idx}"] = f"{vk}={vv}"

        return self.send_action("Originate", params)

    def hangup(self, channel: str) -> dict[str, str]:
        """Hang up an active channel."""
        return self.send_action("Hangup", {"Channel": channel})

    def collect_events_until(
        self,
        stop_predicate: Callable[[dict[str, str]], bool],
        max_duration_seconds: float = 15.0,
    ) -> list[dict[str, str]]:
        """Collect incoming AMI events until stop_predicate returns True or deadline expires."""
        events: list[dict[str, str]] = []
        deadline = time.time() + max_duration_seconds

        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            try:
                msg = self._read_message(timeout=remaining)
            except AmiTimeoutError:
                break

            if not msg:
                continue

            if "Event" in msg:
                events.append(msg)
                if stop_predicate(msg):
                    break

        return events

