"""Role-Based Access Control (RBAC), Authentication, and API Key Manager for Nawari.

Enforces role-based permissions (admin, operator, viewer, auditor, collector)
with cryptographic password hashing and tenant scoping.
"""

from __future__ import annotations
import hashlib
import hmac
import os
import secrets
import time
import uuid
from typing import Dict, Any, List, Optional


ROLE_PERMISSIONS = {
    "admin": {"read", "write", "configure", "acknowledge", "dispatch", "audit", "dr_manage"},
    "operator": {"read", "write", "acknowledge", "dispatch"},
    "viewer": {"read"},
    "auditor": {"read", "audit"},
    "collector": {"ingest"},
}


class RBACSecurityManager:
    """Manages user authentication, token sessions, and RBAC authorization checks."""

    def __init__(self, store):
        self.store = store

    @staticmethod
    def hash_password(password: str, salt: Optional[str] = None) -> str:
        """Hash password using PBKDF2-HMAC-SHA256 with cryptographic salt."""
        s = salt or secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), s.encode("utf-8"), 100000).hex()
        return f"{s}:{pwd_hash}"

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        try:
            salt, stored_hash = hashed.split(":", 1)
            candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
            return hmac.compare_digest(stored_hash, candidate)
        except Exception:
            return False

    def create_user(self, username: str, password: str, role: str, tenant: str = "default") -> Dict[str, Any]:
        if role not in ROLE_PERMISSIONS:
            raise ValueError(f"Invalid role '{role}'. Must be one of {list(ROLE_PERMISSIONS.keys())}")
        
        user_id = f"user-{uuid.uuid4().hex[:8]}"
        hashed = self.hash_password(password)
        now = time.time()

        with self.store.db.transaction() as session:
            session.execute(
                """
                INSERT INTO rbac_users (user_id, username, password_hash, role, tenant, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, TRUE, ?)
                """,
                (user_id, username, hashed, role, tenant, now),
            )
        return {"user_id": user_id, "username": username, "role": role, "tenant": tenant}

    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        with self.store.db.transaction() as session:
            user = session.first("SELECT * FROM rbac_users WHERE username = ? AND is_active = TRUE", (username,))
            if not user:
                return None
            
            if self.verify_password(password, user["password_hash"]):
                now = time.time()
                session.execute("UPDATE rbac_users SET last_login_at = ? WHERE user_id = ?", (now, user["user_id"]))
                # Generate bearer token
                token = f"nwt-{secrets.token_hex(24)}"
                return {
                    "user_id": user["user_id"],
                    "username": user["username"],
                    "role": user["role"],
                    "tenant": user["tenant"],
                    "token": token,
                    "permissions": list(ROLE_PERMISSIONS.get(user["role"], set())),
                }
            return None

    def authorize(self, role: str, required_permission: str) -> bool:
        allowed = ROLE_PERMISSIONS.get(role, set())
        return required_permission in allowed

    def create_api_key(self, name: str, owner_id: str, role: str = "collector", tenant: str = "default", expiry_days: int = 90) -> Dict[str, Any]:
        raw_key = f"nwk_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        key_id = f"key-{uuid.uuid4().hex[:8]}"
        now = time.time()
        expires_at = now + (expiry_days * 86400.0)

        with self.store.db.transaction() as session:
            session.execute(
                """
                INSERT INTO api_keys (key_id, key_hash, name, owner_id, role, tenant, expires_at, is_revoked, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, FALSE, ?)
                """,
                (key_id, key_hash, name, owner_id, role, tenant, expires_at, now),
            )

        return {
            "key_id": key_id,
            "raw_api_key": raw_key,
            "name": name,
            "role": role,
            "expires_at": expires_at,
        }

    def verify_api_key(self, raw_key: str) -> Optional[Dict[str, Any]]:
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        now = time.time()
        with self.store.db.transaction() as session:
            row = session.first(
                "SELECT * FROM api_keys WHERE key_hash = ? AND is_revoked = FALSE AND expires_at > ?",
                (key_hash, now),
            )
            return dict(row) if row else None

    @classmethod
    def map_entra_id_claims_to_role(cls, claims: Dict[str, Any]) -> str:
        """Maps Microsoft Entra ID (Azure AD) OIDC token claims to Nawari RBAC roles.
        
        Evaluates 'roles', 'groups', and directory claims in strict order of privilege:
        - Admin group/role -> 'admin'
        - Operator / Network / Voice engineer -> 'operator'
        - Security auditor / compliance -> 'auditor'
        - Default fallback -> 'viewer'
        """
        user_roles = [str(r).lower() for r in claims.get("roles", [])]
        user_groups = [str(g).lower() for g in claims.get("groups", [])]
        combined = set(user_roles + user_groups)

        if any(r in combined for r in ("nawari.admin", "global.admin", "network.admin")):
            return "admin"
        if any(r in combined for r in ("nawari.operator", "network.engineer", "voice.engineer", "telecom.operator")):
            return "operator"
        if any(r in combined for r in ("nawari.auditor", "security.auditor", "compliance.officer")):
            return "auditor"
        return "viewer"

    @classmethod
    def validate_entra_id_token_structure(
        cls,
        token_claims: Dict[str, Any],
        expected_audience: Optional[str] = None,
        expected_issuer: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validates structure and standard temporal claims of an Entra ID OIDC token payload."""
        now = time.time()
        # Verify required standard claims
        if not token_claims.get("sub") and not token_claims.get("oid"):
            raise ValueError("Token missing required subject or object identifier ('sub'/'oid')")
        
        exp = token_claims.get("exp")
        if exp is not None and float(exp) < now:
            raise ValueError("Token expired")
            
        nbf = token_claims.get("nbf")
        if nbf is not None and float(nbf) > (now + 300):  # 5 min clock skew allowance
            raise ValueError("Token not yet valid")

        if expected_audience and token_claims.get("aud") != expected_audience:
            raise ValueError(f"Invalid audience '{token_claims.get('aud')}', expected '{expected_audience}'")

        if expected_issuer and token_claims.get("iss") != expected_issuer:
            raise ValueError(f"Invalid issuer '{token_claims.get('iss')}', expected '{expected_issuer}'")

        assigned_role = cls.map_entra_id_claims_to_role(token_claims)
        user_email = token_claims.get("preferred_username") or token_claims.get("email") or token_claims.get("upn") or token_claims.get("sub")

        return {
            "valid": True,
            "principal_id": token_claims.get("oid") or token_claims.get("sub"),
            "username": user_email,
            "tenant_id": token_claims.get("tid"),
            "assigned_role": assigned_role,
            "permissions": list(ROLE_PERMISSIONS.get(assigned_role, set())),
        }

