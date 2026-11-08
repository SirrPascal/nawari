"""Idempotent reconciliation engine for applying desired state to Zabbix."""

import logging
from pathlib import Path
from typing import Any, Optional

from services.api.client.models import HostGroup, InterfaceType
from services.api.client.zabbix_client import ZabbixClient
from services.api.config import find_project_root
from services.api.provisioning.diff import (
    ActionType,
    ChangeReport,
    DiffEngine,
    EntityType,
)
from services.api.provisioning.schema import DesiredHost, DesiredState

logger = logging.getLogger("nawari.reconciler")


class Reconciler:
    """Manages diff calculation and idempotent state synchronization."""

    def __init__(self, client: ZabbixClient):
        self.client = client

    def sync_templates(self, templates_dir: Optional[Path] = None) -> list[str]:
        """Import all template YAML files located in templates_dir."""
        if templates_dir is None:
            templates_dir = find_project_root() / "provisioning" / "zabbix" / "templates"

        if not templates_dir.exists():
            return []

        imported = []
        yaml_files = sorted(templates_dir.glob("*.yaml")) + sorted(templates_dir.glob("*.yml"))
        for path in yaml_files:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            try:
                self.client.call("configuration.import", {
                    "format": "yaml",
                    "source": content,
                    "rules": {
                        "templates": {"createMissing": True, "updateExisting": True},
                        "template_groups": {"createMissing": True, "updateExisting": True},
                        "templateLinkage": {"createMissing": True},
                        "items": {"createMissing": True, "updateExisting": True},
                        "discoveryRules": {"createMissing": True, "updateExisting": True},
                        "triggers": {"createMissing": True, "updateExisting": True}
                    }
                })
                imported.append(path.name)
                logger.info(f"Successfully synced template: {path.name}")
            except Exception as e:
                logger.error(f"Failed to sync template {path.name}: {e}")
                raise
        return imported

    def plan(self, desired_state: DesiredState) -> ChangeReport:
        """Fetch current Zabbix state and calculate diff without applying changes."""
        # 0. Sync local template definitions
        self.sync_templates()

        # 1. Fetch live host groups
        desired_group_names = [g.name for g in desired_state.host_groups]
        live_groups = self.client.get_host_groups(names=desired_group_names)
        group_diffs = DiffEngine.diff_host_groups(desired_state.host_groups, live_groups)
        group_map = {g.name: str(g.groupid) for g in live_groups if g.groupid}

        # 2. Fetch live templates needed by desired hosts
        all_tpl_names = {t for h in desired_state.hosts for t in h.templates}
        live_templates = self.client.get_templates(names=list(all_tpl_names)) if all_tpl_names else []
        tpl_map = {}
        for t in live_templates:
            if t.templateid:
                tpl_map[t.host] = str(t.templateid)
                tpl_map[t.name] = str(t.templateid)

        # 3. Fetch live hosts
        hostnames = [h.host for h in desired_state.hosts]
        live_hosts = self.client.get_hosts(hostnames=hostnames) if hostnames else []

        host_diffs = DiffEngine.diff_hosts(
            desired_hosts=desired_state.hosts,
            live_hosts=live_hosts,
            template_name_to_id=tpl_map,
            group_name_to_id=group_map,
        )

        return ChangeReport(items=group_diffs + host_diffs)

    def apply(self, desired_state: DesiredState) -> ChangeReport:
        """Reconcile Zabbix infrastructure to match desired state idempotently."""
        report = self.plan(desired_state)
        if not report.has_changes:
            logger.info("Infrastructure is already in desired state. No changes made.")
            return report

        logger.info(
            f"Applying changes: {len(report.creates)} to create, {len(report.updates)} to update."
        )

        # 1. Reconcile Host Groups
        group_map = {g.name: str(g.groupid) for g in self.client.get_host_groups() if g.groupid}
        for item in report.creates:
            if item.entity_type == EntityType.HOST_GROUP:
                logger.info(f"Creating Host Group: {item.entity_name}")
                gid = self.client.create_host_group(item.entity_name)
                group_map[item.entity_name] = gid

        # 2. Cache required templates
        all_tpl_names = {t for h in desired_state.hosts for t in h.templates}
        live_templates = self.client.get_templates(names=list(all_tpl_names)) if all_tpl_names else []
        tpl_map = {}
        for t in live_templates:
            if t.templateid:
                tpl_map[t.host] = str(t.templateid)
                tpl_map[t.name] = str(t.templateid)

        # 3. Reconcile Hosts
        desired_hosts_map = {h.host: h for h in desired_state.hosts}
        for item in report.creates:
            if item.entity_type == EntityType.HOST:
                dh = desired_hosts_map[item.entity_name]
                logger.info(f"Creating Host: {dh.host} ('{dh.name}')")
                payload = self._build_host_create_payload(dh, group_map, tpl_map)
                self.client.create_host(payload)

        for item in report.updates:
            if item.entity_type == EntityType.HOST and item.target_id:
                dh = desired_hosts_map[item.entity_name]
                logger.info(f"Updating Host: {dh.host} (ID: {item.target_id})")
                self._apply_host_updates(item.target_id, dh, item.details, group_map, tpl_map)

        # 4. Reconcile Administrators, User Groups, Media, and Alert Actions
        try:
            self.reconcile_notifications()
        except Exception as e:
            logger.warning(f"Notification reconciliation encountered an error: {e}")

        logger.info("Reconciliation run completed.")
        return report

    def reconcile_notifications(self) -> dict[str, Any]:
        """Reconcile designated administrators, user group, media, and alert actions."""
        from services.api.provisioning.notification_reconciler import NotificationReconciler
        nr = NotificationReconciler(self.client)
        return nr.reconcile_all()

    def _build_host_create_payload(
        self,
        dh: DesiredHost,
        group_map: dict[str, str],
        tpl_map: dict[str, str],
    ) -> dict[str, Any]:
        # Resolve groupids
        groups = []
        for g in dh.groups:
            gid = group_map.get(g)
            if not gid:
                # Group should exist because we created missing ones
                gid = self.client.ensure_host_group(g)
                group_map[g] = gid
            groups.append({"groupid": gid})

        # Resolve templateids
        templates = []
        for t in dh.templates:
            tid = tpl_map.get(t)
            if tid:
                templates.append({"templateid": tid})
            else:
                logger.warning(f"Template '{t}' not found in Zabbix; skipping link for {dh.host}")

        # Build interfaces
        interfaces = []
        for iface in dh.interfaces:
            if_dict = {
                "type": int(iface.type),
                "main": int(iface.main),
                "useip": int(iface.useip),
                "ip": iface.ip,
                "dns": iface.dns,
                "port": str(iface.port),
            }
            if iface.type == InterfaceType.SNMP and iface.details:
                if_dict["details"] = iface.details.to_dict()
            interfaces.append(if_dict)

        # Build macros
        macros = []
        for m in dh.macros:
            macros.append({
                "macro": m.macro,
                "value": m.value,
                "type": int(m.type),
                "description": m.description,
            })

        # Build tags
        tags = [{"tag": t.tag, "value": t.value} for t in dh.tags]

        payload: dict[str, Any] = {
            "host": dh.host,
            "name": dh.name,
            "status": int(dh.status),
            "description": dh.description,
            "groups": groups,
            "interfaces": interfaces,
            "templates": templates,
            "macros": macros,
            "tags": tags,
        }
        return payload

    def _apply_host_updates(
        self,
        hostid: str,
        dh: DesiredHost,
        details: dict[str, Any],
        group_map: dict[str, str],
        tpl_map: dict[str, str],
    ) -> None:
        update_payload: dict[str, Any] = {}

        if "name" in details:
            update_payload["name"] = dh.name
        if "status" in details:
            update_payload["status"] = int(dh.status)
        if "description" in details:
            update_payload["description"] = dh.description

        if "groups" in details:
            groups = []
            for g in dh.groups:
                gid = group_map.get(g) or self.client.ensure_host_group(g)
                groups.append({"groupid": gid})
            update_payload["groups"] = groups

        if "templates" in details:
            # Query existing templates on the host to clear removed ones
            live_host = self.client.get_hosts([dh.host], select_templates=True)
            current_tids = {
                t["templateid"]
                for t in (live_host[0].get("parentTemplates", []) if live_host else [])
            }
            desired_tids = set()
            templates = []
            for t in dh.templates:
                tid = tpl_map.get(t)
                if tid:
                    templates.append({"templateid": tid})
                    desired_tids.add(tid)
            update_payload["templates"] = templates

            to_clear = current_tids - desired_tids
            if to_clear:
                update_payload["templates_clear"] = [{"templateid": tid} for tid in to_clear]

        if update_payload:
            self.client.update_host(hostid, update_payload)

        # Handle interface updates
        if "interfaces" in details:
            # Query existing interfaces to get interfaceid
            live_host = self.client.get_hosts([dh.host], select_interfaces=True)
            if live_host and live_host[0].get("interfaces"):
                primary_live = next(
                    (i for i in live_host[0]["interfaces"] if int(i.get("main", 0)) == 1),
                    live_host[0]["interfaces"][0]
                )
                desired_main = next((i for i in dh.interfaces if i.main == 1), dh.interfaces[0])
                if_payload = {
                    "ip": desired_main.ip,
                    "port": str(desired_main.port),
                    "type": int(desired_main.type),
                }
                if desired_main.type == InterfaceType.SNMP and desired_main.details:
                    if_payload["details"] = desired_main.details.to_dict()
                self.client.update_interface(primary_live["interfaceid"], if_payload)

