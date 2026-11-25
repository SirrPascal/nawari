"""
tests/test_avaya_sip_provenance.py

Automated TDD test suite for Genuine Avaya SIP Observability and Provenance:
1. Verifies that HomerClient classifies packets by captureId ('nawari-avtest-lab' vs 'nawari-avaya-prod').
2. Verifies that real observed source and destination IPs are preserved and not coerced to 127.0.0.1.
3. Verifies dynamic node identification (resolving Avaya SBCE, SM, CM, and Carrier IPs to semantic node names).
4. Verifies that synthetic loopback calls are explicitly labeled [SYNTHETIC] and production calls [PRODUCTION].
5. Verifies that SIP ladder Mermaid generation correctly renders actual participating endpoints.
"""

import unittest
from pathlib import Path
import sys

_pkg = Path(__file__).resolve().parent.parent / "network observability" / "platform"
if str(_pkg) not in sys.path:
    sys.path.insert(0, str(_pkg))

from nawari.homer_client import HomerClient, resolve_sip_node_name, classify_sip_capture


class TestAvayaSipProvenance(unittest.TestCase):

    def setUp(self):
        self.homer = HomerClient()

    def test_node_name_resolution(self):
        """Verify IP addresses resolve to semantic Avaya infrastructure identities."""
        self.assertEqual(resolve_sip_node_name("10.2.156.22", 5061), "Avaya_Session_Manager")
        self.assertEqual(resolve_sip_node_name("10.2.156.23", 5061), "Avaya_Session_Manager")
        self.assertEqual(resolve_sip_node_name("10.2.156.30", 5060), "Avaya_Communication_Manager")
        self.assertEqual(resolve_sip_node_name("10.2.156.131", 5060), "Avaya_SBCE_Primary")
        self.assertEqual(resolve_sip_node_name("10.2.156.132", 5060), "Avaya_SBCE_Secondary")
        self.assertEqual(resolve_sip_node_name("10.2.156.60", 5060), "Avaya_G450_Gateway")
        self.assertEqual(resolve_sip_node_name("10.2.156.100", 5060), "Safaricom_SIP_Carrier")
        self.assertEqual(resolve_sip_node_name("127.0.0.1", 5060), "Asterisk_Synthetic_Probe")
        self.assertEqual(resolve_sip_node_name("192.168.1.50", 5060), "Endpoint_192_168_1_50")

    def test_capture_classification(self):
        """Verify strict separation of synthetic vs production signaling."""
        # Synthetic node
        synth_class, synth_quality = classify_sip_capture("nawari-avtest-lab", "127.0.0.1")
        self.assertEqual(synth_class, "SYNTHETIC")
        self.assertEqual(synth_quality, "synthetic_probe")

        # Production Avaya node
        prod_class, prod_quality = classify_sip_capture("nawari-avaya-sbce-prod", "10.2.156.131")
        self.assertEqual(prod_class, "PRODUCTION")
        self.assertEqual(prod_quality, "verified_production_capture")

        # Production Avaya SM node
        sm_class, sm_quality = classify_sip_capture("nawari-avaya-sm-prod", "10.2.156.23")
        self.assertEqual(sm_class, "PRODUCTION")
        self.assertEqual(sm_quality, "verified_production_capture")

    def test_sip_ladder_with_genuine_avaya_endpoints(self):
        """Verify SIP ladder parser preserves observed IPs and generates true multi-node sequence diagrams."""
        mock_raw_rows = [
            {
                "id": 101,
                "sid": "avaya-call-test-9901",
                "create_date": "2026-11-24T12:00:00.000Z",
                "protocol_header": {
                    "srcIp": "10.2.156.131",
                    "dstIp": "10.2.156.23",
                    "srcPort": 5060,
                    "dstPort": 5061,
                    "captureId": "nawari-avaya-sbce-prod",
                    "timeSeconds": 1795521600,
                    "timeUseconds": 1000
                },
                "data_header": {
                    "method": "INVITE",
                    "cseq": "101 INVITE",
                    "from_user": "+254700000001",
                    "to_user": "4500"
                },
                "raw_sip": "INVITE sip:4500@10.2.156.23:5061 SIP/2.0\r\nVia: SIP/2.0/TLS 10.2.156.131:5060\r\n\r\n"
            },
            {
                "id": 102,
                "sid": "avaya-call-test-9901",
                "create_date": "2026-11-24T12:00:00.004Z",
                "protocol_header": {
                    "srcIp": "10.2.156.23",
                    "dstIp": "10.2.156.131",
                    "srcPort": 5061,
                    "dstPort": 5060,
                    "captureId": "nawari-avaya-sbce-prod",
                    "timeSeconds": 1795521600,
                    "timeUseconds": 5000
                },
                "data_header": {
                    "method": "100",
                    "cseq": "101 INVITE"
                },
                "raw_sip": "SIP/2.0 100 Trying\r\n\r\n"
            },
            {
                "id": 103,
                "sid": "avaya-call-test-9901",
                "create_date": "2026-11-24T12:00:00.045Z",
                "protocol_header": {
                    "srcIp": "10.2.156.23",
                    "dstIp": "10.2.156.131",
                    "srcPort": 5061,
                    "dstPort": 5060,
                    "captureId": "nawari-avaya-sbce-prod",
                    "timeSeconds": 1795521600,
                    "timeUseconds": 46000
                },
                "data_header": {
                    "method": "200",
                    "cseq": "101 INVITE"
                },
                "raw_sip": "SIP/2.0 200 OK\r\n\r\n"
            }
        ]

        ladder = self.homer._parse_sip_ladder_from_rows("avaya-call-test-9901", mock_raw_rows)
        self.assertEqual(ladder["total_hops"], 3)
        self.assertEqual(ladder["classification"], "PRODUCTION")
        self.assertEqual(ladder["capture_node_id"], "nawari-avaya-sbce-prod")
        self.assertIn("Avaya_SBCE_Primary", ladder["nodes"])
        self.assertIn("Avaya_Session_Manager", ladder["nodes"])
        
        # Verify hops have preserved IP metadata
        h0 = ladder["hops"][0]
        self.assertEqual(h0["src_ip"], "10.2.156.131")
        self.assertEqual(h0["dst_ip"], "10.2.156.23")
        self.assertEqual(h0["source_node"], "Avaya_SBCE_Primary")
        self.assertEqual(h0["target_node"], "Avaya_Session_Manager")

        # Verify Mermaid diagram
        mermaid = ladder["mermaid"]
        self.assertIn("Avaya_SBCE_Primary->>Avaya_Session_Manager: INVITE", mermaid)
        self.assertIn("Avaya_Session_Manager->>Avaya_SBCE_Primary: 100 Trying/Ringing", mermaid)
        self.assertIn("Avaya_Session_Manager->>Avaya_SBCE_Primary: 200 OK", mermaid)


if __name__ == "__main__":
    unittest.main()
