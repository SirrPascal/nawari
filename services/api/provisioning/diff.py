"""Deterministic diff engine for comparing desired state against live Zabbix state."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from services.api.client.models import (
    HostGroup,
    InterfaceType,
    MacroType,
    SNMPVersion,
)
from services.api.provisioning.schema import (
    DesiredHost,
    DesiredHostGroup,
    DesiredInterface,
    DesiredMacro,
    DesiredState,
)


class ActionType(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    NOOP = "NOOP"
    DELETE = "DELETE"


class EntityType(str, Enum):
    HOST_GROUP = "HOST_GROUP"
    HOST = "HOST"
    INTERFACE = "INTERFACE"
    MACRO = "MACRO"
    TAG = "TAG"
    TEMPLATE_LINK = "TEMPLATE_LINK"


@dataclass
class DiffItem:
    entity_type: EntityType
    entity_name: str
    action: ActionType
    details: dict[str, Any] = field(default_factory=dict)
    target_id: Optional[str] = None

    def __str__(self) -> str:
        action_symbol = {
            ActionType.CREATE: "+",
            ActionType.UPDATE: "~",
            ActionType.NOOP: " ",
            ActionType.DELETE: "-",
        }.get(self.action, "?")
        return f"[{action_symbol}] {self.entity_type.value}: {self.entity_name} ({self.action.value})"


@dataclass
class ChangeReport:
    items: list[DiffItem] = field(default_factory=list)

    @property
    def creates(self) -> list[DiffItem]:
        return [i for i in self.items if i.action == ActionType.CREATE]

    @property
    def updates(self) -> list[DiffItem]:
        return [i for i in self.items if i.action == ActionType.UPDATE]

    @property
    def noops(self) -> list[DiffItem]:
        return [i for i in self.items if i.action == ActionType.NOOP]

    @property
    def has_changes(self) -> bool:
        return bool(self.creates or self.updates)

    def summary(self) -> dict[str, int]:
        return {
            "total": len(self.items),
            "create": len(self.creates),
            "update": len(self.updates),
            "noop": len(self.noops),
        }

    def render_text(self) -> str:
        lines = [
            "======================================================================",
            "NAWARI PROVISIONING DIFF REPORT",
            "======================================================================",
        ]
        if not self.has_changes:
            lines.append("No changes required. Infrastructure is in desired state.")
        else:
            for item in self.items:
                if item.action == ActionType.NOOP:
                    continue
                lines.append(str(item))
                for k, v in item.details.items():
                    if isinstance(v, dict) and "old" in v and "new" in v:
                        lines.append(f"    {k}: {v['old']} -> {v['new']}")
                    else:
                        lines.append(f"    {k}: {v}")

        lines.append("----------------------------------------------------------------------")
        s = self.summary()
        lines.append(
            f"Plan: {s['create']} to create, {s['update']} to update, {s['noop']} unchanged."
        )
        lines.append("======================================================================")
        return "\n".join(lines)


class DiffEngine:
    """Computes deterministic diffs between DesiredState and live Zabbix data."""

    @staticmethod
    def diff_host_groups(
        desired_groups: list[DesiredHostGroup],
        live_groups: list[HostGroup],
    ) -> list[DiffItem]:
        diffs: list[DiffItem] = []
        live_map = {g.name: g for g in live_groups}

        for dg in desired_groups:
            if dg.name in live_map:
                diffs.append(
                    DiffItem(
                        entity_type=EntityType.HOST_GROUP,
                        entity_name=dg.name,
                        action=ActionType.NOOP,
                        target_id=live_map[dg.name].groupid,
                    )
                )
            else:
                diffs.append(
                    DiffItem(
                        entity_type=EntityType.HOST_GROUP,
                        entity_name=dg.name,
                        action=ActionType.CREATE,
                        details={"description": dg.description},
                    )
                )
        return diffs

    @staticmethod
    def diff_hosts(
        desired_hosts: list[DesiredHost],
        live_hosts: list[dict[str, Any]],
        template_name_to_id: dict[str, str],
        group_name_to_id: dict[str, str],
    ) -> list[DiffItem]:
        diffs: list[DiffItem] = []
        live_map = {h["host"]: h for h in live_hosts}

        for dh in desired_hosts:
            if dh.host not in live_map:
                # Host needs to be created
                diffs.append(
                    DiffItem(
                        entity_type=EntityType.HOST,
                        entity_name=dh.host,
                        action=ActionType.CREATE,
                        details={
                            "name": dh.name,
                            "status": dh.status,
                            "groups": dh.groups,
                            "templates": dh.templates,
                            "interfaces_count": len(dh.interfaces),
                            "macros_count": len(dh.macros),
                        },
                    )
                )
                continue

            # Host exists: check for updates
            live = live_map[dh.host]
            hostid = str(live["hostid"])
            host_updates: dict[str, Any] = {}

            if live.get("name") != dh.name:
                host_updates["name"] = {"old": live.get("name"), "new": dh.name}

            if int(live.get("status", 0)) != int(dh.status):
                host_updates["status"] = {"old": live.get("status"), "new": dh.status}

            if dh.description and live.get("description", "") != dh.description:
                host_updates["description"] = {
                    "old": live.get("description", ""),
                    "new": dh.description,
                }

            # Check groups (Zabbix 7.0+ returns hostgroups, older returns groups)
            live_groups_list = live.get("hostgroups") or live.get("groups", [])
            live_group_ids = {str(g["groupid"]) for g in live_groups_list}
            desired_group_ids = {
                group_name_to_id[g] for g in dh.groups if g in group_name_to_id
            }
            if desired_group_ids and not desired_group_ids.issubset(live_group_ids):
                host_updates["groups"] = {
                    "old": [g["name"] for g in live_groups_list],
                    "new": dh.groups,
                }

            # Check templates
            live_tpl_ids = {
                str(t["templateid"]) for t in live.get("parentTemplates", [])
            }
            desired_tpl_ids = {
                template_name_to_id[t]
                for t in dh.templates
                if t in template_name_to_id
            }
            if desired_tpl_ids and not desired_tpl_ids.issubset(live_tpl_ids):
                host_updates["templates"] = {
                    "old": [t.get("host") or t.get("name") for t in live.get("parentTemplates", [])],
                    "new": dh.templates,
                }

            # Check interface
            DiffEngine._check_interfaces(dh, live.get("interfaces", []), host_updates)

            # Check macros
            DiffEngine._check_macros(dh, live.get("macros", []), host_updates)

            if host_updates:
                diffs.append(
                    DiffItem(
                        entity_type=EntityType.HOST,
                        entity_name=dh.host,
                        action=ActionType.UPDATE,
                        details=host_updates,
                        target_id=hostid,
                    )
                )
            else:
                diffs.append(
                    DiffItem(
                        entity_type=EntityType.HOST,
                        entity_name=dh.host,
                        action=ActionType.NOOP,
                        target_id=hostid,
                    )
                )

        return diffs

    @staticmethod
    def _check_interfaces(
        dh: DesiredHost,
        live_interfaces: list[dict[str, Any]],
        host_updates: dict[str, Any],
    ) -> None:
        if not dh.interfaces:
            return

        # Find primary interface match
        desired_main = next((i for i in dh.interfaces if i.main == 1), dh.interfaces[0])
        matching_live = next((i for i in live_interfaces if int(i.get("main", 0)) == 1), None)

        if not matching_live:
            host_updates["interface"] = {"action": "create_main", "ip": desired_main.ip}
            return

        if_changes: dict[str, Any] = {}
        if matching_live.get("ip") != desired_main.ip:
            if_changes["ip"] = {"old": matching_live.get("ip"), "new": desired_main.ip}
        if str(matching_live.get("port")) != str(desired_main.port):
            if_changes["port"] = {"old": matching_live.get("port"), "new": desired_main.port}
        if int(matching_live.get("type", 1)) != int(desired_main.type):
            if_changes["type"] = {"old": matching_live.get("type"), "new": desired_main.type}

        # Check SNMP details if SNMP interface
        if desired_main.type == InterfaceType.SNMP and desired_main.details:
            live_details = matching_live.get("details", {})
            des_details = desired_main.details
            if int(live_details.get("version", 2)) != int(des_details.version):
                if_changes["snmp_version"] = {
                    "old": live_details.get("version"),
                    "new": des_details.version,
                }
            if des_details.version == SNMPVersion.SNMP_V3:
                if live_details.get("securityname") != des_details.securityname:
                    if_changes["securityname"] = {
                        "old": live_details.get("securityname"),
                        "new": des_details.securityname,
                    }
                if int(live_details.get("securitylevel", 0)) != int(des_details.securitylevel):
                    if_changes["securitylevel"] = {
                        "old": live_details.get("securitylevel"),
                        "new": des_details.securitylevel,
                    }

        if if_changes:
            host_updates["interfaces"] = if_changes

    @staticmethod
    def _check_macros(
        dh: DesiredHost,
        live_macros: list[dict[str, Any]],
        host_updates: dict[str, Any],
    ) -> None:
        if not dh.macros:
            return

        live_macro_map = {m["macro"]: m for m in live_macros}
        macro_diffs: dict[str, Any] = {}

        for dm in dh.macros:
            if dm.macro not in live_macro_map:
                macro_diffs[dm.macro] = {"action": "create", "type": dm.type}
            else:
                lm = live_macro_map[dm.macro]
                # For secret macros, Zabbix masks the value as '******'
                is_secret = int(lm.get("type", 0)) == MacroType.SECRET
                if not is_secret and lm.get("value") != dm.value:
                    macro_diffs[dm.macro] = {
                        "action": "update_value",
                        "old": lm.get("value"),
                        "new": dm.value,
                    }
                if int(lm.get("type", 0)) != int(dm.type):
                    macro_diffs[dm.macro] = {
                        "action": "update_type",
                        "old": lm.get("type"),
                        "new": dm.type,
                    }

        if macro_diffs:
            host_updates["macros"] = macro_diffs
