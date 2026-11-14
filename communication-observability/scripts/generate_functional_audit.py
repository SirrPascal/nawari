#!/usr/bin/env python3
"""
scripts/generate_functional_audit.py

Generates:
1. docs/dashboards/dashboard-functional-audit.md
2. docs/dashboards/dashboard-consolidation-matrix.md
"""

import json
from pathlib import Path

def main():
    root = Path(__file__).resolve().parent.parent
    inv_file = root / "docs/dashboards/raw_inventory.json"
    with open(inv_file) as f:
        inventory = json.load(f)

    # Dictionary of functional audit details for each dashboard
    audit_data = {
        "nawari-enterprise-overview": {
            "purpose": "Global enterprise-wide health, aviation station availability, active P1/P2 incidents, service tier status, and notification delivery.",
            "audience": "Executive Leadership, Head of IT, Senior NOC Management",
            "questions": "Is the global airline infrastructure healthy? Are any stations offline? Are there active P1/P2 incidents impacting operations? What is the regional availability trend?",
            "telemetry": "Calculated Zabbix synthetic items, aggregate operational metrics, service health matrix.",
            "provenance": "Aggregated & Calculated Zabbix Telemetry",
            "type": "Executive Overview (Tier 1 Entry Point)",
            "unique": "Enterprise service tier health matrix, regional health trends, global outstation availability rate.",
            "overlaps": "Outstation metrics overlap with nawari-global-outstations; incident counts overlap with nawari-incident-operations.",
            "recommendation": "Retain as primary Grafana Home Dashboard with direct drill-down links to domain overviews."
        },
        "nawari-net-overview": {
            "purpose": "Core network infrastructure device inventory, CPU, memory, uptime, and device availability.",
            "audience": "NOC Network Engineers, Infrastructure Administrators",
            "questions": "Are core switches and distribution gateways responsive? Are CPU/memory resources strained? Which network devices are down?",
            "telemetry": "Zabbix SNMP (sysUpTime, hrProcessorLoad, hrStorageUsed), ICMP ping.",
            "provenance": "Real Zabbix SNMP Telemetry",
            "type": "Domain Overview (Tier 2)",
            "unique": "Core distribution gateway and lab switch resource metrics, SNMP availability.",
            "overlaps": "Device availability overlaps with nawari-network-topology and nawari-interface-health.",
            "recommendation": "Consolidate into Network Operations Overview as core infrastructure section."
        },
        "nawari-interface-health": {
            "purpose": "Interface throughput, traffic rates, error counters, discard rates, and utilization percentages.",
            "audience": "Network Engineers, Capacity Planners",
            "questions": "Which switch ports or uplinks are congested? Are there packet discards or CRC errors on network interfaces?",
            "telemetry": "Zabbix SNMP ifHCInOctets, ifHCOutOctets, ifInErrors, ifOutErrors, ifInDiscards, ifOutDiscards.",
            "provenance": "Real Zabbix SNMP 64-bit Counters",
            "type": "Technical Diagnostic (Tier 4)",
            "unique": "Deep-dive interface traffic analysis with variable filtering for device and interface.",
            "overlaps": "Core link bandwidth indicators overlap with nawari-net-overview.",
            "recommendation": "Integrate as detailed diagnostic row in Network Operations Overview with variables ($group, $host, $interface)."
        },
        "nawari-network-topology": {
            "purpose": "Visualization of network topology layers, device interconnections, and service dependencies.",
            "audience": "NOC Operators, System Architects",
            "questions": "How do edge devices connect to core gateways and datacenters? What path does traffic take across core layers?",
            "telemetry": "Zabbix host dependencies, network topology map definitions.",
            "provenance": "Calculated Structural Topology",
            "type": "Visual Overview / Dependency Map",
            "unique": "Topology layer hierarchy and cross-layer structural links.",
            "overlaps": "Topology relationships overlap with nawari-service-catalog-sla dependencies.",
            "recommendation": "Embed as visual topology row in Network Operations Overview."
        },
        "nawari-global-outstations": {
            "purpose": "Worldwide outstation connectivity, regional latency (Domestic, East Africa, International), and outstation SLA compliance.",
            "audience": "Global Operations Center, Airport IT Support",
            "questions": "Are international outstations (LHR, DXB, JNB) reachable? Is trans-regional WAN latency within acceptable limits?",
            "telemetry": "Zabbix ICMP ping, WAN probe latency, outstation availability status.",
            "provenance": "Real & Synthetic Network Telemetry",
            "type": "Domain Deep-Dive (Tier 3)",
            "unique": "Regional station grouping, airport hub connectivity indicators, WAN SLA.",
            "overlaps": "Regional health trends overlap with nawari-enterprise-overview.",
            "recommendation": "Consolidate into WAN, Path & Outstation Observability."
        },
        "nawari-path-analysis": {
            "purpose": "Hop-by-hop path tracing, directional latency, jitter, loss, and route divergence analysis.",
            "audience": "Senior Network Engineers, Telecommunications Specialists",
            "questions": "Where is the bottleneck in the path between endpoints and core services? Which intermediate hop is dropping packets?",
            "telemetry": "Zabbix traceroute synthetic items, directional ICMP hop probes.",
            "provenance": "Synthetic & Measured Path Telemetry",
            "type": "Technical Diagnostic (Tier 4)",
            "unique": "Hop-by-hop breakdown, directional asymmetry analysis.",
            "overlaps": "Path latency overlaps with nawari-global-outstations WAN latency.",
            "recommendation": "Consolidate into WAN, Path & Outstation Observability."
        },
        "nawari-edge-fleet": {
            "purpose": "Distributed edge collector fleet health, SQLite spool storage buffers, and telemetry sync state.",
            "audience": "Observability Engineers, Platform Administrators",
            "questions": "Are edge proxies/collectors running out of disk space? Is edge telemetry buffering or failing to sync upstream?",
            "telemetry": "Edge spool storage gauge, store-and-forward queue depth, agent buffer status.",
            "provenance": "Platform Operational Telemetry",
            "type": "Infrastructure Support (Tier 3)",
            "unique": "Store-and-forward buffer monitoring, spool disk capacity metrics.",
            "overlaps": "Collector reachability overlaps with general infrastructure monitoring.",
            "recommendation": "Consolidate into WAN, Path & Outstation Observability as the edge telemetry reliability section."
        },
        "nawari-endpoint-fleet": {
            "purpose": "High-level overview of enrolled corporate laptops, active reporting endpoints, presence breakdown, and top degraded devices.",
            "audience": "End-User Computing (EUC) Team, Service Desk, Desktop Support",
            "questions": "How many employee laptops are reporting? What percentage are on corporate Wi-Fi vs remote? Which laptops are experiencing edge issues?",
            "telemetry": "Zabbix Agent 2 active metrics, Presence Detector states, Lifecycle Classifier.",
            "provenance": "Real Endpoint Agent Telemetry",
            "type": "Domain Overview (Tier 3)",
            "unique": "Fleet presence breakdown, anti-false-positive lifecycle counts (sleep, shutdown, off-net).",
            "overlaps": "Metrics overlap with nawari-eu-nem-pilot and nawari-endpoint-detail.",
            "recommendation": "Consolidate into Endpoint & User Experience as the fleet summary section."
        },
        "nawari-endpoint-detail": {
            "purpose": "Single-laptop forensic investigation: gateway loss, DNS latency, Wi-Fi RSSI/BSSID, OS lifecycle events, battery status.",
            "audience": "Desktop Support Specialists, Incident Responders",
            "questions": "Why is Jimmy experiencing poor Zoom/Teams calls? Is it his local Wi-Fi signal, gateway loss, or DNS?",
            "telemetry": "Zabbix Agent 2 active diagnostic probes (`nawari.nem.all`), Windows EventLog / macOS power logs.",
            "provenance": "Real Endpoint Diagnostic Telemetry",
            "type": "Technical Diagnostic (Tier 4)",
            "unique": "Granular single-device drill-down with $endpoint variable selector.",
            "overlaps": "Probes overlap with nawari-eu-nem-pilot.",
            "recommendation": "Consolidate into Endpoint & User Experience as the single-device deep-dive section."
        },
        "nawari-eu-nem-pilot": {
            "purpose": "Dedicated pilot dashboard for the End-User Network Experience Monitoring initiative, live active check validation.",
            "audience": "Pilot Stakeholders, Engineering Team",
            "questions": "Are pilot laptops successfully reporting live diagnostic telemetry? What are the gateway RTT and DNS stats?",
            "telemetry": "Zabbix Agent 2 master snapshot (`nawari.nem.all`) and dependent items.",
            "provenance": "Real Active Endpoint Diagnostics",
            "type": "Pilot Dashboard",
            "unique": "Focused pilot fleet view with 10s auto-refresh.",
            "overlaps": "100% functionally overlaps with endpoint-fleet and endpoint-detail.",
            "recommendation": "Unify into the consolidated Endpoint & User Experience dashboard."
        },
        "nawari-service-catalog-sla": {
            "purpose": "Aviation business service reliability, multi-dimensional SLIs (latency, availability, error rate), SLO compliance, and error budgets.",
            "audience": "IT Service Management, Business Relationship Managers, Operations Directors",
            "questions": "Are core airline services (Flight Ops, Baggage Handling, Check-in, DCS) meeting their 99.9% SLO? How much error budget remains?",
            "telemetry": "Zabbix SLA service items, SLI calculators, error budget burn rates.",
            "provenance": "Service Assurance SLI / SLA Telemetry",
            "type": "Business Service Tier (Tier 2/3)",
            "unique": "Multi-dimensional service catalogue, error budget burn rates, tiered SLA compliance.",
            "overlaps": "Service status overlaps with nawari-enterprise-overview.",
            "recommendation": "Consolidate into Network Services & Incident Assurance."
        },
        "nawari-incident-operations": {
            "purpose": "Active incident lifecycle tracking, MTTR metrics, automated escalation triggers, and verified recovery states.",
            "audience": "Incident Managers, NOC Shift Leads",
            "questions": "What active P1/P2/P3 incidents exist? Are incidents escalating according to policy? Has a service truly recovered or is it flapping?",
            "telemetry": "Zabbix problem events, recovery events, incident lifecycle state machine.",
            "provenance": "Event-Derived Incident Telemetry",
            "type": "Operational Assurance (Tier 3)",
            "unique": "Recovery verification logic, MTTR tracking, escalation phase tracking.",
            "overlaps": "Incident count overlaps with nawari-enterprise-overview.",
            "recommendation": "Consolidate into Network Services & Incident Assurance."
        },
        "nawari-predictive-intelligence": {
            "purpose": "Dynamic baseline calculation, seasonal anomaly detection, predictive bandwidth exhaustion, and early warning degradation indicators.",
            "audience": "Capacity Planners, Observability Engineers",
            "questions": "Which links are exhibiting abnormal traffic compared to historical Thursdays? Is a capacity exhaustion predicted in the next 14 days?",
            "telemetry": "Statistical Zabbix trend functions, Holt-Winters baseline projections.",
            "provenance": "Predictive Statistical Telemetry",
            "type": "Advanced Analytics (Tier 3)",
            "unique": "Dynamic threshold baselines, degradation assurance indicators.",
            "overlaps": "Metric sources are network links and services.",
            "recommendation": "Consolidate into Network Services & Incident Assurance."
        },
        "nawari-controlled-operations": {
            "purpose": "Audit log and status of automated remediation actions, circuit breakers, and controlled operational scripts.",
            "audience": "NOC Operations, Platform Engineers",
            "questions": "Did an automated restart trigger for a failing collector? Is any circuit breaker currently tripped?",
            "telemetry": "Zabbix action execution logs, remediation state flags.",
            "provenance": "Operational Action Audit Telemetry",
            "type": "Automation & Remediation (Tier 3)",
            "unique": "Automated action execution ledger and circuit breaker state.",
            "overlaps": "Actions correlate with incidents in nawari-incident-operations.",
            "recommendation": "Consolidate into Network Services & Incident Assurance."
        },
        "nawari-comm-overview": {
            "purpose": "Executive summary of communication infrastructure: core Avaya appliances, SIP trunks, call volume, and overall voice assurance.",
            "audience": "Head of Telecoms, Voice Engineers, Executive NOC",
            "questions": "Are Avaya CM, SM, SBCE, and G450 operational? Are SIP trunks up? What is the current active call volume across the enterprise?",
            "telemetry": "Zabbix aggregate telephony items, SIP OPTIONS status, SNMP appliance summaries.",
            "provenance": "Aggregated Telephony & Voice Telemetry",
            "type": "Domain Overview (Tier 2 Entry Point)",
            "unique": "Unified multi-appliance voice overview, carrier trunk status summary.",
            "overlaps": "Appliance statuses overlap with individual component dashboards.",
            "recommendation": "Retain as primary Communication Services Overview with drill-down links to Avaya and Voice Quality dashboards."
        },
        "nawari-sbce-health": {
            "purpose": "Avaya Session Border Controller Enterprise (SBCE) appliance resources, TLS handshakes, SIP entity reachability, active sessions, and security limits.",
            "audience": "Telephony Engineers, Voice Security Specialists",
            "questions": "Is SBCE CPU or memory spiking? Are TLS connections negotiating properly? What is the concurrent SIP session load?",
            "telemetry": "Zabbix SNMP SBCE MIB (avSbceSystemCpuUtil, avSbceTotalCalls, avSbceTlsHandshakeErrors).",
            "provenance": "Real SBCE SNMP Telemetry",
            "type": "Technical Diagnostic (Tier 4)",
            "unique": "SBCE deep metrics, perimeter security limits, TLS handshake performance.",
            "overlaps": "Perimeter status overlaps with nawari-sip-trunks.",
            "recommendation": "Consolidate into Avaya Infrastructure & Signaling as the SBCE section."
        },
        "nawari-session-manager": {
            "purpose": "Avaya Aura Session Manager (ASM) operational health, SIP entity routing, transaction rates, response times, and memory heap.",
            "audience": "Avaya Voice Engineers, Systems Administrators",
            "questions": "Is Session Manager routing SIP INVITEs successfully? Are entity links to CM or SBCE degraded? What is the SIP response latency?",
            "telemetry": "Zabbix SNMP Avaya ASM MIB, JVM heap memory, SIP message throughput counters.",
            "provenance": "Real Avaya ASM SNMP Telemetry",
            "type": "Technical Diagnostic (Tier 4)",
            "unique": "SIP entity routing matrix, ASM JVM metrics, SIP transaction rates.",
            "overlaps": "SIP routing overlaps with nawari-sip-trunks and nawari-communication-manager.",
            "recommendation": "Consolidate into Avaya Infrastructure & Signaling as the Session Manager section."
        },
        "nawari-communication-manager": {
            "purpose": "Avaya Aura Communication Manager (ACM) call processing occupancy, registered IP endpoints, DSP resource utilization, and hourly voice statistics.",
            "audience": "Avaya Telephony Engineers, Telecoms Operations",
            "questions": "What is CM processor occupancy? Are IP phones unregistering? Are DSP channels exhausting on media processors?",
            "telemetry": "Zabbix SNMP Avaya CM MIB (avCmMeasIpVoStatSumDataLstHrTable, avCmAlarmsTable, 1-hour polling delay enforced).",
            "provenance": "Real Avaya CM SNMP Telemetry (Hourly Polled)",
            "type": "Technical Diagnostic (Tier 4)",
            "unique": "Registered endpoint counts, hourly voice statistics, processor occupancy.",
            "overlaps": "Voice quality overlaps with nawari_voice_intelligence.",
            "recommendation": "Consolidate into Avaya Infrastructure & Signaling as the Communication Manager section."
        },
        "nawari-g450-gateway": {
            "purpose": "Avaya G450 Media Gateway chassis health, power supplies, fans, temperature, DSP VoIP media channels, and E1/T1 PRI sync.",
            "audience": "Hardware Telecoms Engineers, Datacenter Support",
            "questions": "Is the G450 power supply redundant? Are DSP VoIP resources depleted? Is the E1 ISDN PRI clock synchronization locked?",
            "telemetry": "Zabbix SNMP G450 MIB (chassis environment, VoIP channel occupancy, DS1 sync).",
            "provenance": "Real Hardware SNMP Telemetry",
            "type": "Technical Diagnostic (Tier 4)",
            "unique": "Physical appliance chassis monitoring, E1/T1 PRI sync status, DSP VoIP channels.",
            "overlaps": "DSP metrics overlap with CM media resource allocation.",
            "recommendation": "Consolidate into Avaya Infrastructure & Signaling as the G450 Media Gateway section."
        },
        "nawari-sip-trunks": {
            "purpose": "Carrier SIP trunk signaling ladders, SIP OPTIONS round-trip time, carrier response codes (200 OK vs 503 Service Unavailable), and perimeter session routing.",
            "audience": "Voice Network Engineers, Telecom Carrier Managers",
            "questions": "Are Safaricom and Airtel SIP trunks answering OPTIONS pings? What is the carrier signaling response time? Are calls rejecting with 503?",
            "telemetry": "Zabbix SIP OPTIONS response time, SIP ladder status, carrier link availability.",
            "provenance": "Real Signaling Telemetry (Layer 5)",
            "type": "Domain Deep-Dive (Tier 3)",
            "unique": "Carrier signaling ladders, SIP OPTIONS latency comparison across telcos.",
            "overlaps": "Signaling reachability overlaps with SBCE active calls.",
            "recommendation": "Consolidate into Avaya Infrastructure & Signaling as the Carrier SIP Trunks section."
        },
        "nawari-voice-intelligence": {
            "purpose": "Synthetic voice probing via Asterisk test calls, PESQ/POLQA scoring, media delay, jitter, and real-call uninstrumented indicators.",
            "audience": "Voice Quality Specialists, SLA Managers",
            "questions": "What is the synthetic MOS score across internal extensions? Are synthetic calls completing? Is jitter elevated on voice VLANs?",
            "telemetry": "Synthetic Asterisk call probes, RFC 3611 RTCP-XR placeholders (honest uninstrumented indicators), Avaya hourly summary.",
            "provenance": "Synthetic Call Probe & Real SNMP (Explicitly Labeled)",
            "type": "Technical Diagnostic (Tier 3)",
            "unique": "Synthetic call PESQ/MOS metrics, strict distinction between synthetic probes and customer calls.",
            "overlaps": "Media quality overlaps with nawari-voice-service-assurance.",
            "recommendation": "Consolidate into Voice Quality & Contact Centre as the Voice Quality & Synthetic Testing section."
        },
        "nawari-voice-service-assurance": {
            "purpose": "Comprehensive voice media quality: RTP packet loss, codec utilization (G.711 vs G.729), audio jitter buffer, and voice service SLIs.",
            "audience": "Voice Operations, Telecoms NOC",
            "questions": "What audio codecs are in use? What is the aggregate voice packet loss? Are voice calls experiencing clipping?",
            "telemetry": "Zabbix media stream telemetry, RTP loss metrics, codec counters.",
            "provenance": "Real & Synthetic Voice Media Telemetry",
            "type": "Domain Deep-Dive (Tier 3)",
            "unique": "Codec distribution, media stream jitter buffer analysis.",
            "overlaps": "Overlap with nawari_voice_intelligence.",
            "recommendation": "Consolidate into Voice Quality & Contact Centre."
        },
        "nawari-cms-contact-centre": {
            "purpose": "Avaya Call Management System (CMS) contact centre ACD split/skill queue performance: depth, Average Speed of Answer (ASA), abandonment rate, agent states.",
            "audience": "Contact Centre Operations, Customer Service Managers",
            "questions": "What is the current queue depth for customer reservations? Is call abandonment spiking above 5%? How many agents are staffed vs idle?",
            "telemetry": "Zabbix CMS integration items, ACD queue statistics, agent state counters.",
            "provenance": "Application-Derived Contact Centre Telemetry",
            "type": "Domain Deep-Dive (Tier 3)",
            "unique": "ACD split/skill metrics, queue abandonment rate, agent staffing levels.",
            "overlaps": "Call volume overlaps with CM total calls.",
            "recommendation": "Consolidate into Voice Quality & Contact Centre as the Contact Centre Performance section."
        },
        "nawari-recording-wfo": {
            "purpose": "Voice recording (Verint / WFO) operational health, compliance recording percentage, audio capture buffer, and recording pipeline status.",
            "audience": "Compliance Officers, Quality Assurance Leads, Telecoms Engineers",
            "questions": "Are 100% of regulated calls being recorded? Is the recording buffer filling? Are any audio capture streams dropping?",
            "telemetry": "Zabbix Verint/WFO health items, recording stream active flags.",
            "provenance": "Application & Compliance Telemetry",
            "type": "Compliance & Diagnostic (Tier 3)",
            "unique": "Audio recording compliance rate, recording buffer queue depth.",
            "overlaps": "Correlates with contact centre active calls.",
            "recommendation": "Consolidate into Voice Quality & Contact Centre as the Recording & Compliance section."
        },
        "nawari-voice-correlation": {
            "purpose": "Cross-domain correlation linking endpoint Wi-Fi/network health with voice call quality and network incidents affecting telephony.",
            "audience": "Cross-Functional NOC, Tier 3 Incident Escalation",
            "questions": "Is an agent's reported voice degradation caused by their local Wi-Fi packet loss or by carrier SIP trunk congestion?",
            "telemetry": "Correlated metrics joining endpoint diagnostics with voice call quality streams.",
            "provenance": "Cross-Domain Correlated Analytics",
            "type": "Cross-Domain Operations (Tier 3)",
            "unique": "Side-by-side time-correlated Wi-Fi and voice jitter telemetry, automated cross-domain root-cause hypotheses.",
            "overlaps": "Draws from endpoint-detail and voice-service-assurance.",
            "recommendation": "Consolidate into Cross-Domain Correlation & Operations as the primary cross-domain dashboard."
        }
    }

    # Generate dashboard-functional-audit.md
    lines_audit = []
    lines_audit.append("# Nawari Dashboard Functional Audit")
    lines_audit.append("")
    lines_audit.append("**Audit Date:** 2026-11-08")
    lines_audit.append("**Scope:** Deep functional inspection of all 25 active Grafana dashboards in Nawari")
    lines_audit.append("**Operational Objective:** Establish baseline capabilities, identify functional overlap, and define consolidation boundaries without telemetry loss.")
    lines_audit.append("")
    lines_audit.append("---")
    lines_audit.append("")
    lines_audit.append("## 1. Domain Summary & Classification")
    lines_audit.append("")
    lines_audit.append("| UID | Dashboard Title | Operational Tier | Telemetry Provenance | Primary Operational Question |")
    lines_audit.append("|---|---|---|---|---|")

    for d in sorted(inventory, key=lambda x: (x["folderTitle"], x["title"])):
        uid = d["uid"]
        info = audit_data.get(uid, {})
        tier = info.get("type", "Technical Diagnostic")
        prov = info.get("provenance", "Zabbix Telemetry")
        q = info.get("questions", "").split("?")[0] + "?" if info.get("questions") else "N/A"
        lines_audit.append(f"| `{uid}` | {d['title']} | {tier} | {prov} | {q} |")

    lines_audit.append("")
    lines_audit.append("---")
    lines_audit.append("")
    lines_audit.append("## 2. In-Depth Per-Dashboard Functional Profiles")
    lines_audit.append("")

    for d in sorted(inventory, key=lambda x: (x["folderTitle"], x["title"])):
        uid = d["uid"]
        info = audit_data.get(uid, {})
        lines_audit.append(f"### `{uid}` — {d['title']}")
        lines_audit.append(f"- **Primary Operational Purpose:** {info.get('purpose', 'N/A')}")
        lines_audit.append(f"- **Target Audience:** {info.get('audience', 'N/A')}")
        lines_audit.append(f"- **Core Questions Answered:** {info.get('questions', 'N/A')}")
        lines_audit.append(f"- **Telemetry Sources:** {info.get('telemetry', 'N/A')}")
        lines_audit.append(f"- **Data Provenance:** {info.get('provenance', 'N/A')}")
        lines_audit.append(f"- **Operational Tier:** {info.get('type', 'N/A')}")
        lines_audit.append(f"- **Unique Capabilities:** {info.get('unique', 'N/A')}")
        lines_audit.append(f"- **Functional Overlaps:** {info.get('overlaps', 'N/A')}")
        lines_audit.append(f"- **Consolidation Action:** {info.get('recommendation', 'N/A')}")
        lines_audit.append("")

    (root / "docs/dashboards/dashboard-functional-audit.md").write_text("\n".join(lines_audit), encoding="utf-8")
    print("Generated docs/dashboards/dashboard-functional-audit.md")

    # Generate dashboard-consolidation-matrix.md
    matrix_mapping = [
        # 1. Enterprise Executive Overview
        ("nawari-enterprise-overview", "Enterprise Executive Overview & Fleet Availability", "Global service tier health, P1/P2 incidents, outstation availability", "Enterprise Executive Overview", "Retained as Tier 1 Home Entry Point (UID: `nawari-enterprise-overview`)"),
        
        # 2. Network Operations Overview
        ("nawari-net-overview", "Network Infrastructure Overview", "Core router/switch CPU, memory, uptime, availability", "Network Operations Overview", "Consolidated (Row: Core Infrastructure Devices)"),
        ("nawari-interface-health", "Interface Traffic & Performance Health", "64-bit interface counters, bandwidth, discards, CRC errors", "Network Operations Overview", "Consolidated (Row: Interface Health & Link Traffic)"),
        ("nawari-network-topology", "Network Topology & Service Dependencies", "Cross-layer visual topology and device interconnections", "Network Operations Overview", "Consolidated (Row: Network Topology & Layer Hierarchy)"),
        
        # 3. WAN, Path & Outstation Observability
        ("nawari-global-outstations", "Global Outstation Network & WAN Telemetry", "International airport hub connectivity, regional WAN latency", "WAN, Path & Outstation Observability", "Consolidated (Row: Outstation Telemetry & Regional Latency)"),
        ("nawari-path-analysis", "Network Path & Directional Hop Analysis", "Directional hop latency, jitter, loss, path divergence", "WAN, Path & Outstation Observability", "Consolidated (Row: Directional Path & Hop Analysis)"),
        ("nawari-edge-fleet", "Distributed Edge Collector Fleet & Spool Storage", "Store-and-forward queue depth, SQLite spool buffer health", "WAN, Path & Outstation Observability", "Consolidated (Row: Distributed Edge Collector Fleet)"),
        
        # 4. Endpoint & User Experience
        ("nawari-endpoint-fleet", "Endpoint Fleet Observability Overview", "Fleet presence breakdown, active laptops, top degraded devices", "Endpoint & User Experience", "Consolidated (Row: Endpoint Fleet Health & Presence)"),
        ("nawari-endpoint-detail", "Endpoint Deep-Dive & Edge Experience", "Forensic single-device drill-down ($endpoint selector)", "Endpoint & User Experience", "Consolidated (Row: Forensic Endpoint Investigation)"),
        ("nawari-eu-nem-pilot", "End-User Network Experience", "Live active agent probe metrics, gateway RTT/loss, DNS latency", "Endpoint & User Experience", "Consolidated (Row: Real-Time Active Probe Diagnostics)"),
        
        # 5. Network Services & Incident Assurance
        ("nawari-service-catalog-sla", "Aviation Business Service Catalogue & SLA/SLO Assurance", "Tiered business service SLIs/SLOs, error budget burn rates", "Network Services & Incident Assurance", "Consolidated (Row: Aviation Service Catalogue & Error Budgets)"),
        ("nawari-incident-operations", "Incident Operations, Escalation & Verified Recovery", "Active P1/P2 timeline, automated escalation, verified recovery", "Network Services & Incident Assurance", "Consolidated (Row: Incident Lifecycle & Recovery Assurance)"),
        ("nawari-predictive-intelligence", "Predictive Intelligence, Dynamic Baselines & Degradation Assurance", "Seasonal Holt-Winters baselines, capacity exhaustion predictions", "Network Services & Incident Assurance", "Consolidated (Row: Predictive Intelligence & Dynamic Baselines)"),
        ("nawari-controlled-operations", "Controlled Operational Actions & Automated Remediation", "Automated remediation audit ledger, circuit breaker states", "Network Services & Incident Assurance", "Consolidated (Row: Automated Operations & Circuit Breakers)"),
        
        # 6. Communication Services Overview
        ("nawari-comm-overview", "Enterprise Communication Services Overview & Executive Service Assurance", "Unified voice appliance status, carrier trunk health, total calls", "Communication Services Overview", "Retained as Tier 2 Voice Entry Point (UID: `nawari-comm-overview`)"),
        
        # 7. Avaya Infrastructure & Signaling
        ("nawari-sbce-health", "Avaya SBCE Operational Health", "SBCE CPU/memory, TLS handshakes, perimeter security limits", "Avaya Infrastructure & Signaling", "Consolidated (Row: Session Border Controller - SBCE)"),
        ("nawari-session-manager", "Avaya Aura Session Manager (ASM) Operational Health & SIP Entity Routing", "SIP entity routing matrix, ASM JVM heap, transaction rates", "Avaya Infrastructure & Signaling", "Consolidated (Row: Session Manager - ASM)"),
        ("nawari-communication-manager", "Avaya Aura Communication Manager (CM) Call Processing & IP Voice Performance", "CM processor occupancy, registered endpoints, hourly IP voice", "Avaya Infrastructure & Signaling", "Consolidated (Row: Communication Manager - ACM)"),
        ("nawari-g450-gateway", "Avaya G450 Media Gateway Appliance & Physical Telephony Health", "Chassis power/fans, DSP VoIP channels, E1/T1 PRI clock sync", "Avaya Infrastructure & Signaling", "Consolidated (Row: G450 Media Gateway Appliance)"),
        ("nawari-sip-trunks", "Carrier SIP Trunks, Signaling Ladders & Perimeter Session Routing", "Carrier SIP OPTIONS latency, signaling ladder, 503 error rates", "Avaya Infrastructure & Signaling", "Consolidated (Row: Carrier SIP Trunks & Signaling)"),
        
        # 8. Voice Quality & Contact Centre
        ("nawari-voice-intelligence", "Communications Intelligence & Voice Service Assurance", "Synthetic Asterisk call probes, PESQ/POLQA, uninstrumented real MOS", "Voice Quality & Contact Centre", "Consolidated (Row: Voice Intelligence & Synthetic Testing)"),
        ("nawari-voice-service-assurance", "Voice Service Assurance & Media Quality", "RTP packet loss, codec distribution (G.711/G.729), jitter buffer", "Voice Quality & Contact Centre", "Consolidated (Row: Voice Media Quality & Stream Diagnostics)"),
        ("nawari-cms-contact-centre", "Avaya Call Management System (CMS) & Contact Centre Performance", "ACD split/skill queue depth, ASA, abandonment rate, agent state", "Voice Quality & Contact Centre", "Consolidated (Row: CMS Contact Centre Performance)"),
        ("nawari-recording-wfo", "Voice Recording & Workforce Optimisation (WFO) Operational Health", "Verint recording compliance %, audio buffer, stream status", "Voice Quality & Contact Centre", "Consolidated (Row: Voice Recording & Compliance)"),
        
        # 9. Cross-Domain Correlation & Operations
        ("nawari-voice-correlation", "Cross-Domain Voice & Endpoint Telemetry Correlation", "Correlated endpoint Wi-Fi loss vs voice jitter, cross-domain root-cause", "Cross-Domain Correlation & Operations", "Retained as Tier 3 Correlation Hub (UID: `nawari-voice-correlation`)")
    ]

    lines_mat = []
    lines_mat.append("# Nawari Dashboard Consolidation & Rationalisation Matrix")
    lines_mat.append("")
    lines_mat.append("**Rationalisation Target:** Consolidate 25 fragmented dashboards into a 9-Dashboard Progressive Drill-Down Architecture.")
    lines_mat.append("**Guiding Principle:** **One Operational Entry Point → Domain Overview → Technology Deep-Dive → Component Diagnostics.**")
    lines_mat.append("")
    lines_mat.append("---")
    lines_mat.append("")
    lines_mat.append("| Original Dashboard UID | Original Dashboard Title | Unique Functionality Preserved | Destination Consolidated Dashboard | Migration Status & Row Mapping |")
    lines_mat.append("|---|---|---|---|---|")

    for orig_uid, orig_title, unique_f, dest_dash, status_mapping in matrix_mapping:
        lines_mat.append(f"| `{orig_uid}` | {orig_title} | {unique_f} | **{dest_dash}** | {status_mapping} |")

    lines_mat.append("")
    lines_mat.append("---")
    lines_mat.append("")
    lines_mat.append("## Consolidated 9-Dashboard Architecture Overview")
    lines_mat.append("")
    lines_mat.append("### Tier 1 — Executive Overview")
    lines_mat.append("1. **Enterprise Executive Overview** (`nawari-enterprise-overview`): Default Grafana Home dashboard. Overall service health, outstation availability, active incidents.")
    lines_mat.append("")
    lines_mat.append("### Tier 2 — Domain Overviews & Tier 3 Technology Deep-Dives")
    lines_mat.append("#### Network Observability Folder (`Nawari / Network Observability`)")
    lines_mat.append("2. **Network Operations Overview** (`nawari-network-operations`): Unifies Core Infrastructure, Interface Traffic, and Topology.")
    lines_mat.append("3. **WAN, Path & Outstation Observability** (`nawari-wan-path-outstation`): Unifies Global Outstations, Hop-by-Hop Path Tracing, and Edge Collector Fleet.")
    lines_mat.append("4. **Endpoint & User Experience** (`nawari-endpoint-experience`): Unifies Fleet Health, Single-Device Forensics, and Real-Time Active NEM Probes.")
    lines_mat.append("5. **Network Services & Incident Assurance** (`nawari-network-services-assurance`): Unifies Business Service SLIs/SLOs, Incident Operations, Predictive Baselines, and Controlled Operations.")
    lines_mat.append("")
    lines_mat.append("#### Communication Observability Folder (`Nawari / Communication Observability`)")
    lines_mat.append("6. **Communication Services Overview** (`nawari-comm-overview`): Unifies Executive Voice Assurance, Carrier Trunk summary, and Core Appliance health.")
    lines_mat.append("7. **Avaya Infrastructure & Signaling** (`nawari-avaya-infrastructure`): Unifies SBCE, Session Manager, Communication Manager, G450 Media Gateway, and Carrier SIP Trunks.")
    lines_mat.append("8. **Voice Quality & Contact Centre** (`nawari-voice-contact-centre`): Unifies Voice Intelligence Synthetic Probes, Media Stream Quality, CMS ACD Queues, and Verint WFO Compliance.")
    lines_mat.append("9. **Cross-Domain Correlation & Operations** (`nawari-voice-correlation`): Unifies Endpoint Wi-Fi Correlation, Voice Degradation Hypotheses, and Cross-Domain Incident Escalation.")

    (root / "docs/dashboards/dashboard-consolidation-matrix.md").write_text("\n".join(lines_mat), encoding="utf-8")
    print("Generated docs/dashboards/dashboard-consolidation-matrix.md")

if __name__ == "__main__":
    main()

