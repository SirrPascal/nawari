"""Multi-Leg Call Lifecycle Correlator across SIP, Asterisk AMI, and Avaya Aura."""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from services.voice.correlation.cause_codes import CauseCodeTranslator
from services.voice.correlation.privacy import mask_phone_number
from services.voice.sip.ladder import SIPCallLadder


@dataclass
class CallLeg:
    leg_id: str
    protocol: str  # SIP, AMI, AVAYA_SBC, AVAYA_SM
    source_entity: str
    destination_entity: str
    start_time: float
    end_time: Optional[float] = None
    status: str = "ESTABLISHED"
    call_id: Optional[str] = None
    uniqueid: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CorrelatedCallSession:
    session_id: str
    caller_masked: str
    callee_masked: str
    creation_time: float
    sip_call_id: Optional[str] = None
    asterisk_uniqueid: Optional[str] = None
    asterisk_linkedid: Optional[str] = None
    avaya_session_id: Optional[str] = None
    answer_time: Optional[float] = None
    termination_time: Optional[float] = None
    final_sip_code: Optional[int] = None
    q850_cause: Optional[int] = None
    termination_category: str = "ACTIVE"
    diagnostic_summary: Optional[str] = None
    is_operational_failure: bool = False
    legs: list[CallLeg] = field(default_factory=list)
    ladder: Optional[SIPCallLadder] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.answer_time and self.termination_time:
            return round(self.termination_time - self.answer_time, 2)
        elif self.termination_time:
            return round(self.termination_time - self.creation_time, 2)
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "caller": self.caller_masked,
            "callee": self.callee_masked,
            "sip_call_id": self.sip_call_id,
            "asterisk_uniqueid": self.asterisk_uniqueid,
            "avaya_session_id": self.avaya_session_id,
            "creation_time": self.creation_time,
            "duration_seconds": self.duration_seconds,
            "final_sip_code": self.final_sip_code,
            "q850_cause": self.q850_cause,
            "termination_category": self.termination_category,
            "diagnostic_summary": self.diagnostic_summary,
            "is_operational_failure": self.is_operational_failure,
            "total_legs": len(self.legs),
            "legs": [l.to_dict() for l in self.legs],
        }


class SessionCorrelator:
    """Binds SIP Call-ID, Asterisk AMI Uniqueid, and Avaya Session identifiers into cohesive sessions."""

    def __init__(self) -> None:
        self.sessions: dict[str, CorrelatedCallSession] = {}
        self._sip_map: dict[str, str] = {}       # sip_call_id -> session_id
        self._ami_map: dict[str, str] = {}       # asterisk_uniqueid -> session_id
        self._avaya_map: dict[str, str] = {}     # avaya_session_id -> session_id

    def get_or_create_session(
        self,
        sip_call_id: Optional[str] = None,
        asterisk_uniqueid: Optional[str] = None,
        avaya_session_id: Optional[str] = None,
        caller: Optional[str] = None,
        callee: Optional[str] = None,
        start_time: Optional[float] = None,
    ) -> CorrelatedCallSession:
        """Find an existing call session by any matching identifier or initialize a new correlated session."""
        session_id = None
        if sip_call_id and sip_call_id in self._sip_map:
            session_id = self._sip_map[sip_call_id]
        elif asterisk_uniqueid and asterisk_uniqueid in self._ami_map:
            session_id = self._ami_map[asterisk_uniqueid]
        elif avaya_session_id and avaya_session_id in self._avaya_map:
            session_id = self._avaya_map[avaya_session_id]

        if session_id and session_id in self.sessions:
            sess = self.sessions[session_id]
            # Bind any new identifiers
            if sip_call_id and not sess.sip_call_id:
                sess.sip_call_id = sip_call_id
                self._sip_map[sip_call_id] = sess.session_id
            if asterisk_uniqueid and not sess.asterisk_uniqueid:
                sess.asterisk_uniqueid = asterisk_uniqueid
                self._ami_map[asterisk_uniqueid] = sess.session_id
            if avaya_session_id and not sess.avaya_session_id:
                sess.avaya_session_id = avaya_session_id
                self._avaya_map[avaya_session_id] = sess.session_id
            return sess

        # Create new session
        t = start_time if start_time is not None else time.time()
        seed = f"{sip_call_id or ''}:{asterisk_uniqueid or ''}:{avaya_session_id or ''}:{t}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        new_session_id = f"sess-{digest}"

        sess = CorrelatedCallSession(
            session_id=new_session_id,
            caller_masked=mask_phone_number(caller),
            callee_masked=mask_phone_number(callee),
            creation_time=t,
            sip_call_id=sip_call_id,
            asterisk_uniqueid=asterisk_uniqueid,
            avaya_session_id=avaya_session_id,
            ladder=SIPCallLadder(call_id=sip_call_id or new_session_id),
        )

        self.sessions[new_session_id] = sess
        if sip_call_id:
            self._sip_map[sip_call_id] = new_session_id
        if asterisk_uniqueid:
            self._ami_map[asterisk_uniqueid] = new_session_id
        if avaya_session_id:
            self._avaya_map[avaya_session_id] = new_session_id

        return sess

    def add_call_leg(
        self,
        session_id: str,
        leg_id: str,
        protocol: str,
        source_entity: str,
        destination_entity: str,
        start_time: Optional[float] = None,
    ) -> CallLeg:
        sess = self.sessions.get(session_id)
        if not sess:
            raise KeyError(f"Session {session_id} not found")

        leg = CallLeg(
            leg_id=leg_id,
            protocol=protocol,
            source_entity=source_entity,
            destination_entity=destination_entity,
            start_time=start_time or time.time(),
            call_id=sess.sip_call_id,
            uniqueid=sess.asterisk_uniqueid,
        )
        sess.legs.append(leg)
        return leg

    def terminate_session(
        self,
        session_id: str,
        final_sip_code: Optional[int] = None,
        reason_header: Optional[str] = None,
        warning_header: Optional[str] = None,
        end_time: Optional[float] = None,
    ) -> CorrelatedCallSession:
        sess = self.sessions.get(session_id)
        if not sess:
            raise KeyError(f"Session {session_id} not found")

        sess.termination_time = end_time or time.time()
        sess.final_sip_code = final_sip_code

        cls_res = CauseCodeTranslator.classify_call_termination(
            final_sip_code, reason_header=reason_header, warning_header=warning_header
        )
        sess.termination_category = cls_res["category"]
        sess.is_operational_failure = cls_res["is_infrastructure_failure"]
        sess.diagnostic_summary = cls_res["diagnostic_summary"]

        if "reason_info" in cls_res:
            sess.q850_cause = cls_res["reason_info"].get("cause_code")

        # Mark legs completed
        for leg in sess.legs:
            if not leg.end_time:
                leg.end_time = sess.termination_time
                leg.status = "TERMINATED"

        return sess

