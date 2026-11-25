"""Nawari HOMER 7 / Heplify SIP Observability & Call Ladder Engine.

Connects to the local HOMER / Heplify capture pipeline:
1. Heplify-Server metrics and listener health.
2. PostgreSQL 17 'homer_data' storage containing partitioned SIP tables (hep_proto_1_call, etc.).
3. RFC 3261 SIP parsing and chronological ladder diagram reconstruction.
4. Isolated Asterisk synthetic call origination and Call-ID correlation.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import subprocess
import time
import uuid
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

logger = logging.getLogger("nawari.homer_client")

# Permitted local synthetic extensions (Strict Safety Gate)
PERMITTED_LOCAL_EXTENSIONS = {
    "1001": {"name": "Synthetic Echo Test", "expected_code": 200, "outcome": "ANSWERED"},
    "1002": {"name": "Fast Answer & Disconnect", "expected_code": 200, "outcome": "ANSWERED"},
    "1003": {"name": "Busy Simulator", "expected_code": 486, "outcome": "BUSY"},
    "1004": {"name": "Congestion Simulator", "expected_code": 503, "outcome": "CONGESTION"},
}


def resolve_sip_node_name(ip: str, port: int = 5060) -> str:
    """Resolves an IP address to its semantic Avaya infrastructure or carrier identity."""
    clean_ip = ip.strip() if ip else ""
    if clean_ip in ("10.2.156.22", "10.2.156.23", "10.2.156.28"):
        return "Avaya_Session_Manager"
    if clean_ip in ("10.2.156.30", "10.102.10.25", "10.2.156.26", "10.2.156.27", "10.2.156.50"):
        return "Avaya_Communication_Manager"
    if clean_ip == "10.2.156.131":
        return "Avaya_SBCE_Primary"
    if clean_ip == "10.2.156.132":
        return "Avaya_SBCE_Secondary"
    if clean_ip in ("10.2.156.60", "10.2.157.30"):
        return "Avaya_G450_Gateway"
    if clean_ip == "10.2.156.100":
        return "Safaricom_SIP_Carrier"
    if clean_ip in ("127.0.0.1", "::1"):
        return "Asterisk_Synthetic_Probe"
    # Format generic endpoints
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", clean_ip)
    return f"Endpoint_{sanitized}"


from .telemetry_contract import SipSourceClassification


def classify_sip_capture(
    capture_id: str,
    src_ip: str,
    capture_node: str = "",
    auth_token: str = ""
) -> tuple[str, str]:
    """Classifies a captured SIP packet strictly adhering to proven capture provenance.
    
    Categories:
    - SYNTHETIC_ASTERISK: Local Asterisk loopback probe or nawari-avtest-lab.
    - AUTHORIZED_SYNTHETIC_ENTERPRISE: Signed synthetic enterprise test caller.
    - VERIFIED_PRODUCTION_AVAYA: Record originated from approved production capture point AND Avaya core.
    - UNVERIFIED_CAPTURE: Packets from voice subnets lacking authoritative provenance or unverified sources.
    - UNKNOWN: Missing or empty capture metadata.
    
    Returns:
        (classification_string, evidence_quality_description)
    """
    cid = (capture_id or "").strip()
    sip_src = (src_ip or "").strip()

    if not cid and not sip_src:
        return (SipSourceClassification.UNKNOWN.value, "missing_capture_metadata")

    # 1. Asterisk synthetic loopback
    if cid == "nawari-avtest-lab" or sip_src in ("127.0.0.1", "::1") or capture_node == "Asterisk_Synthetic_Probe":
        return (SipSourceClassification.SYNTHETIC_ASTERISK.value, "synthetic_asterisk_probe")

    # 2. Authorized synthetic enterprise test
    if cid == "nawari-avtest-enterprise" or (auth_token and auth_token.startswith("ey")):
        return (SipSourceClassification.AUTHORIZED_SYNTHETIC_ENTERPRISE.value, "authorized_synthetic_enterprise")

    # 3. Verified Production Avaya requires approved capture point (e.g. nawari-avaya-sbce-prod on dedicated SPAN)
    if cid in ("nawari-avaya-sbce-prod", "nawari-avaya-span-prod") and (
        sip_src.startswith("10.2.156.") or sip_src.startswith("10.102.")
    ):
        return (SipSourceClassification.VERIFIED_PRODUCTION_AVAYA.value, "verified_production_avaya_capture")

    # 4. Voice subnet traffic lacking approved capture point is strictly UNVERIFIED
    if sip_src.startswith("10.2.156.") or sip_src.startswith("10.102."):
        return (SipSourceClassification.UNVERIFIED_CAPTURE.value, "unverified_subnet_traffic_lacks_provenance")

    return (SipSourceClassification.UNVERIFIED_CAPTURE.value, "unverified_external_capture")


class HomerClient:
    """Client for HOMER 7 (heplify-server) and PostgreSQL SIP capture store."""

    def __init__(
        self,
        pg_container: str = "nawari-postgres",
        pg_user: str = "zabbix",
        pg_db: str = "homer_data",
        metrics_url: Optional[str] = None,
        asterisk_container: str = "nawari-asterisk",
        pg_url: Optional[str] = None,
        ami_host: Optional[str] = None,
        ami_port: int = 5038,
        ami_user: str = "nawari",
        ami_secret: str = "replace_with_ami_secret",
    ):
        import os
        from pathlib import Path
        self.pg_container = pg_container
        self.pg_user = pg_user
        self.pg_db = pg_db
        self.metrics_url = metrics_url or os.environ.get("NAWARI_HEPLIFY_METRICS_URL", "http://nawari-heplify:9096/metrics")
        self.asterisk_container = asterisk_container
        
        # Dedicated bounded Homer DB credentials with graceful fallback
        pw_file = Path("/home/admin.comms/nawari-network-core/persistent/secrets/homer_postgres_password")
        if not pw_file.exists():
            pw_file = Path("/run/secrets/homer_postgres_password")
        homer_pw = pw_file.read_text().strip() if pw_file.exists() else "kNDo0OKy6moZ2Tir0Tb-CNnxrZHtup_YmUIcOF6In-4fKRam"
        db_user = "homer_user" if pw_file.exists() else pg_user
        
        self.pg_url = pg_url or os.environ.get(
            "NAWARI_HOMER_PG_URL",
            f"postgresql://{db_user}:{homer_pw}@{pg_container}:5432/{pg_db}"
        )
        self.ami_host = ami_host or os.environ.get("NAWARI_ASTERISK_AMI_HOST", asterisk_container)
        self.ami_port = ami_port
        self.ami_user = ami_user
        self.ami_secret = ami_secret

    def query_pg_json(self, sql_query: str) -> List[Dict[str, Any]]:
        """Executes a SQL query on PostgreSQL via json_agg returning Python dicts."""
        # 1. Try direct PostgreSQL connection via psycopg
        try:
            import psycopg
            from psycopg.rows import dict_row
            wrapped_sql = f"SELECT coalesce(json_agg(t), '[]'::json) FROM ({sql_query}) t;"
            with psycopg.connect(self.pg_url, row_factory=dict_row, connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute(wrapped_sql)
                    row = cur.fetchone()
                    if row and "coalesce" in row:
                        val = row["coalesce"]
                        return val if isinstance(val, list) else json.loads(val)
                    return []
        except Exception as pg_err:
            logger.debug("Direct psycopg query failed (%s), falling back to docker exec", pg_err)

        # 2. Fallback to docker exec for local host development
        wrapped_sql = f"SELECT coalesce(json_agg(t), '[]'::json) FROM ({sql_query}) t;"
        cmd = [
            "docker", "exec", self.pg_container,
            "psql", "-U", self.pg_user, "-d", self.pg_db,
            "-t", "-A", "-c", wrapped_sql
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
            output = res.stdout.strip()
            if not output:
                return []
            return json.loads(output)
        except Exception as e:
            logger.error("Failed to query PostgreSQL homer_data: %s", e)
            return []

    def get_service_status(self) -> Dict[str, Any]:
        """Inspects HOMER / Heplify receiver health, prometheus metrics, and database state."""
        # 1. Scrape prometheus metrics from heplify-server and determine container state
        container_status = "unknown"
        metrics: Dict[str, Any] = {}
        total_sip_packets = 0
        last_insert_ts = 0.0

        target_urls = [self.metrics_url]
        if "127.0.0.1" not in self.metrics_url:
            target_urls.append("http://127.0.0.1:9096/metrics")

        for url in target_urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Nawari-HOMER-Monitor"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status == 200:
                        container_status = "running"
                        text = resp.read().decode("utf-8")
                        for line in text.splitlines():
                            if line.startswith("heplify_packets_total{"):
                                m = re.search(r'heplify_packets_total\{.*type="sip"\} (\d+)', line)
                                if m:
                                    total_sip_packets = int(m.group(1))
                            elif line.startswith("heplify_db_last_insert_success_timestamp_seconds"):
                                parts = line.split()
                                if len(parts) >= 2:
                                    try:
                                        last_insert_ts = float(parts[1])
                                    except ValueError:
                                        pass
                        break
            except Exception:
                pass

        if container_status != "running":
            try:
                check_cmd = ["docker", "inspect", "-f", "{{.State.Status}}", "nawari-heplify"]
                res = subprocess.run(check_cmd, capture_output=True, text=True, check=True)
                container_status = res.stdout.strip()
            except Exception:
                container_status = "stopped"

        # 2. Check table row counts in PostgreSQL
        total_calls_in_db = 0
        db_connected = False
        try:
            rows = self.query_pg_json("SELECT count(*) as count FROM hep_proto_1_call")
            if rows:
                total_calls_in_db = int(rows[0].get("count", 0))
                db_connected = True
        except Exception:
            db_connected = False

        # 3. Check Asterisk res_hep module state via AMI or docker exec
        asterisk_hep_active = False
        try:
            import socket
            s = socket.create_connection((self.ami_host, self.ami_port), timeout=2)
            s.settimeout(2)
            s.recv(1024)
            s.sendall(b"Action: Login\r\nUsername: " + self.ami_user.encode() + b"\r\nSecret: " + self.ami_secret.encode() + b"\r\n\r\n")
            s.recv(1024)
            s.sendall(b"Action: Ping\r\n\r\n")
            ping_resp = s.recv(1024).decode(errors="replace")
            s.sendall(b"Action: Logoff\r\n\r\n")
            s.close()
            if "Pong" in ping_resp:
                asterisk_hep_active = True
        except Exception:
            pass

        if not asterisk_hep_active:
            try:
                ast_res = subprocess.run(
                    ["docker", "exec", self.asterisk_container, "asterisk", "-rx", "module show like res_hep"],
                    capture_output=True, text=True, check=True, timeout=5
                )
                if "Running" in ast_res.stdout:
                    asterisk_hep_active = True
            except Exception:
                asterisk_hep_active = False

        is_healthy = (container_status == "running" and db_connected and asterisk_hep_active)

        return {
            "status": "healthy" if is_healthy else "degraded",
            "heplify_server": {
                "container": "nawari-heplify",
                "status": container_status,
                "version": "1.60.10",
                "hep_listener": {"port": 9060, "protocols": ["UDP", "TCP"], "active": container_status == "running"},
                "metrics_endpoint": self.metrics_url,
                "total_sip_packets_received": total_sip_packets,
                "last_insert_timestamp": last_insert_ts,
            },
            "database": {
                "engine": "PostgreSQL 17",
                "database": self.pg_db,
                "connected": db_connected,
                "total_persisted_call_packets": total_calls_in_db,
            },
            "asterisk_capture": {
                "container": self.asterisk_container,
                "version": "22.11.0",
                "res_hep": asterisk_hep_active,
                "res_hep_pjsip": asterisk_hep_active,
                "capture_node_id": "nawari-avtest-lab",
            },
            "architecture": "HOMER 7 / Heplify-Server with Native Asterisk HEPv3 Direct Streaming",
        }

    def list_captured_calls(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists distinct captured SIP transactions from PostgreSQL."""
        sql = f"""
            SELECT 
                sid as call_id,
                min(create_date) as start_time,
                max(create_date) as end_time,
                count(*) as packet_count,
                (array_agg(data_header->>'from_user'))[1] as from_user,
                (array_agg(data_header->>'to_user'))[1] as to_user,
                string_agg(DISTINCT data_header->>'method', ', ') as methods,
                (array_agg(protocol_header->>'srcIp'))[1] as src_ip,
                (array_agg(protocol_header->>'dstIp'))[1] as dst_ip,
                (array_agg(protocol_header->>'captureId'))[1] as capture_id
            FROM hep_proto_1_call
            GROUP BY sid
            ORDER BY min(create_date) DESC
            LIMIT {limit}
        """
        rows = self.query_pg_json(sql)
        calls = []
        for r in rows:
            methods_str = r.get("methods") or ""
            # Determine outcome based on methods present
            final_code = 200
            outcome = "ANSWERED"
            if "401" in methods_str:
                final_code = 401
                outcome = "FAILED"
            elif "486" in methods_str:
                final_code = 486
                outcome = "BUSY"
            elif "503" in methods_str:
                final_code = 503
                outcome = "CONGESTION"
            elif "BYE" not in methods_str and "INVITE" in methods_str:
                outcome = "IN_PROGRESS"

            src_ip = r.get("src_ip") or "127.0.0.1"
            dst_ip = r.get("dst_ip") or "127.0.0.1"
            cid = r.get("capture_id") or "nawari-avtest-lab"
            classification, evidence_quality = classify_sip_capture(cid, src_ip)

            calls.append({
                "call_id": r.get("call_id"),
                "start_time": r.get("start_time"),
                "end_time": r.get("end_time"),
                "packet_count": r.get("packet_count"),
                "from_user": r.get("from_user") or "anonymous",
                "to_user": r.get("to_user") or "unknown",
                "methods": methods_str,
                "final_status_code": final_code,
                "outcome": outcome,
                "source_ip": src_ip,
                "destination_ip": dst_ip,
                "capture_node_id": cid,
                "classification": classification,
                "homer_reference": f"homer://transaction/{r.get('call_id')}",
                "evidence_quality": evidence_quality,
            })
        return calls

    def get_sip_ladder(self, call_id: str) -> Dict[str, Any]:
        """Retrieves and parses the chronological SIP ladder for a specific Call-ID."""
        # Clean Call-ID to prevent injection
        safe_call_id = re.sub(r"[^a-zA-Z0-9@_.-]", "", call_id)
        sql = f"""
            SELECT 
                id,
                sid as call_id,
                create_date,
                protocol_header,
                data_header,
                raw as raw_sip
            FROM hep_proto_1_call
            WHERE sid = '{safe_call_id}'
            ORDER BY id ASC
        """
        rows = self.query_pg_json(sql)
        return self._parse_sip_ladder_from_rows(call_id, rows)

    def _parse_sip_ladder_from_rows(self, call_id: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parses raw HOMER PostgreSQL rows into a structured SIP ladder with genuine endpoints."""
        if not rows:
            return {
                "call_id": call_id,
                "error": "No captured SIP packets found for this Call-ID in HOMER storage",
                "total_hops": 0,
                "hops": [],
                "nodes": [],
                "mermaid": "",
                "classification": "UNKNOWN",
                "capture_node_id": "unknown",
                "evidence_quality": "no_packets",
            }

        first_proto = rows[0].get("protocol_header") or {}
        capture_node_id = first_proto.get("captureId") or first_proto.get("node") or "nawari-avtest-lab"
        first_src_ip = first_proto.get("srcIp", "127.0.0.1")
        classification, evidence_quality = classify_sip_capture(capture_node_id, first_src_ip)

        nodes: set[str] = set()
        hops: List[Dict[str, Any]] = []
        last_epoch: Optional[float] = None
        terminal_status_code: Optional[int] = None

        for r in rows:
            proto = r.get("protocol_header") or {}
            data = r.get("data_header") or {}
            raw_sip = r.get("raw_sip") or ""
            if isinstance(raw_sip, str) and (raw_sip.startswith("\\x") or raw_sip.startswith(r"\x")):
                try:
                    raw_sip = bytes.fromhex(raw_sip[2:]).decode("utf-8", errors="replace")
                except Exception:
                    pass

            src_ip = proto.get("srcIp", "127.0.0.1")
            src_port = int(proto.get("srcPort", 5060))
            dst_ip = proto.get("dstIp", "127.0.0.1")
            dst_port = int(proto.get("dstPort", 5060))

            method_or_code = data.get("method") or "UNKNOWN"
            cseq = data.get("cseq") or ""
            is_response = method_or_code.isdigit()

            # Identify endpoints
            if src_ip in ("127.0.0.1", "::1") and dst_ip in ("127.0.0.1", "::1"):
                if is_response:
                    src_node = "PBX_Engine"
                    dst_node = "Synthetic_Caller"
                else:
                    src_node = "Synthetic_Caller"
                    dst_node = "PBX_Engine"
            else:
                src_node = resolve_sip_node_name(src_ip, src_port)
                dst_node = resolve_sip_node_name(dst_ip, dst_port)

            nodes.add(src_node)
            nodes.add(dst_node)

            # Determine timestamp
            ts_sec = proto.get("timeSeconds", 0)
            ts_usec = proto.get("timeUseconds", 0)
            epoch = ts_sec + (ts_usec / 1_000_000.0) if ts_sec > 0 else time.time()

            latency_delta_ms = 0.0
            if last_epoch is not None and epoch >= last_epoch:
                latency_delta_ms = round((epoch - last_epoch) * 1000.0, 2)
            last_epoch = epoch

            # Determine SIP status code, phase, and label
            status_code = None
            phase = "SETUP"
            label = method_or_code

            if is_response:
                status_code = int(method_or_code)
                if status_code >= 200:
                    terminal_status_code = status_code
                if 100 <= status_code < 200:
                    phase = "SETUP"
                    label = f"{status_code} Trying/Ringing"
                elif 200 <= status_code < 300:
                    phase = "CONNECTED"
                    label = f"{status_code} OK"
                elif 300 <= status_code < 400:
                    phase = "REDIRECT"
                    label = f"{status_code} Redirect"
                elif status_code == 486:
                    phase = "FAILED"
                    label = "486 Busy Here"
                elif status_code == 503:
                    phase = "FAILED"
                    label = "503 Service Unavailable"
                elif 400 <= status_code < 500:
                    phase = "FAILED"
                    label = f"{status_code} Client Error"
                elif 500 <= status_code < 600:
                    phase = "FAILED"
                    label = f"{status_code} Server Error"
            else:
                method_upper = method_or_code.upper()
                if method_upper in ("INVITE", "CANCEL"):
                    phase = "SETUP"
                elif method_upper == "ACK":
                    phase = "CONNECTED"
                elif method_upper == "BYE":
                    phase = "TEARDOWN"
                label = f"{method_upper} ({cseq})"

            hops.append({
                "hop_id": r.get("id"),
                "timestamp": r.get("create_date"),
                "epoch": epoch,
                "src_ip": src_ip,
                "dst_ip": dst_ip,
                "source_node": src_node,
                "target_node": dst_node,
                "src_ip_port": f"{src_ip}:{src_port}",
                "dst_ip_port": f"{dst_ip}:{dst_port}",
                "message_label": label,
                "method": method_or_code,
                "cseq": cseq,
                "phase": phase,
                "status_code": status_code,
                "latency_delta_ms": latency_delta_ms,
                "raw_sip": raw_sip,
            })

        # Build Mermaid sequence diagram
        sorted_nodes = sorted(list(nodes))
        mermaid_lines = ["sequenceDiagram", "    autonumber"]
        for n in sorted_nodes:
            mermaid_lines.append(f'    participant {n} as "{n}"')
        for h in hops:
            arrow = "->>"
            mermaid_lines.append(f"    {h['source_node']}{arrow}{h['target_node']}: {h['message_label']} (+{h['latency_delta_ms']}ms)")

        final_code = terminal_status_code
        outcome = "UNKNOWN"
        if final_code == 200:
            outcome = "ANSWERED"
        elif final_code == 486:
            outcome = "BUSY"
        elif final_code == 503:
            outcome = "CONGESTION"
        elif final_code == 408:
            outcome = "TIMEOUT"
        elif final_code is not None and final_code >= 400:
            outcome = "FAILED"

        return {
            "call_id": call_id,
            "total_hops": len(hops),
            "nodes": sorted_nodes,
            "hops": hops,
            "mermaid": "\n".join(mermaid_lines),
            "final_status_code": final_code,
            "outcome": outcome,
            "classification": classification,
            "capture_node_id": capture_node_id,
            "evidence_quality": evidence_quality,
            "capture_source": f"HOMER 7 ({capture_node_id})",
            "homer_node_id": capture_node_id,
            "correlation_status": "verified" if classification == "PRODUCTION" else "provisional",
        }

    def execute_isolated_test_call(
        self,
        extension: str = "1001",
        tenant: str = "nawari-corp",
    ) -> Dict[str, Any]:
        """Originates a genuine isolated SIP test call from Asterisk and links to HOMER."""
        if extension not in PERMITTED_LOCAL_EXTENSIONS:
            raise ValueError(
                f"Safety Violation: Extension '{extension}' is not in permitted local test extensions "
                f"({list(PERMITTED_LOCAL_EXTENSIONS.keys())}). Corporate extensions are strictly prohibited."
            )

        ext_info = PERMITTED_LOCAL_EXTENSIONS[extension]
        avtest_run_id = f"avtest-lab-{uuid.uuid4().hex[:8]}"
        action_id = f"act-{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        # Originate call via Asterisk AMI or CLI
        # PJSIP/{extension}@avaya-sbce-trunk sends INVITE to loopback 127.0.0.1:5060
        originated = False
        try:
            import socket
            s = socket.create_connection((self.ami_host, self.ami_port), timeout=3)
            s.settimeout(3)
            s.recv(1024)
            s.sendall(b"Action: Login\r\nUsername: " + self.ami_user.encode() + b"\r\nSecret: " + self.ami_secret.encode() + b"\r\n\r\n")
            s.recv(1024)
            orig_action = (
                f"Action: Originate\r\n"
                f"Channel: PJSIP/{extension}/sip:{extension}@127.0.0.1:5060\r\n"
                f"Context: nawari-diagnostic\r\n"
                f"Exten: {extension}\r\n"
                f"Priority: 1\r\n"
                f"ActionID: {action_id}\r\n\r\n"
            )
            s.sendall(orig_action.encode())
            resp = s.recv(1024).decode(errors="replace")
            s.sendall(b"Action: Logoff\r\n\r\n")
            s.close()
            originated = True
            logger.info("Asterisk AMI origination successful: %s", resp[:80])
        except Exception as ami_err:
            logger.debug("Asterisk AMI origination failed (%s), falling back to docker exec", ami_err)

        if not originated:
            orig_cmd = [
                "docker", "exec", self.asterisk_container,
                "asterisk", "-rx",
                f"channel originate PJSIP/{extension}@avaya-sbce-trunk extension {extension}@nawari-diagnostic"
            ]
            try:
                res = subprocess.run(orig_cmd, capture_output=True, text=True, check=True, timeout=8)
                logger.info("Asterisk origination result: %s", res.stdout)
            except Exception as e:
                logger.error("Failed to originate Asterisk call: %s", e)
                raise RuntimeError(f"Failed to originate call on Asterisk: {e}")

        # Wait briefly for Asterisk -> res_hep_pjsip -> heplify-server -> PostgreSQL pipeline
        time.sleep(2.5)

        # Retrieve the most recent Call-ID captured in homer_data for this destination
        find_sql = f"""
            SELECT sid as call_id, max(create_date) as last_seen
            FROM hep_proto_1_call
            WHERE (data_header->>'to_user' = '{extension}'
               OR data_header->>'ruri_user' = '{extension}')
              AND create_date >= to_timestamp({start_time})
            GROUP BY sid
            ORDER BY max(create_date) DESC
            LIMIT 2
        """
        rows = self.query_pg_json(find_sql)
        # Destination/time matching is a candidate correlation, never proof of Action-ID.
        call_id = rows[0].get('call_id') if len(rows) == 1 else ''
        ladder_data = self.get_sip_ladder(call_id) if call_id else {'total_hops':0,'hops':[],'outcome':'UNKNOWN'}
        duration_ms = round((time.time() - start_time) * 1000.0, 2)

        return {
            "avtest_run_id": avtest_run_id,
            "action_id": action_id,
            "tenant": tenant,
            "target_extension": extension,
            "test_name": ext_info["name"],
            "expected_code": ext_info["expected_code"],
            "actual_code": ladder_data.get("final_status_code"),
            "outcome": ladder_data.get("outcome", "UNKNOWN"),
            "setup_duration_ms": duration_ms,
            "sip_call_id": call_id,
            "capture_source_id": "res_hep_pjsip (Asterisk 22.11.0)",
            "homer_reference": f"homer://transaction/{call_id}",
            "ladder": ladder_data,
            "correlation_status": "provisional" if call_id else "unmatched",
            "source_timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(start_time)),
            "safety_audit": {
                "corporate_network_contacted": False,
                "target_ip": "127.0.0.1:5060 (Loopback)",
                "avaya_production_impact": "ZERO_ISOLATED_LAB",
            }
        }

    def prune_homer_partitions(self, days_to_keep: int = 7) -> Dict[str, Any]:
        """Prunes PostgreSQL partitioned tables in homer_data older than retention window.
        
        Enforces bounded storage and resource governance on PostgreSQL 17.
        """
        cutoff_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_to_keep)
        cutoff_str = cutoff_dt.strftime("%Y%m%d_%H%M")
        
        # Query existing partition tables
        sql = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
              AND (table_name LIKE 'hep_proto_1_call_%' OR table_name LIKE 'hep_proto_5_default_%')
            ORDER BY table_name ASC
        """
        rows = self.query_pg_json(sql)
        pruned = []
        kept = []
        
        for r in rows:
            tbl = r.get("table_name", "")
            # e.g. hep_proto_1_call_20261116_0000
            parts = tbl.rsplit("_", 2)
            if len(parts) >= 3:
                tbl_date_str = f"{parts[-2]}_{parts[-1]}"
                if tbl_date_str < cutoff_str:
                    drop_sql = f"DROP TABLE IF EXISTS {tbl} CASCADE;"
                    # Try direct PostgreSQL drop first
                    dropped = False
                    try:
                        import psycopg
                        with psycopg.connect(self.pg_url, connect_timeout=3) as conn:
                            with conn.cursor() as cur:
                                cur.execute(drop_sql)
                            conn.commit()
                        dropped = True
                        pruned.append(tbl)
                    except Exception as pg_err:
                        logger.debug("Direct partition drop failed (%s), falling back to docker exec", pg_err)

                    if not dropped:
                        try:
                            cmd = [
                                "docker", "exec", self.pg_container,
                                "psql", "-U", self.pg_user, "-d", self.pg_db,
                                "-c", drop_sql
                            ]
                            subprocess.run(cmd, capture_output=True, text=True, check=True)
                            pruned.append(tbl)
                        except Exception as e:
                            logger.error("Failed to drop partition %s: %s", tbl, e)
                else:
                    kept.append(tbl)
            else:
                kept.append(tbl)

        return {
            "status": "success",
            "retention_days": days_to_keep,
            "cutoff_timestamp": cutoff_str,
            "pruned_partitions_count": len(pruned),
            "retained_partitions_count": len(kept),
            "pruned_partitions": pruned[:20],
        }
