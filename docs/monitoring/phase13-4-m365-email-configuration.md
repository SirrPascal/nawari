# Phase 13.4 — Microsoft 365 Email Integration & Modern Auth Runbook

## 1. Overview & Current Provisioning State

To provide reliable email notification delivery for Avaya communication alerts, Nawari provides two production-grade Zabbix 7.4 Media Type configurations:

1. **Native Zabbix Office365 SMTP Media Type** (`provisioning/zabbix/media_types/media_type_office365.yaml`):
   - Uses direct SMTP submission via `smtp.office365.com:587` with STARTTLS and strict peer/host SSL certificate verification.
   - **Current Safety State:** Exported with `status: DISABLED`, `username: ""`, and `password: ""`.
2. **Modern Auth (OAuth 2.0) AlertScript Media Type** (`provisioning/zabbix/media_types/media_type_office365_oauth.yaml` & `scripts/zabbix_m365_oauth_sender.py`):
   - Uses Microsoft Entra ID (Azure AD) OAuth 2.0 client credentials flow to send emails via Microsoft Graph API (`/v1.0/users/{sender}/sendMail`) or authenticated SMTP.
   - **Current Safety State:** Script exits cleanly with return code `0` when unconfigured, preventing alert spool retries or Zabbix daemon warnings.

---

## 2. Configuration Parameters

### Native SMTP Media Type Specification

| Parameter | Value | Description |
| :--- | :--- | :--- |
| **Media Type Name** | `Office365 (Nawari Telephony)` | Display name in Zabbix Administration -> Media types |
| **Type** | `EMAIL` | Native Zabbix email delivery driver |
| **SMTP Server** | `smtp.office365.com` | Official Microsoft 365 Exchange Online endpoint |
| **SMTP Port** | `587` | Client submission port |
| **Connection Security**| `STARTTLS` | Mandatory opportunistic TLS |
| **SSL Verify Peer** | `YES` | Enforce valid CA chain validation |
| **SSL Verify Host** | `YES` | Enforce CN/SAN hostname validation against `smtp.office365.com` |
| **Authentication** | `NORMAL_PASSWORD` | Basic SMTP Auth (or App Password) |
| **Username** | *(Pending customer supply)* | e.g. `nawari-alerts@kenya-airways.com` |
| **Password** | *(Pending customer supply)* | Account password or Application Secret |
| **Status** | `DISABLED` | Safe default; must be enabled by operator post-credentialing |

### OAuth 2.0 AlertScript Specification

| Parameter | Value | Description |
| :--- | :--- | :--- |
| **Script Name** | `zabbix_m365_oauth_sender.py` | Standalone Python 3 executable |
| **Execution Path** | `/usr/lib/zabbix/alertscripts/` | Configured in `zabbix_server.conf` -> `AlertScriptsPath` |
| **Script Parameters** | `{ALERT.SENDTO}`, `{ALERT.SUBJECT}`, `{ALERT.MESSAGE}` | Positional arguments passed by Zabbix server daemon |
| **Tenant ID Variable** | `M365_TENANT_ID` | Entra ID Directory (tenant) GUID |
| **Client ID Variable** | `M365_CLIENT_ID` | Application (client) GUID |
| **Client Secret Variable**| `M365_CLIENT_SECRET` | App registration client secret value |
| **Sender Address** | `M365_SENDER_ADDRESS` | Mailbox licensed to send alert messages |

---

## 3. Production Activation Runbook

When the customer administrator provides Microsoft 365 credentials, follow these instructions:

### Procedure A: Activating Native SMTP
1. In Zabbix Frontend, navigate to **Administration -> Media types**.
2. Select **Import** and upload `provisioning/zabbix/media_types/media_type_office365.yaml`.
3. Open the imported `Office365 (Nawari Telephony)` media type:
   - Set **Username** to the dedicated notification mailbox (e.g., `telephony-noc@company.com`).
   - Set **Password** to the assigned mailbox password or Entra App Password.
   - Set **Status** to **Enabled**.
4. Click **Test** and enter a valid test recipient email to verify STARTTLS handshake and authentication.

### Procedure B: Activating Modern Auth OAuth 2.0 (Recommended by Microsoft)
Microsoft is deprecating legacy basic SMTP authentication across Exchange Online. For highest reliability and security:
1. Register an application in **Microsoft Entra ID admin center**:
   - Permission: `Mail.Send` (Application permission).
   - Grant admin consent for your organization.
   - Create a client secret and record its value.
2. Deploy the sender script to your Zabbix server:
   ```bash
   cp /Users/madeira/Desktop/Projects/nawari/scripts/zabbix_m365_oauth_sender.py /usr/lib/zabbix/alertscripts/
   chmod +x /usr/lib/zabbix/alertscripts/zabbix_m365_oauth_sender.py
   ```
3. Configure environment variables in `/etc/zabbix/zabbix_server.conf.d/m365.conf` or `/etc/environment`:
   ```bash
   export M365_TENANT_ID="00000000-0000-0000-0000-000000000000"
   export M365_CLIENT_ID="11111111-1111-1111-1111-111111111111"
   export M365_CLIENT_SECRET="your-azure-client-secret"
   export M365_SENDER_ADDRESS="telephony-noc@company.com"
   ```
4. In Zabbix, import `provisioning/zabbix/media_types/media_type_office365_oauth.yaml` and enable the media type.

---

## 4. User Media Assignment

To assign the media type to NOC operators:
1. Navigate to **Administration -> Users**.
2. Edit the target user or user group (e.g., `NOC Telephony Duty`).
3. Under the **Media** tab, click **Add**:
   - **Type**: `Office365 (Nawari Telephony)` or `Office365 OAuth Script`.
   - **Send to**: `telephony-duty@company.com` or individual engineer address.
   - **When active**: `1-7,00:00-24:00` (24x7 coverage).
   - **Use if severity**: Check `Warning`, `Average`, `High`, `Disaster`.
4. Save the user profile.

