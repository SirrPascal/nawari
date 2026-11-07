"""
Nawari Phase 8 — Endpoint Enrollment & Device Trust Lifecycle (Workstream 8C)
Manages one-time provisioning tokens, cryptographic HMAC token binding,
authoritative server-side provenance validation, and certificate/token revocation.
"""

from __future__ import annotations

import hmac
import hashlib
import ipaddress
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Dict


@dataclass
class EnrollmentToken:
    token: str
    issuer: str
    expires_at: float
    one_time: bool = True
    is_used: bool = False
    allowed_cidrs: list[str] = field(default_factory=list)


@dataclass
class EndpointCredential:
    endpoint_id: str
    hostname: str
    mac_address: str
    issued_at: float
    expires_at: float
    secret_hash: str
    provenance: str
    is_revoked: bool = False
    revocation_reason: Optional[str] = None
    revoked_at: Optional[float] = None


class EnrollmentError(Exception):
    pass


class RevocationError(Exception):
    pass


class EnrollmentManager:
    def __init__(self, hmac_signing_secret: Optional[str] = None):
        self._secret = (hmac_signing_secret or secrets.token_hex(32)).encode("utf-8")
        self._enrollment_tokens: Dict[str, EnrollmentToken] = {}
        self._registered_endpoints: Dict[str, EndpointCredential] = {}
        self._revocation_list: Dict[str, dict] = {}

    def generate_provisioning_token(
        self,
        issuer: str,
        expires_in_hours: int = 24,
        one_time: bool = True,
        allowed_cidrs: Optional[list[str]] = None,
    ) -> str:
        token = f"nawari-enroll-{secrets.token_urlsafe(32)}"
        exp = time.time() + (expires_in_hours * 3600)
        self._enrollment_tokens[token] = EnrollmentToken(
            token=token,
            issuer=issuer,
            expires_at=exp,
            one_time=one_time,
            allowed_cidrs=allowed_cidrs or [],
        )
        return token

    def determine_provenance(self, client_ip: str) -> str:
        """
        Server-side authoritative provenance determination.
        Client cannot self-assert provenance.
        """
        try:
            ip_obj = ipaddress.ip_address(client_ip)
            if ip_obj.is_loopback:
                return "LOCAL_DEVELOPMENT"
            
            # Kenya Airways Production Subnets (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
            if ip_obj.is_private:
                return "PHYSICAL_PRODUCTION"
            return "EXTERNAL_REMOTE"
        except ValueError:
            return "UNKNOWN_PROVENANCE"

    def register_endpoint(
        self,
        enrollment_token: str,
        hostname: str,
        mac_address: str,
        client_ip: str,
        requested_endpoint_id: Optional[str] = None,
    ) -> dict:
        now = time.time()

        # 1. Validate Enrollment Token
        token_meta = self._enrollment_tokens.get(enrollment_token)
        if not token_meta:
            raise EnrollmentError("Invalid or unknown enrollment token.")
        if token_meta.is_used and token_meta.one_time:
            raise EnrollmentError("Enrollment token has already been consumed.")
        if now > token_meta.expires_at:
            raise EnrollmentError("Enrollment token has expired.")

        # Validate CIDR restriction if present
        if token_meta.allowed_cidrs:
            client_ip_obj = ipaddress.ip_address(client_ip)
            if not any(client_ip_obj in ipaddress.ip_network(cidr) for cidr in token_meta.allowed_cidrs):
                raise EnrollmentError(f"Client IP {client_ip} is outside allowed provisioning subnets.")

        # 2. Generate Identity & Credentials
        endpoint_id = requested_endpoint_id or str(uuid.uuid4())
        raw_secret_token = f"nawari-agent-{secrets.token_urlsafe(32)}"
        
        # Hash secret token with HMAC
        secret_hash = hmac.new(self._secret, raw_secret_token.encode("utf-8"), hashlib.sha256).hexdigest()
        
        # 3. Determine Authoritative Provenance Server-Side
        authoritative_provenance = self.determine_provenance(client_ip)

        # 90-day validity
        expires_at = now + (90 * 86400)

        cred = EndpointCredential(
            endpoint_id=endpoint_id,
            hostname=hostname,
            mac_address=mac_address,
            issued_at=now,
            expires_at=expires_at,
            secret_hash=secret_hash,
            provenance=authoritative_provenance,
        )
        self._registered_endpoints[endpoint_id] = cred

        # Mark token as used if one_time
        if token_meta.one_time:
            token_meta.is_used = True

        return {
            "endpoint_id": endpoint_id,
            "secret_token": raw_secret_token,
            "provenance": authoritative_provenance,
            "expires_at": expires_at,
        }

    def validate_endpoint_token(self, endpoint_id: str, secret_token: str) -> bool:
        if self.is_revoked(endpoint_id):
            return False

        cred = self._registered_endpoints.get(endpoint_id)
        if not cred:
            return False

        if time.time() > cred.expires_at:
            return False

        expected_hash = hmac.new(self._secret, secret_token.encode("utf-8"), hashlib.sha256).hexdigest()
        return secrets.compare_digest(expected_hash, cred.secret_hash)

    def revoke_endpoint(self, endpoint_id: str, reason: str, actor: str) -> bool:
        if endpoint_id not in self._registered_endpoints:
            raise RevocationError(f"Cannot revoke unknown endpoint ID: {endpoint_id}")

        cred = self._registered_endpoints[endpoint_id]
        cred.is_revoked = True
        cred.revocation_reason = reason
        cred.revoked_at = time.time()

        self._revocation_list[endpoint_id] = {
            "endpoint_id": endpoint_id,
            "reason": reason,
            "actor": actor,
            "revoked_at": cred.revoked_at,
        }
        return True

    def is_revoked(self, endpoint_id: str) -> bool:
        return endpoint_id in self._revocation_list
