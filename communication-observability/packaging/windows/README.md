# Standalone Windows endpoint packaging — experimental fallback

This is no longer the primary employee-laptop deployment architecture. The
approved primary path is the signed Nawari external collector managed by the
single Netdata service, packaged under `network observability/packaging/windows`.
Keep this standalone MSI source frozen as a fallback until Windows acceptance
proves whether every required diagnostic can run reliably under Netdata.

The managed Windows deployment contains two logically separate services:

- `NawariEndpointAgent`, installed by `NawariEndpointAgent-x64.msi`.
- Netdata Child, installed from the organization-approved official Netdata MSI.

Administrators deploy one Intune Win32 application containing both signed MSIs
and the coordination scripts. Windows Installer packages are installed
sequentially; one MSI must not launch a nested second MSI transaction.

## Build boundary

Build the Windows executable and MSI on an approved Windows x64 runner:

```powershell
.\Build-Msi.ps1 -Version 1.0.0 -Configuration Release
```

Release mode fails unless an approved Authenticode certificate thumbprint and
Windows SDK `signtool.exe` are available. PyInstaller cannot cross-compile the
Windows binary on macOS.

## Intune package contents

Include:

- `NawariEndpointAgent-x64.msi`
- The pinned, organization-approved Netdata x64 MSI as `Netdata-x64.msi`
- `Install-Intune.ps1`, `Detect-Intune.ps1`, and `Uninstall-Intune.ps1`
- A short-lived enrollment-token file delivered by an approved secret process

The install command must provide the expected SHA-256 values. Both MSI files
must also have valid Authenticode signatures. The token is passed to the agent
over standard input, protected with machine-scope DPAPI, and the staging file
is removed.

Example Intune command shape (values omitted intentionally):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-Intune.ps1 `
  -GatewayUrl "https://nawari.example.internal" `
  -EnrollmentTokenFile "C:\ProgramData\Nawari\staging-token.txt" `
  -NawariMsiSha256 "<approved hash>" `
  -NetdataMsiSha256 "<approved hash>"
```

The plain MSI supports standard repair, upgrade, and removal operations:

```text
msiexec /i NawariEndpointAgent-x64.msi /qn /norestart
msiexec /fa NawariEndpointAgent-x64.msi /qn /norestart
msiexec /x NawariEndpointAgent-x64.msi /qn /norestart
```

Agent identity, protected credentials, configuration, and buffered telemetry
under `%ProgramData%\Nawari\Endpoint Agent` survive ordinary MSI upgrades and
removal. Use `Uninstall-Intune.ps1 -PurgeIdentityAndTelemetry` only for an
explicit device-retirement workflow.

## Acceptance gates

This source definition is not a signed production package until a Windows x64
runner has completed all of the following:

1. Frozen-executable smoke and probe tests.
2. WiX ICE validation and clean install/repair/major-upgrade/uninstall tests.
3. Authenticode verification for the EXE and MSI.
4. Windows 10 and Windows 11 service, sleep/wake, Wi-Fi, VPN, and spool replay tests.
5. Intune System-context installation, detection, rollback, and staged-ring deployment.
6. Approved Netdata configuration and verified child-to-Parent TLS streaming.
