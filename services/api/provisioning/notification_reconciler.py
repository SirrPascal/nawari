"""Notification and Administrator Recipient Reconciler for Zabbix 7.4.

Manages idempotent provisioning of the dedicated user group
'Nawari Avaya & Communications Administrators', the four designated administrators,
their user media profiles, and the authoritative communication alert action.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from services.api.client.zabbix_client import ZabbixClient

logger = logging.getLogger("nawari.notification_reconciler")

ADMIN_USER_GROUP = "Nawari Avaya & Communications Administrators"
ACTION_NAME = "Nawari Avaya & Communication Alerting"

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

COMMUNICATION_HOST_GROUPS = [
    "Voice Infrastructure",
    "Avaya Infrastructure",
    "Edge SBC",
    "SIP Carrier Trunks",
    "Communications Applications",
    "Synthetic Probes",
]


class NotificationReconciler:
    """Reconciles Zabbix users, groups, user media, and actions."""

    def __init__(self, client: ZabbixClient):
        self.client = client

    def reconcile_all(self) -> Dict[str, Any]:
        """Execute full reconciliation of user groups, administrators, and alerting action."""
        group_id = self.ensure_admin_group()
        user_ids = self.ensure_administrators(group_id)
        action_id = self.ensure_communication_action(group_id)
        return {
            "group_id": group_id,
            "user_ids": user_ids,
            "action_id": action_id,
            "recipients_count": len(user_ids),
        }

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
        # Find default Email media type
        mts = self.client.call("mediatype.get", {"filter": {"name": "Email"}})
        email_mt_id = str(mts[0]["mediatypeid"]) if mts else "1"

        # Find Admin role (type 2)
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
                    # Update user media
                    update_payload["medias"] = [desired_media]
                    needs_update = True

                if needs_update:
                    self.client.call("user.update", update_payload)
                    logger.info(f"Updated user '{username}' (ID: {uid})")
            else:
                # Create user
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
        # Find hostgroup IDs for all covered communication host groups
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
                    "mediatypeid": 0,  # Send to all enabled recipient media types
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
                "operationtype": 11,  # Notify all involved in previous steps
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

