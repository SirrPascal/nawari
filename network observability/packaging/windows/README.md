# Windows Netdata endpoint extension

This is the primary Windows endpoint deployment path. One Intune Win32
application installs the approved vendor Netdata MSI and adds the signed
`nawari.plugin.exe` collector to Netdata's external-plugin directory. Netdata
remains the only primary monitoring service.

The installer does not modify or rebuild the vendor MSI. It verifies both
artifact hashes and Authenticode signatures, preserves existing files for
rollback, installs an approved metrics-only collector configuration, installs
the authenticated Parent `stream.conf`, restarts Netdata, and requires Nawari
charts to appear before reporting success.

The default collector policy has `structured_evidence_enabled=false`. Endpoint
measurements therefore follow Netdata child-to-Parent streaming. Arbitrary path
histories or selected events require a separately reviewed server-side design;
they are not silently sent through a second endpoint intake.

Windows runtime acceptance remains mandatory. In particular, the native
Windows network-context implementation must still prove resolver, gateway,
Wi-Fi, VPN, and proxy collection under an employee system context.
