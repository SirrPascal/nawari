# Nawari Credential Security & Rotation Guide

## 1. Principles of Credential Management

In Nawari:
1. **Zero Committed Secrets:** No production passwords, API tokens, SNMP communities, or SNMPv3 passphrases may ever appear in Git repositories, documentation, or commit messages.
2. **Dynamic Injection:** All credentials are dynamically resolved from environment variables or runtime secrets using the `${VARIABLE_NAME}` syntax.
3. **Least Privilege:** Services and monitoring agents use dedicated accounts with strictly scoped role-based access control (RBAC).

---

## 2. Credential Rotation Procedures

### A. Rotating the Zabbix Web Administrator Password
1. Generate a strong passphrase complying with Zabbix 7.4 complexity rules (minimum 12 characters, uppercase, lowercase, numbers, special characters; **must not contain** "Admin", "Zabbix", or "Administrator"):
   ```bash
   NEW_PASS=$(openssl rand -base64 16)
   ```
2. Update the password in Zabbix via API:
   ```bash
   python3 -c "
   from services.api.config import get_settings
   from services.api.client.zabbix_client import ZabbixClient
   client = ZabbixClient(get_settings().zabbix)
   client.connect()
   client.call('user.update', {'userid': '1', 'passwd': '${NEW_PASS}', 'current_passwd': '${OLD_PASS}'})
   print('Password updated successfully.')
   "
   ```
3. Update `ZBX_API_PASSWORD` in `.env` (or production secret store).
4. Restart Zabbix Web and Grafana:
   ```bash
   docker compose restart zabbix-web grafana
   ```

### B. Rotating the Zabbix API Token
1. Generate a new API token via Zabbix API:
   ```bash
   python3 -c "
   from services.api.config import get_settings
   from services.api.client.zabbix_client import ZabbixClient
   client = ZabbixClient(get_settings().zabbix)
   client.connect()
   token_info = client.call('token.create', {'name': 'grafana-token-v2', 'userid': '1'})
   token_gen = client.call('token.generate', [token_info['tokenids'][0]])
   print('New Token:', token_gen[0]['token'])
   "
   ```
2. Update `ZBX_API_TOKEN` in `.env`.
3. Restart Grafana to update the provisioned datasource:
   ```bash
   docker compose restart grafana
   ```
4. Revoke the old token via `token.delete`.

### C. Rotating SNMPv3 Device Passphrases
1. Update `AVAYA_SBCE_SNMP_AUTH_PASS` and `AVAYA_SBCE_SNMP_PRIV_PASS` in the host `.env` file.
2. Run Nawari reconciliation to update the host interface and macros in Zabbix:
   ```bash
   python3 -m services.api.cli plan
   python3 -m services.api.cli apply
   ```
3. Verify connectivity through Zabbix SNMP poller.
