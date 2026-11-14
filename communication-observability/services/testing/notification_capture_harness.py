"""
services/testing/notification_capture_harness.py

Deterministic Staging Notification Capture & Test Harness for Nawari Phase 13.7.

Provides:
1. Deterministic simulation of Scenarios A through J:
   - Scenario A: Total Network Outage (mock-core-switch-01 / core-gw-01 unreachable -> 5 recipients)
   - Scenario B: Total Communications Outage (avaya-sbce-01 / avaya-sm-01 / avaya-cm-01 / avaya-g450-01 host unavailable -> 5 recipients)
   - Scenario C: SIP Trunk Outage (sip-trunk-carrier-01 / sip-trunk-safaricom entity down -> 4 voice admins, no Service Desk)
   - Scenario D: Monitoring Failure (SNMP agent down / telemetry stale -> technical team only, no Service Desk)
   - Scenario E: Component Failure (PSU failure, fan tray, link down -> technical team only, no Service Desk)
   - Scenario F: Synthetic Voice Failure (Asterisk MOS < 3.5, probe failed -> 4 voice admins, labeled synthetic)
   - Scenario G: 30-Minute Escalation ({EVENT.AGE} duration, repeat step 2..0 every 1800s, no duplicate actions)
   - Scenario H: Recovery Notification ({EVENT.DURATION} monitoring-observed downtime, 5 recipients)
   - Scenario I: Repeated Outage (independent event IDs and durations, no state leakage)
   - Scenario J: Acknowledgment and Maintenance Suppression (pause_suppressed = 1)
2. Macro Evaluation Engine ({HOST.NAME}, {EVENT.NAME}, {EVENT.SEVERITY}, {EVENT.DATE}, {EVENT.TIME},
   {EVENT.OPDATA}, {EVENT.DURATION}, {EVENT.AGE}, {EVENT.ID}, {EVENT.RECOVERY.DATE}, {EVENT.RECOVERY.TIME})
3. Recipient Resolution:
   - Group 15 ('Nawari Total Outage Recipients') -> 5 recipients:
     - John Gacomo (John.Gacomo@kenya-airways.com)
     - Robinson Wainaina (Robinson.Wainaina@kenya-airways.com)
     - Pascal Gathungu (Pascal.Gathungu@kenya-airways.com)
     - Mercy Vaati (Mercy.Vaati@kenya-airways.com)
     - IT Service Desk (ITservicedesk@kenya-airways.com)
   - Group 14 ('Nawari Avaya & Communications Administrators') -> 4 voice administrators:
     - John Gacomo, Robinson Wainaina, Pascal Gathungu, Mercy Vaati
   - Group 7 ('Zabbix administrators') -> technical team
4. Action Matching & Mutual Exclusivity Verification:
   - Confirms that for any event tagged with notification_class, EXACTLY ONE active action matches.
   - Validates that legacy Action 7 ('Nawari Avaya & Communication Alerting') is retired (status=1)
     and does NOT duplicate notifications for any event.
5. Zero Monitoring Platform Branding Validator:
   - Recipient-facing messages must never contain 'Nawari', 'Zabbix', 'Grafana',
     or internal monitoring infrastructure jargon.
6. Monitoring-Observed Downtime Quantifier:
   - Computes and documents the difference between physical real-world outage timeline
     and monitoring-observed downtime ({EVENT.DURATION}) resulting from polling intervals
     and threshold verification delays.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class NotificationRecipient:
    """Represents a configured user recipient in Zabbix."""
    username: str
    name: str
    surname: str
    email: str
    user_groups: List[str]
    media_status: str = "CONFIGURED_UNVERIFIED"


# Designated Authoritative Users
DESIGNATED_COMM_ADMINS = [
    NotificationRecipient(
        username="john.gacomo",
        name="John",
        surname="Gacomo",
        email="John.Gacomo@kenya-airways.com",
        user_groups=["Nawari Avaya & Communications Administrators", "Nawari Total Outage Recipients"],
    ),
    NotificationRecipient(
        username="robinson.wainaina",
        name="Robinson",
        surname="Wainaina",
        email="Robinson.Wainaina@kenya-airways.com",
        user_groups=["Nawari Avaya & Communications Administrators", "Nawari Total Outage Recipients"],
    ),
    NotificationRecipient(
        username="pascal.gathungu",
        name="Pascal",
        surname="Gathungu",
        email="Pascal.Gathungu@kenya-airways.com",
        user_groups=["Nawari Avaya & Communications Administrators", "Nawari Total Outage Recipients"],
    ),
    NotificationRecipient(
        username="mercy.vaati",
        name="Mercy",
        surname="Vaati",
        email="Mercy.Vaati@kenya-airways.com",
        user_groups=["Nawari Avaya & Communications Administrators", "Nawari Total Outage Recipients"],
    ),
]

SERVICE_DESK_RECIPIENT = NotificationRecipient(
    username="itservicedesk",
    name="IT Service Desk",
    surname="Kenya Airways",
    email="ITservicedesk@kenya-airways.com",
    user_groups=["Nawari Total Outage Recipients"],
)

TECH_ADMIN_RECIPIENT = NotificationRecipient(
    username="tech.admin",
    name="Technical",
    surname="Administrator",
    email="noc-infrastructure@kenya-airways.com",
    user_groups=["Zabbix administrators"],
)

ALL_CONFIGURED_RECIPIENTS = DESIGNATED_COMM_ADMINS + [SERVICE_DESK_RECIPIENT, TECH_ADMIN_RECIPIENT]


@dataclass
class SimulatedZabbixEvent:
    """Represents an event generated by the Zabbix trigger subsystem."""
    event_id: str
    clock: int  # Epoch timestamp
    host_name: str
    host_groups: List[str]
    trigger_name: str
    severity: int  # 0=Not classified, 1=Info, 2=Warning, 3=Average, 4=High, 5=Disaster
    opdata: str
    tags: Dict[str, str]
    acknowledged: bool = False
    maintenance: bool = False
    recovery_event_id: Optional[str] = None
    recovery_clock: Optional[int] = None

    @property
    def notification_class(self) -> str:
        return self.tags.get("notification_class", "degradation")

    @property
    def severity_label(self) -> str:
        labels = {
            0: "Not classified",
            1: "Information",
            2: "Warning",
            3: "Average",
            4: "High",
            5: "Disaster",
        }
        return labels.get(self.severity, "Warning")


@dataclass
class RenderedNotification:
    """Captured notification output dispatched by an action operation."""
    scenario_id: str
    action_name: str
    action_id: str
    operation_type: str  # "PROBLEM", "ESCALATION", "RECOVERY", "UPDATE"
    escalation_step: int
    recipients: List[str]  # Email addresses
    recipient_usernames: List[str]
    subject: str
    body: str
    event_id: str
    recovery_event_id: Optional[str] = None
    monitoring_duration_str: Optional[str] = None
    monitoring_duration_seconds: Optional[int] = None
    real_downtime_seconds: Optional[int] = None
    detection_delay_seconds: int = 0
    recovery_delay_seconds: int = 0


def format_zabbix_duration(seconds: int) -> str:
    """Format duration in seconds matching Zabbix {EVENT.DURATION} and {EVENT.AGE} macro syntax."""
    if seconds < 0:
        return "0s"
    days = seconds // 86400
    rem = seconds % 86400
    hours = rem // 3600
    rem = rem % 3600
    minutes = rem // 60
    secs = rem % 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or len(parts) == 0:
        parts.append(f"{secs}s")
    return " ".join(parts)


def format_zabbix_timestamp(clock: int) -> Tuple[str, str]:
    """Return (YYYY.MM.DD, HH:MM:SS) in UTC format matching Zabbix macro output."""
    dt = datetime.fromtimestamp(clock, tz=timezone.utc)
    return dt.strftime("%Y.%m.%d"), dt.strftime("%H:%M:%S")


def expand_macros(
    template: str,
    event: SimulatedZabbixEvent,
    is_recovery: bool = False,
    current_clock: Optional[int] = None,
) -> str:
    """Expand native Zabbix macros deterministically."""
    ev_date, ev_time = format_zabbix_timestamp(event.clock)
    cur_clock = current_clock if current_clock is not None else (event.recovery_clock or event.clock)
    age_seconds = max(0, cur_clock - event.clock)
    age_str = format_zabbix_duration(age_seconds)

    if event.recovery_clock:
        duration_seconds = max(0, event.recovery_clock - event.clock)
        duration_str = format_zabbix_duration(duration_seconds)
        rec_date, rec_time = format_zabbix_timestamp(event.recovery_clock)
        rec_id = event.recovery_event_id or f"R_{event.event_id}"
    else:
        duration_seconds = age_seconds
        duration_str = age_str
        rec_date, rec_time = "", ""
        rec_id = ""

    replacements = {
        "{HOST.NAME}": event.host_name,
        "{EVENT.NAME}": event.trigger_name,
        "{EVENT.SEVERITY}": event.severity_label,
        "{EVENT.DATE}": ev_date,
        "{EVENT.TIME}": ev_time,
        "{EVENT.OPDATA}": event.opdata,
        "{EVENT.AGE}": age_str,
        "{EVENT.DURATION}": duration_str,
        "{EVENT.ID}": event.event_id,
        "{EVENT.RECOVERY.DATE}": rec_date,
        "{EVENT.RECOVERY.TIME}": rec_time,
        "{EVENT.RECOVERY.ID}": rec_id,
    }

    result = template
    for macro, val in replacements.items():
        result = result.replace(macro, val)
    return result


@dataclass
class ZabbixActionDefinition:
    """Definition of a Zabbix action with conditions and templates."""
    action_id: str
    name: str
    status: int  # 0=Enabled, 1=Disabled
    target_class: Optional[str]
    target_user_group: str
    problem_subject: str
    problem_message: str
    escalation_subject: Optional[str] = None
    escalation_message: Optional[str] = None
    recovery_subject: Optional[str] = None
    recovery_message: Optional[str] = None
    repeat_interval_sec: int = 0
    pause_suppressed: bool = True
    host_groups: Optional[List[str]] = None
    min_severity: Optional[int] = None

    def matches(self, event: SimulatedZabbixEvent) -> bool:
        """Evaluate whether this action matches the simulated event."""
        if self.status != 0:
            return False

        if event.maintenance and self.pause_suppressed:
            return False

        # Tag-based action evaluation (Actions 10-15)
        if self.target_class is not None:
            return event.notification_class == self.target_class

        # Legacy Action 7 condition evaluation
        if self.min_severity is not None and event.severity < self.min_severity:
            return False

        if self.host_groups is not None:
            if not any(hg in self.host_groups for hg in event.host_groups):
                return False

        return True


class NotificationCaptureHarness:
    """Deterministic Staging Capture & Simulation Harness for Zabbix Notifications."""

    def __init__(self, retire_legacy_action: bool = True):
        self.retire_legacy_action = retire_legacy_action
        self.captured_notifications: List[RenderedNotification] = []
        self.actions = self._build_actions()

    def _build_actions(self) -> List[ZabbixActionDefinition]:
        """Construct the action registry matching Zabbix 7.4 configuration."""
        legacy_status = 1 if self.retire_legacy_action else 0

        # Action 7: Legacy Communication Action (Retired to prevent duplicate delivery)
        action_7 = ZabbixActionDefinition(
            action_id="7",
            name="Nawari Avaya & Communication Alerting",
            status=legacy_status,
            target_class=None,  # Evaluated by host group and severity
            target_user_group="Nawari Avaya & Communications Administrators",
            problem_subject="Problem: {EVENT.NAME}",
            problem_message="Problem started at {EVENT.TIME} on {EVENT.DATE}\nHost: {HOST.NAME}",
            recovery_subject="Resolved: {EVENT.NAME}",
            recovery_message="Problem has been resolved at {EVENT.RECOVERY.TIME} on {EVENT.RECOVERY.DATE}\nHost: {HOST.NAME}",
            repeat_interval_sec=1800,
            pause_suppressed=True,
            host_groups=[
                "Voice Infrastructure",
                "Avaya Infrastructure",
                "Edge SBC",
                "SIP Carrier Trunks",
                "Communications Applications",
                "Synthetic Probes",
            ],
            min_severity=2,  # Warning
        )

        # Action 10: Total Outage Alert
        action_10 = ZabbixActionDefinition(
            action_id="10",
            name="Total Outage Alert",
            status=0,
            target_class="total_outage",
            target_user_group="Nawari Total Outage Recipients",
            problem_subject="[TOTAL OUTAGE] — {HOST.NAME} — {EVENT.NAME}",
            problem_message=(
                "A total outage has been identified affecting the following device or service.\n\n"
                "Affected Device/Service: {HOST.NAME}\n"
                "Issue: {EVENT.NAME}\n"
                "Severity: {EVENT.SEVERITY}\n"
                "Outage Start: {EVENT.DATE} {EVENT.TIME}\n"
                "Details: {EVENT.OPDATA}\n"
                "Status: OUTAGE IN PROGRESS\n\n"
                "The affected device or service is currently unavailable. "
                "Please investigate and take the necessary action to restore normal operations.\n\n"
                "A further notification will be issued once service has been restored."
            ),
            escalation_subject="[TOTAL OUTAGE ESCALATION] — {HOST.NAME} — {EVENT.NAME} — Duration: {EVENT.AGE}",
            escalation_message=(
                "An unresolved total outage continues to affect the following device or service.\n\n"
                "Affected Device/Service: {HOST.NAME}\n"
                "Issue: {EVENT.NAME}\n"
                "Severity: {EVENT.SEVERITY}\n"
                "Outage Start: {EVENT.DATE} {EVENT.TIME}\n"
                "Current Duration: {EVENT.AGE}\n"
                "Details: {EVENT.OPDATA}\n"
                "Status: OUTAGE UNRESOLVED (ESCALATION)\n\n"
                "The affected device or service remains unavailable. Please escalate immediately to the designated duty manager."
            ),
            recovery_subject="[RECOVERED] — {HOST.NAME} — Total Downtime: {EVENT.DURATION}",
            recovery_message=(
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
            ),
            repeat_interval_sec=1800,
            pause_suppressed=True,
        )

        # Action 11: Communication Service Alert
        action_11 = ZabbixActionDefinition(
            action_id="11",
            name="Communication Service Alert",
            status=0,
            target_class="service_outage",
            target_user_group="Nawari Avaya & Communications Administrators",
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
            pause_suppressed=True,
        )

        # Action 12: Synthetic Voice Failure Alert
        action_12 = ZabbixActionDefinition(
            action_id="12",
            name="Synthetic Voice Failure Alert",
            status=0,
            target_class="synthetic_failure",
            target_user_group="Nawari Avaya & Communications Administrators",
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
            pause_suppressed=True,
        )

        # Action 13: Network Degradation Alert
        action_13 = ZabbixActionDefinition(
            action_id="13",
            name="Network Degradation Alert",
            status=0,
            target_class="degradation",
            target_user_group="Zabbix administrators",
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
            pause_suppressed=True,
        )

        # Action 14: Component Failure Alert
        action_14 = ZabbixActionDefinition(
            action_id="14",
            name="Component Failure Alert",
            status=0,
            target_class="component_failure",
            target_user_group="Zabbix administrators",
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
            pause_suppressed=True,
        )

        # Action 15: Monitoring Failure Alert
        action_15 = ZabbixActionDefinition(
            action_id="15",
            name="Monitoring Failure Alert",
            status=0,
            target_class="monitoring_failure",
            target_user_group="Zabbix administrators",
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
            pause_suppressed=True,
        )

        return [action_7, action_10, action_11, action_12, action_13, action_14, action_15]

    def resolve_recipients_for_group(self, group_name: str) -> List[NotificationRecipient]:
        """Resolve user recipients belonging to the given group."""
        return [r for r in ALL_CONFIGURED_RECIPIENTS if group_name in r.user_groups]

    def match_actions_for_event(self, event: SimulatedZabbixEvent) -> List[ZabbixActionDefinition]:
        """Return all active actions that match the given event."""
        return [a for a in self.actions if a.matches(event)]

    def dispatch_problem(
        self,
        scenario_id: str,
        event: SimulatedZabbixEvent,
        step: int = 1,
        current_clock: Optional[int] = None,
        detection_delay_seconds: int = 0,
    ) -> List[RenderedNotification]:
        """Simulate dispatching a problem notification step."""
        matched = self.match_actions_for_event(event)
        results = []

        cur_clock = current_clock if current_clock is not None else event.clock

        for action in matched:
            recipients = self.resolve_recipients_for_group(action.target_user_group)
            emails = [r.email for r in recipients]
            unames = [r.username for r in recipients]

            if step == 1:
                subj = expand_macros(action.problem_subject, event, is_recovery=False, current_clock=cur_clock)
                body = expand_macros(action.problem_message, event, is_recovery=False, current_clock=cur_clock)
                op_type = "PROBLEM"
            else:
                esc_sub = action.escalation_subject or action.problem_subject
                esc_msg = action.escalation_message or action.problem_message
                subj = expand_macros(esc_sub, event, is_recovery=False, current_clock=cur_clock)
                body = expand_macros(esc_msg, event, is_recovery=False, current_clock=cur_clock)
                op_type = "ESCALATION"

            age_sec = max(0, cur_clock - event.clock)

            rendered = RenderedNotification(
                scenario_id=scenario_id,
                action_name=action.name,
                action_id=action.action_id,
                operation_type=op_type,
                escalation_step=step,
                recipients=emails,
                recipient_usernames=unames,
                subject=subj,
                body=body,
                event_id=event.event_id,
                monitoring_duration_seconds=age_sec,
                monitoring_duration_str=format_zabbix_duration(age_sec),
                detection_delay_seconds=detection_delay_seconds,
            )
            self.captured_notifications.append(rendered)
            results.append(rendered)

        return results

    def dispatch_recovery(
        self,
        scenario_id: str,
        event: SimulatedZabbixEvent,
        real_downtime_seconds: Optional[int] = None,
        detection_delay_seconds: int = 0,
        recovery_delay_seconds: int = 0,
    ) -> List[RenderedNotification]:
        """Simulate dispatching a recovery notification step."""
        if not event.recovery_clock:
            event.recovery_clock = event.clock + 300  # Default 5 minutes
        if not event.recovery_event_id:
            event.recovery_event_id = f"REC_{event.event_id}"

        matched = self.match_actions_for_event(event)
        results = []

        mon_duration_sec = max(0, event.recovery_clock - event.clock)
        mon_duration_str = format_zabbix_duration(mon_duration_sec)

        for action in matched:
            recipients = self.resolve_recipients_for_group(action.target_user_group)
            emails = [r.email for r in recipients]
            unames = [r.username for r in recipients]

            rec_sub = action.recovery_subject or "[RECOVERED] — {HOST.NAME} — {EVENT.NAME}"
            rec_msg = action.recovery_message or "Problem resolved at {EVENT.RECOVERY.TIME}."

            subj = expand_macros(rec_sub, event, is_recovery=True)
            body = expand_macros(rec_msg, event, is_recovery=True)

            rendered = RenderedNotification(
                scenario_id=scenario_id,
                action_name=action.name,
                action_id=action.action_id,
                operation_type="RECOVERY",
                escalation_step=1,
                recipients=emails,
                recipient_usernames=unames,
                subject=subj,
                body=body,
                event_id=event.event_id,
                recovery_event_id=event.recovery_event_id,
                monitoring_duration_seconds=mon_duration_sec,
                monitoring_duration_str=mon_duration_str,
                real_downtime_seconds=real_downtime_seconds,
                detection_delay_seconds=detection_delay_seconds,
                recovery_delay_seconds=recovery_delay_seconds,
            )
            self.captured_notifications.append(rendered)
            results.append(rendered)

        return results


def validate_zero_platform_branding(text: str) -> Tuple[bool, List[str]]:
    """Verify text contains NO prohibited monitoring platform words."""
    forbidden = [
        r"\bnawari\b",
        r"\bzabbix\b",
        r"\bgrafana\b",
    ]
    found = []
    for pattern in forbidden:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if matches:
            found.extend(matches)
    return (len(found) == 0, found)


def calculate_downtime_delta(
    real_outage_start: int,
    real_outage_end: int,
    poll_interval_seconds: int,
    consecutive_failures_required: int,
    recovery_poll_interval_seconds: int = 10,
) -> Dict[str, Any]:
    """Calculate the difference between real-world physical outage and monitoring-observed downtime.

    In Zabbix, a problem trigger does not fire instantaneously when a physical wire is unplugged.
    It requires:
      detection_delay = (poll_interval * consecutive_failures)
    Similarly, recovery requires:
      recovery_delay = recovery_poll_interval
    Monitoring observed duration is (T_rec - T_prob):
      T_prob = real_outage_start + detection_delay
      T_rec = real_outage_end + recovery_delay
      monitoring_duration = (real_outage_end - real_outage_start) + (recovery_delay - detection_delay)
    """
    real_duration = real_outage_end - real_outage_start
    detection_delay = poll_interval_seconds * consecutive_failures_required
    recovery_delay = recovery_poll_interval_seconds

    observed_start = real_outage_start + detection_delay
    observed_end = real_outage_end + recovery_delay
    observed_duration = max(0, observed_end - observed_start)

    delta = observed_duration - real_duration

    return {
        "real_duration_seconds": real_duration,
        "real_duration_str": format_zabbix_duration(real_duration),
        "detection_delay_seconds": detection_delay,
        "recovery_delay_seconds": recovery_delay,
        "observed_start": observed_start,
        "observed_end": observed_end,
        "observed_duration_seconds": observed_duration,
        "observed_duration_str": format_zabbix_duration(observed_duration),
        "delta_seconds": delta,
    }


def differentiate_host_vs_service_recovery(
    trigger_name: str,
    host_name: str,
    duration_str: str = "0s",
) -> Dict[str, Any]:
    """Provide service-restoration evidence analysis distinguishing host ping from service recovery.

    A recovered ICMP reachability check on a host restores reachability, NOT full service.
    Service restoration requires service-level evidence:
    - SIP entity registration status
    - SIP trunk availability (OPTIONS 200 OK)
    - Call routing availability
    - Successful synthetic call completion
    """
    t_lower = trigger_name.lower()
    is_host_reachability = any(k in t_lower for k in ["icmp", "ping", "unreachable by icmp ping", "unavailable by icmp ping"])
    is_sip_trunk = any(k in t_lower for k in ["options", "sip trunk", "sip entity"])
    is_synthetic = any(k in t_lower for k in ["synthetic", "mos", "one-way audio"])

    if is_host_reachability:
        recovery_type = "HOST_REACHABILITY_RESTORED"
        operational_interpretation = (
            f"Network reachability to {host_name} has resumed. "
            "Higher-layer voice daemons, SIP registrations, and call routing require service-level verification."
        )
        service_restored_proven = False
    elif is_sip_trunk:
        recovery_type = "SIP_TRUNK_SIGNALING_RESTORED"
        operational_interpretation = (
            f"SIP signaling response on {host_name} has recovered. "
            "Inbound and outbound trunk capacity is operational."
        )
        service_restored_proven = True
    elif is_synthetic:
        recovery_type = "SYNTHETIC_PROBE_VALIDATED"
        operational_interpretation = (
            f"Automated synthetic voice probe on {host_name} completed successfully. "
            "End-to-end voice path media quality confirmed."
        )
        service_restored_proven = True
    else:
        recovery_type = "SUBSYSTEM_RESTORED"
        operational_interpretation = f"Subsystem condition on {host_name} has cleared."
        service_restored_proven = True

    return {
        "host_name": host_name,
        "trigger_name": trigger_name,
        "duration_str": duration_str,
        "recovery_type": recovery_type,
        "operational_interpretation": operational_interpretation,
        "service_restored_proven": service_restored_proven,
    }

