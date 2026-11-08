"""Notification and Administrator Recipient Reconciler for Zabbix 7.4.

Manages idempotent provisioning of:
1. User groups:
   - 'Nawari Avaya & Communications Administrators' (4 designated voice engineers)
   - 'Nawari Total Outage Recipients' (4 voice engineers + Kenya Airways IT Service Desk)
2. Users and user media profiles (CONFIGURED_UNVERIFIED, zero unsolicited test emails).
3. Trigger event tagging with 'notification_class' (total_outage, service_outage, degradation,
   component_failure, monitoring_failure, synthetic_failure, informational).
4. Structured Trigger Actions:
   - 'Nawari Avaya & Communication Alerting' (authoritative backward-compatible communication action)
   - 'Total Outage Alert' (delivers to all 5 recipients with monitoring-observed {EVENT.DURATION})
   - 'Communication Service Alert' (delivers to 4 communication administrators)
   - 'Synthetic Voice Failure Alert' (delivers to 4 communication administrators)
   - 'Network Degradation Alert' (delivers to technical team)
   - 'Component Failure Alert' (delivers to technical team)
   - 'Monitoring Failure Alert' (delivers to technical team)

All recipient-facing notifications use generic, professional operational language
without mentioning internal monitoring tool or platform names (e.g. no 'Nawari' or 'Zabbix').
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from services.api.client.zabbix_client import ZabbixClient

logger = logging.getLogger("nawari.notification_reconciler")

ADMIN_USER_GROUP = "Nawari Avaya & Communications Administrators"
TOTAL_OUTAGE_USER_GROUP = "Nawari Total Outage Recipients"
TECH_ADMIN_USER_GROUP = "Zabbix administrators"

ACTION_NAME = "Nawari Avaya & Communication Alerting"
ACTION_TOTAL_OUTAGE = "Total Outage Alert"
ACTION_COMM_SERVICE = "Communication Service Alert"
ACTION_SYNTHETIC_VOICE = "Synthetic Voice Failure Alert"
ACTION_NETWORK_DEGRADATION = "Network Degradation Alert"
ACTION_COMPONENT_FAILURE = "Component Failure Alert"
ACTION_MONITORING_FAILURE = "Monitoring Failure Alert"

DESIGNATED_ADMINISTRATORS = [
    {
        "username": "john.gacomo",
        "name": "John",
        "surname": "Gacomo",
        "email": "John.Gacomo@kenya-airways.com",
    },
    {
        "username": "robinson.wainaina",
        "name": "Robinson",
        "surname": "Wainaina",
        "email": "Robinson.Wainaina@kenya-airways.com",
    },
    {
        "username": "pascal.gathungu",
        "name": "Pascal",
        "surname": "Gathungu",
        "email": "Pascal.Gathungu@kenya-airways.com",
    },
    {
        "username": "mercy.vaati",
        "name": "Mercy",
        "surname": "Vaati",
        "email": "Mercy.Vaati@kenya-airways.com",
    },
]

SERVICE_DESK_RECIPIENT = {
    "username": "itservicedesk",
    "name": "IT Service Desk",
    "surname": "Kenya Airways",
    "email": "ITservicedesk@kenya-airways.com",
}

COMMUNICATION_HOST_GROUPS = [
    "Voice Infrastructure",
    "Avaya Infrastructure",
    "Edge SBC",
    "SIP Carrier Trunks",
    "Communications Applications",
    "Synthetic Probes",
]

# Clean Operational Notification Templates (No monitoring engine branding)
TOTAL_OUTAGE_PROBLEM_SUBJECT = "[TOTAL OUTAGE] — {HOST.NAME} — {EVENT.NAME}"
TOTAL_OUTAGE_PROBLEM_MESSAGE = (
    "A total outage has been identified affecting the following device or service.\n\n"
    "Affected Device/Service: {HOST.NAME}\n"
    "Issue: {EVENT.NAME}\n"
    "Severity: {EVENT.SEVERITY}\n"
    "Outage Start: {EVENT.DATE} {EVENT.TIME}\n"
    "Details: {EVENT.OPDATA}\n"
    "Status: OUTAGE IN PROGRESS\n\n"
    "The affected device or service is currently unavailable. Please investigate and take the necessary action to restore normal operations.\n\n"
    "A further notification will be issued once service has been restored."
)

TOTAL_OUTAGE_ESCALATION_SUBJECT = "[TOTAL OUTAGE ESCALATION] — {HOST.NAME} — {EVENT.NAME} — Duration: {EVENT.AGE}"
TOTAL_OUTAGE_ESCALATION_MESSAGE = (
    "An unresolved total outage continues to affect the following device or service.\n\n"
    "Affected Device/Service: {HOST.NAME}\n"
    "Issue: {EVENT.NAME}\n"
    "Severity: {EVENT.SEVERITY}\n"
    "Outage Start: {EVENT.DATE} {EVENT.TIME}\n"
    "Current Duration: {EVENT.AGE}\n"
    "Details: {EVENT.OPDATA}\n"
    "Status: OUTAGE UNRESOLVED (ESCALATION)\n\n"
    "The affected device or service remains unavailable. Please escalate immediately to the designated duty manager."
)

TOTAL_OUTAGE_RECOVERY_SUBJECT = "[RECOVERED] — {HOST.NAME} — Total Downtime: {EVENT.DURATION}"
TOTAL_OUTAGE_RECOVERY_MESSAGE = (
    "The previously reported outage affecting the following device or service has been resolved.\n\n"
    "Affected Device/Service: {HOST.NAME}\n"
    "Original Issue: {EVENT.NAME}\n"
    "Severity: {EVENT.SEVERITY}\n"
    "Outage Start: {EVENT.DATE} {EVENT.TIME}\n"
    "Recovery Time: {EVENT.RECOVERY.DATE} {EVENT.RECOVERY.TIME}\n"
    "Total Downtime: {EVENT.DURATION}\n"
    "Status: RECOVERED\n\n"
    "The affected device or service is responding again and has returned to an operational state.\n\n"
    "Please review the incident and establish the underlying cause where necessary."
)


def classify_trigger_description(desc: str, strict_service_semantics: bool = False) -> str:
    """Deterministically classify a trigger into its notification_class tag value.

    Args:
        desc: The trigger description string.
        strict_service_semantics: When True (Phase 13.8 service-outage semantics),
            distinguishes isolated voice component/host unreachability (e.g. single SBCE,
            single G450, single SIP trunk) as 'service_outage' rather than 'total_outage'.
            True 'total_outage' is reserved for network core / core transport failures
            affecting the entire site or cluster-wide outages.
    """
    d = desc.lower()

    if strict_service_semantics:
        if any(k in d for k in [
            "total network core transport failure",
            "network core transport failure",
            "network core down",
            "total outage",
            "core switch unreachable",
            "unavailable by icmp ping",
            "device unreachable by icmp ping",
            "core cluster failure",
            "all session managers unreachable",
            "all carrier routes down"
        ]):
            return "total_outage"
        elif any(k in d for k in [
            "appliance unreachable", "host unavailable", "processor unreachable",
            "chassis unreachable", "endpoint unreachable",
            "sip entity down", "deny new service", "unregistered from communication manager",
            "consecutive options probe failures", "dns srv/a resolution failure",
            "recording pipeline health failure"
        ]):
            return "service_outage"
    else:
        if any(k in d for k in [
            "total network core transport failure",
            "network core transport failure",
            "network core down",
            "total outage",
            "core switch unreachable",
            "appliance unreachable", "host unavailable", "processor unreachable",
            "chassis unreachable", "endpoint unreachable", "unavailable by icmp ping"
        ]):
            return "total_outage"
        elif any(k in d for k in [
            "sip entity down", "deny new service", "unregistered from communication manager",
            "consecutive options probe failures", "dns srv/a resolution failure",
            "recording pipeline health failure"
        ]):
            return "service_outage"

    if any(k in d for k in [
        "synthetic voice", "synthetic probe", "one-way audio"
    ]):
        return "synthetic_failure"
    elif any(k in d for k in [
        "snmp agent is not responding", "telemetry stale", "telemetry missing",
        "synthetic sip options probe failure", "probe telemetry is stale",
        "no snmp data collection"
    ]):
        return "monitoring_failure"
    elif any(k in d for k in [
        "power supply unit", "fan tray", "e1/isdn", "ambient temperature",
        "telephony alarms present", "critical enterprise alarm", "link down"
    ]):
        return "component_failure"
    elif any(k in d for k in [
        "device has just been restarted", "host has been restarted",
        "system name has changed", "certificate expiration"
    ]):
        return "informational"
    elif any(k in d for k in [
        "utilization", "capacity", "failure rate", "discards", "packet loss",
        "jitter", "latency", "call rate abnormal", "service level degradation",
        "storage warning", "partially up", "icmp ping loss", "icmp response time",
        "high bandwidth"
    ]):
        return "degradation"
    return "degradation"


def classify_service_outage_semantics(desc: str) -> str:
    """Phase 13.8 helper to classify triggers using strict service-outage semantics."""
    return classify_trigger_description(desc, strict_service_semantics=True)


class NotificationReconciler:
    """Reconciles Zabbix users, groups, user media, trigger tags, and alerting actions."""

    def __init__(self, client: ZabbixClient):
        self.client = client

    def reconcile_all(self, include_total_outage: bool = False) -> Dict[str, Any]:
        """Execute reconciliation of communication administrators and actions.

        Maintains exact backward compatibility with Phase 13.4 tests (4 administrators).
        If include_total_outage is True, also provisions Total Outage policy.
        """
        group_id = self.ensure_admin_group()
        user_ids = self.ensure_administrators(group_id)
        action_id = self.ensure_communication_action(group_id)

        result: Dict[str, Any] = {
            "group_id": group_id,
            "user_ids": user_ids,
            "action_id": action_id,
            "recipients_count": len(user_ids),
        }

        if include_total_outage:
            to_res = self.reconcile_total_outage_policy()
            result.update(to_res)

        return result

    def ensure_admin_group(self) -> str:
        """Ensure the dedicated user group exists and has proper permissions."""
        grps = self.client.call("usergroup.get", {"filter": {"name": ADMIN_USER_GROUP}})
        if grps:
            logger.info(f"User group '{ADMIN_USER_GROUP}' exists (ID: {grps[0]['usrgrpid']})")
            return str(grps[0]["usrgrpid"])

        res = self.client.call(
            "usergroup.create",
            {
                "name": ADMIN_USER_GROUP,
                "gui_access": 0,
                "users_status": 0,
            },
        )
        gid = str(res["usrgrpids"][0])
        logger.info(f"Created user group '{ADMIN_USER_GROUP}' (ID: {gid})")
        return gid

    def ensure_administrators(self, group_id: str) -> Dict[str, str]:
        """Ensure all four designated administrators exist with valid media and group membership."""
        mts = self.client.call("mediatype.get", {"filter": {"name": "Email"}})
        email_mt_id = str(mts[0]["mediatypeid"]) if mts else "1"

        roles = self.client.call("role.get", {"filter": {"name": "Admin role"}})
        role_id = str(roles[0]["roleid"]) if roles else "2"

        user_ids: Dict[str, str] = {}

        for admin in DESIGNATED_ADMINISTRATORS:
            username = admin["username"]
            email = admin["email"]
            existing = self.client.call(
                "user.get",
                {
                    "filter": {"username": username},
                    "selectUsrgrps": ["usrgrpid", "name"],
                    "selectMedias": "extend",
                },
            )

            desired_media = {
                "mediatypeid": email_mt_id,
                "sendto": [email],
                "active": 0,  # Enabled
                "severity": 63,  # All 6 severities (Information..Disaster)
                "period": "1-7,00:00-24:00",
            }

            if existing:
                uid = str(existing[0]["userid"])
                user_ids[username] = uid

                # Check group membership
                current_grps = [str(g["usrgrpid"]) for g in existing[0].get("usrgrps", [])]
                update_payload: Dict[str, Any] = {"userid": uid}
                needs_update = False

                if group_id not in current_grps:
                    current_grps.append(group_id)
                    update_payload["usrgrps"] = [{"usrgrpid": gid} for gid in current_grps]
                    needs_update = True

                # Check media
                current_medias = existing[0].get("medias", [])
                has_valid_email = any(
                    str(m.get("mediatypeid")) == email_mt_id
                    and email in m.get("sendto", [])
                    and str(m.get("active")) == "0"
                    for m in current_medias
                )

                if not has_valid_email:
                    update_payload["medias"] = [desired_media]
                    needs_update = True

                if needs_update:
                    self.client.call("user.update", update_payload)
                    logger.info(f"Updated user '{username}' (ID: {uid})")
            else:
                create_payload = {
                    "username": username,
                    "name": admin["name"],
                    "surname": admin["surname"],
                    "passwd": "NawariSecOps2026!KQ",
                    "roleid": role_id,
                    "usrgrps": [{"usrgrpid": group_id}],
                    "medias": [desired_media],
                }
                res = self.client.call("user.create", create_payload)
                uid = str(res["userids"][0])
                user_ids[username] = uid
                logger.info(f"Created user '{username}' (ID: {uid}) with media {email}")

        return user_ids

    def ensure_communication_action(self, group_id: str) -> str:
        """Ensure the authoritative communication alert action exists and targets the group."""
        hgrps = self.client.call("hostgroup.get", {"filter": {"name": COMMUNICATION_HOST_GROUPS}})
        hgrp_ids = [str(g["groupid"]) for g in hgrps]

        conditions: List[Dict[str, Any]] = [
            {"conditiontype": 4, "operator": 5, "value": "2"}  # Severity >= Warning
        ]
        for gid in hgrp_ids:
            conditions.append({"conditiontype": 0, "operator": 0, "value": gid})

        operations = [
            {
                "operationtype": 0,  # Send message
                "esc_step_from": 1,
                "esc_step_to": 1,
                "opmessage_grp": [{"usrgrpid": group_id}],
                "opmessage": {
                    "default_msg": 1,
                    "mediatypeid": 0,
                },
            },
            {
                "operationtype": 0,
                "esc_step_from": 2,
                "esc_step_to": 0,  # Repeat indefinitely every 30m
                "esc_period": "1800s",
                "opmessage_grp": [{"usrgrpid": group_id}],
                "opmessage": {
                    "default_msg": 1,
                    "mediatypeid": 0,
                },
            },
        ]

        recovery_operations = [
            {
                "operationtype": 11,  # Notify all involved
                "opmessage": {"default_msg": 1},
            }
        ]

        update_operations = [
            {
                "operationtype": 12,  # Notify all involved
                "opmessage": {"default_msg": 1},
            }
        ]

        existing = self.client.call("action.get", {"filter": {"name": ACTION_NAME}})
        if existing:
            action_id = str(existing[0]["actionid"])
            update_payload = {
                "actionid": action_id,
                "status": 0,  # Enabled
                "esc_period": "30m",
                "pause_suppressed": "1",
                "filter": {
                    "evaltype": 0,
                    "conditions": conditions,
                },
                "operations": operations,
                "recovery_operations": recovery_operations,
                "update_operations": update_operations,
            }
            self.client.call("action.update", update_payload)
            logger.info(f"Updated communication action '{ACTION_NAME}' (ID: {action_id})")
            return action_id

        create_payload = {
            "name": ACTION_NAME,
            "eventsource": 0,
            "status": 0,
            "esc_period": "30m",
            "pause_suppressed": "1",
            "notify_if_canceled": "1",
            "filter": {
                "evaltype": 0,
                "conditions": conditions,
            },
            "operations": operations,
            "recovery_operations": recovery_operations,
            "update_operations": update_operations,
        }
        res = self.client.call("action.create", create_payload)
        action_id = str(res["actionids"][0])
        logger.info(f"Created communication action '{ACTION_NAME}' (ID: {action_id})")
        return action_id

    # --------------------------------------------------------------------------
    # Total Outage Notification Enhancement (Phase 13.6)
    # --------------------------------------------------------------------------

    def reconcile_total_outage_policy(self) -> Dict[str, Any]:
        """Reconcile Total Outage user group, 5 recipients, trigger tags, and structured actions."""
        admin_group_id = self.ensure_admin_group()
        total_outage_group_id = self.ensure_group(
            TOTAL_OUTAGE_USER_GROUP,
            "Designated recipients for total outages and service downtime recovery notifications (Four communications administrators and KQ IT Service Desk)"
        )

        all_user_ids = self.ensure_all_recipients(admin_group_id, total_outage_group_id)
        tag_stats = self.reconcile_trigger_tags()
        actions = self.ensure_structured_actions(admin_group_id, total_outage_group_id)

        # Phase 13.8: Ensure User Groups 14 and 15 have read permissions across monitored host groups
        self.ensure_group_permissions(admin_group_id)
        self.ensure_group_permissions(total_outage_group_id)

        # Phase 13.7: Gracefully supersede and disable legacy Action 7 to guarantee mutual exclusivity
        # and prevent duplicate notifications for the four administrators who belong to both groups.
        legacy_actions = self.client.call("action.get", {"filter": {"name": ACTION_NAME}})
        if legacy_actions:
            legacy_id = str(legacy_actions[0]["actionid"])
            self.client.call("action.update", {"actionid": legacy_id, "status": 1})
            logger.info(f"Retired legacy action '{ACTION_NAME}' (ID: {legacy_id}) to prevent duplicate notifications")

        return {
            "total_outage_group_id": total_outage_group_id,
            "all_recipients_count": len(all_user_ids),
            "all_user_ids": all_user_ids,
            "tag_stats": tag_stats,
            "structured_actions": actions,
        }

    def ensure_group_permissions(self, group_id: str) -> None:
        """Ensure the user group has read permission (2) across all host groups."""
        try:
            hgrps = self.client.call("hostgroup.get", {"output": ["groupid"]})
            if hgrps:
                rights = [{"id": str(g["groupid"]), "permission": 2} for g in hgrps]
                self.client.call("usergroup.update", {"usrgrpid": group_id, "hostgroup_rights": rights})
        except Exception as e:
            logger.debug(f"Failed to update hostgroup_rights for group {group_id}: {e}")

    def ensure_group(self, group_name: str, description: str) -> str:
        """Ensure a user group exists and return its groupid."""
        grps = self.client.call("usergroup.get", {"filter": {"name": group_name}})
        if grps:
            logger.info(f"User group '{group_name}' exists (ID: {grps[0]['usrgrpid']})")
            return str(grps[0]["usrgrpid"])

        res = self.client.call(
            "usergroup.create",
            {
                "name": group_name,
                "gui_access": 0,
                "users_status": 0,
            },
        )
        gid = str(res["usrgrpids"][0])
        logger.info(f"Created user group '{group_name}' (ID: {gid})")
        return gid

    def ensure_all_recipients(self, admin_group_id: str, total_outage_group_id: str) -> Dict[str, str]:
        """Ensure all 5 recipients exist with active media and proper group memberships."""
        mts = self.client.call("mediatype.get", {"filter": {"name": "Email"}})
        email_mt_id = str(mts[0]["mediatypeid"]) if mts else "1"

        roles = self.client.call("role.get", {"filter": {"name": "Admin role"}})
        role_id = str(roles[0]["roleid"]) if roles else "2"

        user_ids: Dict[str, str] = {}

        # 1. Four Communication Administrators (in both groups)
        for admin in DESIGNATED_ADMINISTRATORS:
            uid = self._ensure_single_user(
                admin["username"],
                admin["name"],
                admin["surname"],
                admin["email"],
                email_mt_id,
                role_id,
                [admin_group_id, total_outage_group_id]
            )
            user_ids[admin["username"]] = uid

        # 2. IT Service Desk (in Total Outage group only)
        sd = SERVICE_DESK_RECIPIENT
        sd_uid = self._ensure_single_user(
            sd["username"],
            sd["name"],
            sd["surname"],
            sd["email"],
            email_mt_id,
            role_id,
            [total_outage_group_id]
        )
        user_ids[sd["username"]] = sd_uid

        return user_ids

    def _ensure_single_user(
        self,
        username: str,
        name: str,
        surname: str,
        email: str,
        mediatypeid: str,
        roleid: str,
        desired_group_ids: List[str]
    ) -> str:
        """Create or update a single user with group memberships and media."""
        existing = self.client.call(
            "user.get",
            {
                "filter": {"username": username},
                "selectUsrgrps": ["usrgrpid", "name"],
                "selectMedias": "extend",
            },
        )

        desired_media = {
            "mediatypeid": mediatypeid,
            "sendto": [email],
            "active": 0,  # Enabled
            "severity": 63,  # All 6 severities
            "period": "1-7,00:00-24:00",
        }

        if existing:
            uid = str(existing[0]["userid"])
            current_grps = [str(g["usrgrpid"]) for g in existing[0].get("usrgrps", [])]
            update_payload: Dict[str, Any] = {"userid": uid}
            needs_update = False

            updated_grps = list(set(current_grps + desired_group_ids))
            if set(updated_grps) != set(current_grps):
                update_payload["usrgrps"] = [{"usrgrpid": gid} for gid in updated_grps]
                needs_update = True

            current_medias = existing[0].get("medias", [])
            has_valid_email = any(
                str(m.get("mediatypeid")) == mediatypeid
                and email in m.get("sendto", [])
                and str(m.get("active")) == "0"
                for m in current_medias
            )
            if not has_valid_email:
                update_payload["medias"] = [desired_media]
                needs_update = True

            if needs_update:
                self.client.call("user.update", update_payload)
                logger.info(f"Updated user '{username}' (ID: {uid})")
            return uid
        else:
            create_payload = {
                "username": username,
                "name": name,
                "surname": surname,
                "passwd": "NawariSecOps2026!KQ",
                "roleid": roleid,
                "usrgrps": [{"usrgrpid": gid} for gid in desired_group_ids],
                "medias": [desired_media],
            }
            res = self.client.call("user.create", create_payload)
            uid = str(res["userids"][0])
            logger.info(f"Created user '{username}' (ID: {uid}) with media {email}")
            return uid

    def reconcile_trigger_tags(self) -> Dict[str, int]:
        """Apply 'notification_class' tags across all triggers on Nawari templates and hosts."""
        template_names = [
            "Nawari Generic SNMP Base",
            "Nawari Network Device by SNMP",
            "Nawari Avaya SBCE by SNMP",
            "Nawari Voice Synthetic Probe by Zabbix Trapper",
            "Template Nawari Endpoint Probe by Zabbix Trapper",
            "Nawari Avaya Session Manager by SNMP",
            "Nawari Avaya Communication Manager by SNMP",
            "Nawari Avaya G450 Media Gateway by SNMP",
            "Nawari SIP Trunk by Trapper",
            "Nawari Avaya CMS and WFO by Trapper",
        ]

        tpls = self.client.call("template.get", {"filter": {"name": template_names}, "output": ["templateid", "name"]})
        tpl_ids = [t["templateid"] for t in tpls]

        triggers = self.client.call(
            "trigger.get",
            {
                "templateids": tpl_ids,
                "output": ["triggerid", "description"],
                "selectTags": "extend",
            }
        )

        net_hosts = self.client.call("host.get", {"filter": {"host": ["core-gw-01", "mock-core-switch-01", "endpoint-probe-01"]}, "output": ["hostid", "host"]})
        if net_hosts:
            host_trs = self.client.call(
                "trigger.get",
                {
                    "hostids": [h["hostid"] for h in net_hosts],
                    "output": ["triggerid", "description"],
                    "selectTags": "extend",
                }
            )
            triggers.extend(host_trs)

        counts: Dict[str, int] = {}
        updated_count = 0

        for tr in triggers:
            tid = tr["triggerid"]
            desc = tr["description"]
            nclass = classify_trigger_description(desc)
            counts[nclass] = counts.get(nclass, 0) + 1

            tags = tr.get("tags", [])
            existing_tag_val = None
            for t in tags:
                if t.get("tag") == "notification_class":
                    existing_tag_val = t.get("value")
                    break

            if existing_tag_val != nclass:
                cleaned_tags = [t for t in tags if t.get("tag") != "notification_class"]
                cleaned_tags.append({"tag": "notification_class", "value": nclass})
                try:
                    self.client.call("trigger.update", {"triggerid": tid, "tags": cleaned_tags})
                    updated_count += 1
                except Exception as e:
                    logger.debug(f"Failed to update trigger {tid} tags: {e}")

        logger.info(f"Reconciled trigger tags: {updated_count} triggers updated. Counts: {counts}")
        return counts

    def ensure_structured_actions(self, admin_group_id: str, total_outage_group_id: str) -> Dict[str, str]:
        """Ensure all 6 structured trigger actions exist with proper tags, templates, and recipients."""
        tech_grps = self.client.call("usergroup.get", {"filter": {"name": TECH_ADMIN_USER_GROUP}})
        tech_group_id = str(tech_grps[0]["usrgrpid"]) if tech_grps else "7"

        action_ids: Dict[str, str] = {}

        # 1. Total Outage Alert Action
        action_ids[ACTION_TOTAL_OUTAGE] = self._create_or_update_action(
            name=ACTION_TOTAL_OUTAGE,
            tag_value="total_outage",
            recipient_group_id=total_outage_group_id,
            problem_subject=TOTAL_OUTAGE_PROBLEM_SUBJECT,
            problem_message=TOTAL_OUTAGE_PROBLEM_MESSAGE,
            escalation_subject=TOTAL_OUTAGE_ESCALATION_SUBJECT,
            escalation_message=TOTAL_OUTAGE_ESCALATION_MESSAGE,
            recovery_subject=TOTAL_OUTAGE_RECOVERY_SUBJECT,
            recovery_message=TOTAL_OUTAGE_RECOVERY_MESSAGE,
            repeat_interval_sec=1800,  # Repeat every 30 minutes
        )

        # 2. Communication Service Alert Action
        action_ids[ACTION_COMM_SERVICE] = self._create_or_update_action(
            name=ACTION_COMM_SERVICE,
            tag_value="service_outage",
            recipient_group_id=admin_group_id,
            problem_subject="[SERVICE OUTAGE] — {HOST.NAME} — {EVENT.NAME}",
            problem_message=(
                "A service outage has been identified affecting the following communications service.\n\n"
                "Affected Service: {HOST.NAME}\n"
                "Issue: {EVENT.NAME}\n"
                "Severity: {EVENT.SEVERITY}\n"
                "Detected: {EVENT.DATE} {EVENT.TIME}\n"
                "Details: {EVENT.OPDATA}\n"
                "Status: SERVICE OUTAGE IN PROGRESS\n\n"
                "The affected communications service is currently unavailable. Please investigate and restore normal operations."
            ),
            recovery_subject="[RECOVERED] — {HOST.NAME} — {EVENT.NAME} — Duration: {EVENT.DURATION}",
            recovery_message=(
                "The previously reported communications service outage has recovered.\n\n"
                "Affected Service: {HOST.NAME}\n"
                "Original Issue: {EVENT.NAME}\n"
                "Outage Start: {EVENT.DATE} {EVENT.TIME}\n"
                "Recovery Time: {EVENT.RECOVERY.DATE} {EVENT.RECOVERY.TIME}\n"
                "Total Downtime: {EVENT.DURATION}\n"
                "Status: RECOVERED"
            ),
            repeat_interval_sec=3600,
        )

        # 3. Synthetic Voice Failure Alert Action
        action_ids[ACTION_SYNTHETIC_VOICE] = self._create_or_update_action(
            name=ACTION_SYNTHETIC_VOICE,
            tag_value="synthetic_failure",
            recipient_group_id=admin_group_id,
            problem_subject="[SYNTHETIC ALERT] — {HOST.NAME} — {EVENT.NAME}",
            problem_message=(
                "A synthetic voice probe has detected a failure or voice quality degradation.\n\n"
                "Probe Target: {HOST.NAME}\n"
                "Issue: {EVENT.NAME}\n"
                "Severity: {EVENT.SEVERITY}\n"
                "Detected: {EVENT.DATE} {EVENT.TIME}\n"
                "Details: {EVENT.OPDATA}\n"
                "Status: SYNTHETIC TEST FAILURE\n\n"
                "Please inspect synthetic probe metrics and verify voice path integrity."
            ),
            recovery_subject="[RECOVERED] — {HOST.NAME} — {EVENT.NAME} — Duration: {EVENT.DURATION}",
            recovery_message=(
                "The synthetic voice probe condition has cleared.\n\n"
                "Probe Target: {HOST.NAME}\n"
                "Original Issue: {EVENT.NAME}\n"
                "Duration: {EVENT.DURATION}\n"
                "Status: RECOVERED"
            ),
            repeat_interval_sec=0,
        )

        # 4. Network Degradation Alert Action
        action_ids[ACTION_NETWORK_DEGRADATION] = self._create_or_update_action(
            name=ACTION_NETWORK_DEGRADATION,
            tag_value="degradation",
            recipient_group_id=tech_group_id,
            problem_subject="[DEGRADATION] — {HOST.NAME} — {EVENT.NAME}",
            problem_message=(
                "Performance threshold degradation detected.\n\n"
                "Affected Device/Component: {HOST.NAME}\n"
                "Condition: {EVENT.NAME}\n"
                "Severity: {EVENT.SEVERITY}\n"
                "Detected: {EVENT.DATE} {EVENT.TIME}\n"
                "Details: {EVENT.OPDATA}\n"
                "Status: DEGRADATION ACTIVE"
            ),
            recovery_subject="[RECOVERED] — {HOST.NAME} — {EVENT.NAME} — Duration: {EVENT.DURATION}",
            recovery_message=(
                "Performance metrics have returned to nominal baseline thresholds.\n\n"
                "Affected Device/Component: {HOST.NAME}\n"
                "Original Condition: {EVENT.NAME}\n"
                "Duration: {EVENT.DURATION}\n"
                "Status: NORMAL"
            ),
            repeat_interval_sec=7200,
        )

        # 5. Component Failure Alert Action
        action_ids[ACTION_COMPONENT_FAILURE] = self._create_or_update_action(
            name=ACTION_COMPONENT_FAILURE,
            tag_value="component_failure",
            recipient_group_id=tech_group_id,
            problem_subject="[COMPONENT FAILURE] — {HOST.NAME} — {EVENT.NAME}",
            problem_message=(
                "Hardware component or interface failure detected.\n\n"
                "Affected Device: {HOST.NAME}\n"
                "Component Issue: {EVENT.NAME}\n"
                "Severity: {EVENT.SEVERITY}\n"
                "Detected: {EVENT.DATE} {EVENT.TIME}\n"
                "Details: {EVENT.OPDATA}\n"
                "Status: COMPONENT FAILURE"
            ),
            recovery_subject="[RECOVERED] — {HOST.NAME} — {EVENT.NAME} — Duration: {EVENT.DURATION}",
            recovery_message=(
                "The hardware component or interface has recovered.\n\n"
                "Affected Device: {HOST.NAME}\n"
                "Original Issue: {EVENT.NAME}\n"
                "Duration: {EVENT.DURATION}\n"
                "Status: RECOVERED"
            ),
            repeat_interval_sec=3600,
        )

        # 6. Monitoring Failure Alert Action
        action_ids[ACTION_MONITORING_FAILURE] = self._create_or_update_action(
            name=ACTION_MONITORING_FAILURE,
            tag_value="monitoring_failure",
            recipient_group_id=tech_group_id,
            problem_subject="[MONITORING FAILURE] — {HOST.NAME} — {EVENT.NAME}",
            problem_message=(
                "Monitoring agent or telemetry collection failure detected.\n\n"
                "Monitored Entity: {HOST.NAME}\n"
                "Issue: {EVENT.NAME}\n"
                "Severity: {EVENT.SEVERITY}\n"
                "Detected: {EVENT.DATE} {EVENT.TIME}\n"
                "Details: {EVENT.OPDATA}\n"
                "Status: TELEMETRY COLLECTION FAILURE\n\n"
                "Note: Underlying device may remain operational; telemetry retrieval has stalled."
            ),
            recovery_subject="[RECOVERED] — {HOST.NAME} — {EVENT.NAME} — Duration: {EVENT.DURATION}",
            recovery_message=(
                "Telemetry collection has resumed successfully.\n\n"
                "Monitored Entity: {HOST.NAME}\n"
                "Original Issue: {EVENT.NAME}\n"
                "Duration: {EVENT.DURATION}\n"
                "Status: MONITORING RESTORED"
            ),
            repeat_interval_sec=0,
        )

        return action_ids

    def _create_or_update_action(
        self,
        name: str,
        tag_value: str,
        recipient_group_id: str,
        problem_subject: str,
        problem_message: str,
        recovery_subject: str,
        recovery_message: str,
        repeat_interval_sec: int = 1800,
        escalation_subject: Optional[str] = None,
        escalation_message: Optional[str] = None,
    ) -> str:
        """Create or update a single Zabbix action filtered by notification_class tag."""
        conditions = [
            {
                "conditiontype": 26,  # Tag value
                "operator": 0,        # equals
                "value2": "notification_class",
                "value": tag_value,
            }
        ]

        operations = [
            {
                "operationtype": 0,  # Send message
                "esc_step_from": 1,
                "esc_step_to": 1,
                "opmessage_grp": [{"usrgrpid": recipient_group_id}],
                "opmessage": {
                    "default_msg": 0,
                    "subject": problem_subject,
                    "message": problem_message,
                    "mediatypeid": 0,
                },
            }
        ]

        if repeat_interval_sec > 0:
            esc_sub = escalation_subject or problem_subject
            esc_msg = escalation_message or problem_message
            operations.append({
                "operationtype": 0,
                "esc_step_from": 2,
                "esc_step_to": 0,  # Repeat indefinitely until recovery
                "esc_period": f"{repeat_interval_sec}s",
                "opmessage_grp": [{"usrgrpid": recipient_group_id}],
                "opmessage": {
                    "default_msg": 0,
                    "subject": esc_sub,
                    "message": esc_msg,
                    "mediatypeid": 0,
                },
            })

        recovery_operations = [
            {
                "operationtype": 11,  # Notify all involved
                "opmessage": {
                    "default_msg": 0,
                    "subject": recovery_subject,
                    "message": recovery_message,
                },
            }
        ]

        update_operations = [
            {
                "operationtype": 12,  # Notify all involved
                "opmessage": {
                    "default_msg": 1,
                },
            }
        ]

        existing = self.client.call("action.get", {"filter": {"name": name}})
        if existing:
            action_id = str(existing[0]["actionid"])
            update_payload = {
                "actionid": action_id,
                "status": 0,  # Enabled
                "esc_period": "30m",
                "pause_suppressed": "1",
                "filter": {
                    "evaltype": 0,
                    "conditions": conditions,
                },
                "operations": operations,
                "recovery_operations": recovery_operations,
                "update_operations": update_operations,
            }
            self.client.call("action.update", update_payload)
            logger.info(f"Updated action '{name}' (ID: {action_id})")
            return action_id

        create_payload = {
            "name": name,
            "eventsource": 0,
            "status": 0,
            "esc_period": "30m",
            "pause_suppressed": "1",
            "notify_if_canceled": "1",
            "filter": {
                "evaltype": 0,
                "conditions": conditions,
            },
            "operations": operations,
            "recovery_operations": recovery_operations,
            "update_operations": update_operations,
        }
        res = self.client.call("action.create", create_payload)
        action_id = str(res["actionids"][0])
        logger.info(f"Created action '{name}' (ID: {action_id})")
        return action_id
