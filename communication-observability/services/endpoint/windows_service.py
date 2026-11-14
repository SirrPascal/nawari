"""Windows Service host for the frozen Nawari Endpoint Agent executable.

PyInstaller bundles pywin32 into the Windows executable. Imports stay inside
the dispatcher so non-Windows development and tests do not require pywin32.
"""

from __future__ import annotations

import asyncio
import os
import threading
from typing import Any


def run_service_dispatcher() -> int:
    """Connect the frozen executable to the Windows Service Control Manager."""
    if os.name != "nt":
        return 2

    import servicemanager  # type: ignore[import-not-found]
    import win32event  # type: ignore[import-not-found]
    import win32service  # type: ignore[import-not-found]
    import win32serviceutil  # type: ignore[import-not-found]

    from services.endpoint.config import AgentConfig
    from services.endpoint.runner import EndpointAgentRunner
    from services.endpoint.windows_credentials import load_token

    class NawariEndpointService(win32serviceutil.ServiceFramework):
        _svc_name_ = "NawariEndpointAgent"
        _svc_display_name_ = "Nawari Endpoint Agent"
        _svc_description_ = "Network digital user-experience diagnostics and secure telemetry delivery."

        def __init__(self, args: Any) -> None:
            super().__init__(args)
            self._stop_event = win32event.CreateEvent(None, 0, 0, None)
            self._loop: asyncio.AbstractEventLoop | None = None
            self._runner: EndpointAgentRunner | None = None
            self._thread: threading.Thread | None = None

        def SvcStop(self) -> None:  # noqa: N802 - pywin32 API name
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            if self._loop and self._runner:
                asyncio.run_coroutine_threadsafe(self._runner.stop(), self._loop)
            win32event.SetEvent(self._stop_event)

        def SvcDoRun(self) -> None:  # noqa: N802 - pywin32 API name
            servicemanager.LogInfoMsg("Nawari Endpoint Agent service starting")
            self._thread = threading.Thread(target=self._run_agent, daemon=True)
            self._thread.start()
            win32event.WaitForSingleObject(self._stop_event, win32event.INFINITE)
            if self._thread:
                self._thread.join(timeout=30)
            servicemanager.LogInfoMsg("Nawari Endpoint Agent service stopped")

        def _run_agent(self) -> None:
            os.environ["NAWARI_AGENT_TOKEN"] = load_token()
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._runner = EndpointAgentRunner(
                config=AgentConfig.load_from_env(),
                enable_uploader=True,
            )
            try:
                self._loop.run_until_complete(self._runner.start())
            finally:
                self._loop.close()

    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(NawariEndpointService)
    servicemanager.StartServiceCtrlDispatcher()
    return 0
