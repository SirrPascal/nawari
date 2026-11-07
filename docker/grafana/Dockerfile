FROM grafana/grafana:11.6.0

USER root

# Pre-install the exact pinned Alexander Zobnin Zabbix App plugin (v6.10.2)
RUN grafana cli plugins install alexanderzobnin-zabbix-app 6.10.2

USER grafana

