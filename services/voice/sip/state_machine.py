"""RFC 3261 SIP Transaction State Machine and Latency Dissection Engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from services.voice.sip.parser import SIPMessage, SIPMessageType, SIPMethod


class TransactionState(str, Enum):
    # Client states
    CALLING = "CALLING"
    TRYING = "TRYING"
    PROCEEDING = "PROCEEDING"
    COMPLETED = "COMPLETED"
    CONFIRMED = "CONFIRMED"
    TERMINATED = "TERMINATED"


@dataclass
class SIPTransaction:
    transaction_id: str
    method: str
    is_invite: bool
    is_client: bool = True
    state: TransactionState = TransactionState.CALLING
    creation_time: float = field(default_factory=time.time)
    first_18x_time: Optional[float] = None
    alerting_180_time: Optional[float] = None
    answer_200_time: Optional[float] = None
    termination_time: Optional[float] = None
    final_response_code: Optional[int] = None
    final_response_reason: Optional[str] = None
    retransmissions_count: int = 0
    messages: list[SIPMessage] = field(default_factory=list)

    @property
    def post_dial_delay_ms(self) -> Optional[float]:
        """Post-Dial Delay (PDD): Time from initial INVITE until first provisional 18x progress/ringing."""
        if self.first_18x_time is not None:
            return round((self.first_18x_time - self.creation_time) * 1000.0, 2)
        return None

    @property
    def time_to_alerting_ms(self) -> Optional[float]:
        """Time to Alerting (TTA): Time from initial INVITE until station reports 180 Ringing."""
        if self.alerting_180_time is not None:
            return round((self.alerting_180_time - self.creation_time) * 1000.0, 2)
        return None

    @property
    def time_to_answer_ms(self) -> Optional[float]:
        """Time to Answer (TTOA): Time from alerting (180) until call is answered (200 OK)."""
        if self.answer_200_time is not None and self.alerting_180_time is not None:
            return round((self.answer_200_time - self.alerting_180_time) * 1000.0, 2)
        elif self.answer_200_time is not None:
            return round((self.answer_200_time - self.creation_time) * 1000.0, 2)
        return None

    @property
    def teardown_duration_ms(self) -> Optional[float]:
        """Teardown duration: From BYE request until final 200 OK response."""
        if not self.is_invite and self.method == "BYE" and self.termination_time:
            return round((self.termination_time - self.creation_time) * 1000.0, 2)
        return None

    def process_message(self, msg: SIPMessage, event_time: Optional[float] = None) -> None:
        """Process incoming/outgoing SIP message and update transaction state & latencies."""
        t = event_time if event_time is not None else time.time()
        self.messages.append(msg)

        if msg.message_type == SIPMessageType.REQUEST:
            if msg.method == self.method and len(self.messages) > 1:
                self.retransmissions_count += 1
            return

        # Handle Responses
        status = msg.status_code
        if not status:
            return

        if 100 <= status < 200:
            if status == 100 and self.state == TransactionState.CALLING:
                self.state = TransactionState.PROCEEDING
            elif 180 <= status <= 183:
                self.state = TransactionState.PROCEEDING
                if self.first_18x_time is None:
                    self.first_18x_time = t
                if status == 180 and self.alerting_180_time is None:
                    self.alerting_180_time = t

        elif 200 <= status < 300:
            self.final_response_code = status
            self.final_response_reason = msg.reason_phrase
            if self.is_invite:
                self.answer_200_time = t
                self.state = TransactionState.TERMINATED
                self.termination_time = t
            else:
                self.state = TransactionState.COMPLETED
                self.termination_time = t

        elif 300 <= status < 700:
            self.final_response_code = status
            self.final_response_reason = msg.reason_phrase
            self.state = TransactionState.COMPLETED
            self.termination_time = t

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "method": self.method,
            "is_invite": self.is_invite,
            "state": self.state.value,
            "final_response_code": self.final_response_code,
            "final_response_reason": self.final_response_reason,
            "post_dial_delay_ms": self.post_dial_delay_ms,
            "time_to_alerting_ms": self.time_to_alerting_ms,
            "time_to_answer_ms": self.time_to_answer_ms,
            "retransmissions_count": self.retransmissions_count,
            "total_messages": len(self.messages),
        }

