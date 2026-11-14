# Phase 13.4 — Microsoft 365 Email Integration & Modern Auth Runbook

## 1. Overview & Current Provisioning State

To provide reliable email notification delivery for Avaya communication alerts, Nawari provisions declarative Zabbix 7.4 Media Types and user recipient configurations.

All four designated voice administrators have their email media configured and enabled in Zabbix:
- **John Gacomo:** `John.Gacomo@kenya-airways.com`
- **Robinson Wainaina:** `Robinson.Wainaina@kenya-airways.com`
- **Pascal Gathungu:** `Pascal.Gathungu@kenya-airways.com`
- **Mercy Vaati:** `Mercy.Vaati@kenya-airways.com`

---

## 2. Configuration Parameters & Classification

| Parameter | Native SMTP Media Type | Modern Auth OAuth 2.0 AlertScript |
| :--- | :--- | :--- |
| **Media Type Name** | `Microsoft 365 Email` | `Office365 Modern Auth OAuth` |
| **Zabbix Driver** | `EMAIL` (Native Zabbix SMTP) | `SCRIPT` (`zabbix_m365_oauth_sender.py`) |
| **Host / Endpoint** | `smtp.office365.com` | `login.microsoftonline.com` / Graph API |
| **Port / Security** | Port `587` with mandatory `STARTTLS` | HTTPS Port `443` (TLS 1.3) |
| **Certificate Peer Verification** | `YES` (Strict CA validation) | `YES` (System CA trust store) |
| **Certificate Host Verification** | `YES` (Strict CN/SAN check) | `YES` (Strict hostname verification) |
| **Authentication Flow** | Basic SMTP Auth / App Password | OAuth 2.0 Client Credentials (`Mail.Send`) |
| **Current Safety State** | `status: DISABLED` (Secrets blank) | Exits cleanly (`code 0`) when unconfigured |
| **Delivery Verification Status** | `CONFIGURED_UNVERIFIED` | `CONFIGURED_UNVERIFIED` |

> [!CAUTION]
> **Safety Principle:**
> Zero unsolicited test emails are dispatched to `@kenya-airways.com` mailboxes during local staging or simulation.
> Microsoft 365 credentials remain unconfigured in Git.
> Delivery status is truthfully reported as **`CONFIGURED_UNVERIFIED`** until customer credentials are supplied and an authorized delivery rehearsal is executed.

---

## 3. Production Activation Runbook

When the customer administrator provides Microsoft 365 credentials, execute the following procedure:

### Option A: Modern Authentication OAuth 2.0 (Recommended by Microsoft)
Microsoft is deprecating legacy Basic Authentication across Exchange Online. Modern Authentication via Microsoft Entra ID provides superior token-based security:

1. **Azure App Registration:**
   - In **Microsoft Entra admin center**, register `Nawari Telephony Alerting`.
   - Grant Application Permission: `Mail.Send`.
   - Grant Admin Consent for the organization.
   - Generate Client Secret and note Application (client) ID and Directory (tenant) ID.

2. **Deploy AlertScript:**
   ```bash
   cp /Users/madeira/Desktop/Projects/nawari/scripts/zabbix_m365_oauth_sender.py /usr/lib/zabbix/alertscripts/
   chmod +x /usr/lib/zabbix/alertscripts/zabbix_m365_oauth_sender.py
   ```

3. **Set Environment Secrets (outside Git):**
   ```bash
   export M365_TENANT_ID="<tenant-guid>"
   export M365_CLIENT_ID="<client-guid>"
   export M365_CLIENT_SECRET="<client-secret>"
   export M365_SENDER_ADDRESS="telephony-noc@kenya-airways.com"
   ```

4. **Import & Enable Media Type in Zabbix:**
   - In Zabbix Frontend: **Administration -> Media types -> Import**
   - Upload `provisioning/zabbix/media_types/media_type_office365_oauth.yaml`
   - Set Status: **Enabled**.

### Option B: Native SMTP Client Submission
If the tenant retains SMTP AUTH enabled on a dedicated service mailbox:
1. Navigate to: **Administration -> Media types -> Import**
2. Upload: `provisioning/zabbix/media_types/media_type_office365.yaml`
3. Edit the media type:
   - **Username:** `telephony-noc@kenya-airways.com`
   - **Password:** `<service-account-password-or-app-password>`
   - **Status:** **Enabled**.
4. Test with an authorized staging mailbox before enabling production alerts.
