"""Unit tests for Multi-Channel Notification Router and ITSM Adapter (Workstream 13C)."""

import os
import tempfile
import pytest

from services.multisite.notifications import (
    DeliveryStatus,
    NotificationChannel,
    NotificationMessage,
    NotificationRouter,
)


def test_multichannel_notification_dispatch_p1_and_p3():
    router = NotificationRouter(is_production_mode=False)

    # 1. P1 Incident dispatches Email + SMS + ServiceNow ITSM
    p1_incident = {
        "incident_id": "INC-TEST-P1",
        "title": "Core Datacenter Switch Offline",
        "severity": "P1_CRITICAL",
        "station_id": "JKIA-HUB",
        "service_id": "SVC-DCS-GLOBAL",
        "status": "DETECTED",
        "created_at": "2026-11-08T09:00:00Z",
    }
    msgs_p1 = router.dispatch_incident_notifications(p1_incident)
    channels_p1 = {m.channel for m in msgs_p1}
    assert NotificationChannel.SMTP_EMAIL in channels_p1
    assert NotificationChannel.SMS in channels_p1
    assert NotificationChannel.SERVICENOW_ITSM in channels_p1
    assert all(m.status == DeliveryStatus.DELIVERED for m in msgs_p1)
    
    # Verify ServiceNow ticket record created
    ticket = router.get_itsm_ticket("INC-TEST-P1")
    assert ticket is not None
    assert ticket["urgency"] == "1 - High"

    # 2. P3 Incident dispatches Email + ServiceNow, but NO SMS
    p3_incident = {
        "incident_id": "INC-TEST-P3",
        "title": "Redundant Interface Down",
        "severity": "P3_MEDIUM",
        "station_id": "MBA-STATION",
        "service_id": "SVC-CORP-ERP",
        "status": "DETECTED",
        "created_at": "2026-11-08T09:00:00Z",
    }
    msgs_p3 = router.dispatch_incident_notifications(p3_incident)
    channels_p3 = {m.channel for m in msgs_p3}
    assert NotificationChannel.SMTP_EMAIL in channels_p3
    assert NotificationChannel.SERVICENOW_ITSM in channels_p3
    assert NotificationChannel.SMS not in channels_p3  # P3 does not page SMS


def test_carrier_failure_retries_and_dead_letter_queue():
    # Simulate network failures on SMS
    router = NotificationRouter(is_production_mode=False, simulate_network_failures=True)

    incident = {
        "incident_id": "INC-SMS-FAIL",
        "title": "PBX Trunk Link Down",
        "severity": "P1_CRITICAL",
        "station_id": "JKIA-HUB",
    }
    msgs = router.dispatch_incident_notifications(incident)
    sms_msg = next(m for m in msgs if m.channel == NotificationChannel.SMS)
    assert sms_msg.status == DeliveryStatus.FAILED
    assert sms_msg.retry_count == 1

    # Retry 1: still fails (retry_count = 2)
    router.retry_failed_messages()
    assert sms_msg.retry_count == 2
    assert sms_msg.status == DeliveryStatus.FAILED

    # Retry 2: reaches max_retries (3) -> enters DEAD_LETTER queue
    router.retry_failed_messages()
    assert sms_msg.status == DeliveryStatus.DEAD_LETTER
    assert len(router.get_dead_letter_queue()) == 1

    # Requeue recovery from DLQ
    requeued = router.requeue_dead_letter(sms_msg.message_id)
    assert requeued is True
    assert len(router.get_dead_letter_queue()) == 0

    # Fix carrier network issue and retry
    router.simulate_network_failures = False
    router.retry_failed_messages()
    # Should now be delivered
    assert sms_msg.status == DeliveryStatus.DELIVERED


def test_servicenow_timeout_and_reconnection():
    router = NotificationRouter(is_production_mode=False, simulate_itsm_timeout=True)

    incident = {
        "incident_id": "INC-ITSM-TIMEOUT",
        "title": "DCS Check-in Terminal Gateway Failure",
        "severity": "P2_HIGH",
        "station_id": "MBA-STATION",
    }
    msgs = router.dispatch_incident_notifications(incident)
    itsm_msg = next(m for m in msgs if m.channel == NotificationChannel.SERVICENOW_ITSM)
    assert itsm_msg.status == DeliveryStatus.FAILED
    assert "SERVICENOW_TIMEOUT" in str(itsm_msg.last_error)

    # Reconnection: Service restored, retry delivery
    router.simulate_itsm_timeout = False
    router.retry_failed_messages()
    assert itsm_msg.status == DeliveryStatus.DELIVERED


def test_durable_spool_queue_survives_process_restart():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        spool_path = tf.name

    try:
        # 1. Process 1: Dispatches notifications and persists queue
        router1 = NotificationRouter(spool_file_path=spool_path, simulate_network_failures=True)
        incident = {
            "incident_id": "INC-DURABLE",
            "title": "WAN Flap Incident",
            "severity": "P1_CRITICAL",
            "station_id": "JKIA-HUB",
        }
        router1.dispatch_incident_notifications(incident)
        outbox1 = router1.get_outbox()
        assert len(outbox1) >= 3

        # 2. Simulate Process Restart: instantiate brand new router loading same spool file
        router2 = NotificationRouter(spool_file_path=spool_path)
        outbox2 = router2.get_outbox()
        assert len(outbox2) == len(outbox1)
        inc_ids = {m.incident_id for m in outbox2}
        assert "INC-DURABLE" in inc_ids
    finally:
        if os.path.exists(spool_path):
            os.remove(spool_path)

