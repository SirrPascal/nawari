// SPDX-License-Identifier: GPL-3.0-or-later
// nawari.plugin is a compiled plugins.d collector managed by the Netdata lifecycle.
package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptrace"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

const maxQueueBytes = 8 * 1024 * 1024
const maxQueueAge = 24 * time.Hour

var idPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$`)

type Config struct {
	EnrollmentID                   string `json:"enrollment_id"`
	ProducerID                     string `json:"producer_id"`
	ObservationPointID             string `json:"observation_point_id"`
	ServiceID                      string `json:"service_id"`
	OperationID                    string `json:"operation_id"`
	ConfigVersion                  string `json:"config_version"`
	ExecutionContext               string `json:"execution_context"`
	URL                            string `json:"url"`
	Intake                         string `json:"intake"`
	TokenFile                      string `json:"token_file"`
	CAFile                         string `json:"ca_file"`
	QueueDir                       string `json:"queue_dir"`
	IntervalMS                     int    `json:"interval_ms"`
	JitterMS                       int    `json:"jitter_ms"`
	TimeoutMS                      int    `json:"timeout_ms"`
	ExpectedStatuses               []int  `json:"expected_statuses"`
	Fixture                        bool   `json:"fixture"`
	StructuredEvidence             bool   `json:"structured_evidence_enabled"`
	DNSTestName                    string `json:"dns_test_name"`
	ICMPTarget                     string `json:"icmp_target"`
	PathEnabled                    bool   `json:"path_enabled"`
	PathIntervalMS                 int    `json:"path_interval_ms"`
	PathMaxHops                    int    `json:"path_max_hops"`
	ApplicationDiscoveryEnabled    bool   `json:"application_discovery_enabled"`
	ApplicationDiscoveryIntervalMS int    `json:"application_discovery_interval_ms"`
	ApplicationDiscoveryMaxApps    int    `json:"application_discovery_max_apps"`
	DNSObservationPath             string `json:"dns_observation_path"`
	DNSSlowThresholdMS             int    `json:"dns_slow_threshold_ms"`
}

func (c Config) validate() error {
	for _, value := range []string{c.EnrollmentID, c.ProducerID, c.ObservationPointID, c.ServiceID, c.OperationID, c.ConfigVersion} {
		if !idPattern.MatchString(value) {
			return errors.New("invalid configured identity")
		}
	}
	if c.IntervalMS < 1000 || c.IntervalMS > 3600000 || c.TimeoutMS < 100 || c.TimeoutMS > 30000 || c.TimeoutMS > c.IntervalMS || c.JitterMS < 0 || c.JitterMS > c.IntervalMS {
		return errors.New("invalid request budget")
	}
	if len(c.ExpectedStatuses) == 0 {
		return errors.New("expected statuses required")
	}
	for _, status := range c.ExpectedStatuses {
		if status < 100 || status > 599 {
			return errors.New("invalid expected status")
		}
	}
	for _, target := range []string{c.DNSTestName, c.ICMPTarget} {
		if target != "" && !validProbeHost(target) {
			return errors.New("invalid diagnostic target")
		}
	}
	if c.PathEnabled && (c.PathIntervalMS < 300000 || c.PathIntervalMS > 86400000 || c.PathMaxHops < 1 || c.PathMaxHops > 16) {
		return errors.New("invalid bounded path policy")
	}
	if c.ApplicationDiscoveryEnabled && (c.ApplicationDiscoveryIntervalMS < 60000 || c.ApplicationDiscoveryIntervalMS > 900000 || c.ApplicationDiscoveryMaxApps < 1 || c.ApplicationDiscoveryMaxApps > 16) {
		return errors.New("invalid application discovery policy")
	}
	if c.DNSObservationPath != "" && (len(c.DNSObservationPath) > 1024 || c.DNSSlowThresholdMS < 1 || c.DNSSlowThresholdMS > 30000) {
		return errors.New("invalid DNS observation policy")
	}
	destinations := []string{c.URL}
	if c.StructuredEvidence {
		if c.Intake == "" || c.TokenFile == "" || c.QueueDir == "" {
			return errors.New("structured evidence configuration incomplete")
		}
		destinations = append(destinations, c.Intake)
	}
	for _, raw := range destinations {
		u, err := url.Parse(raw)
		if err != nil || u.Hostname() == "" || u.User != nil || u.Fragment != "" {
			return errors.New("invalid destination")
		}
		if c.Fixture {
			ip := net.ParseIP(u.Hostname())
			if u.Scheme != "http" || ip == nil || !ip.IsLoopback() {
				return errors.New("fixtures require literal loopback HTTP destinations")
			}
		} else if u.Scheme != "https" {
			return errors.New("managed destinations require verified HTTPS")
		}
	}
	if c.ExecutionContext != "system" && !(c.Fixture && c.ExecutionContext == "fixture") {
		return errors.New("unsupported execution context")
	}
	return nil
}

type Phase struct {
	State      string   `json:"state"`
	DurationMS *float64 `json:"duration_ms"`
}

type Result struct {
	TestResult string           `json:"test_result"`
	TotalMS    float64          `json:"total_ms"`
	Phases     map[string]Phase `json:"phases"`
	HTTPStatus int              `json:"http_status,omitempty"`
	ProxyMode  string           `json:"proxy_mode"`
	LocalIP    string           `json:"local_ip,omitempty"`
	BodyBytes  int64            `json:"body_bytes"`
	CertDays   *int             `json:"certificate_days_remaining,omitempty"`
}

func validProbeHost(value string) bool {
	if net.ParseIP(value) != nil {
		return true
	}
	return idPattern.MatchString(value) && !strings.ContainsAny(value, "/:@")
}

func milliseconds(duration time.Duration) float64 {
	return float64(duration.Microseconds()) / 1000
}

// Each operation uses a fresh direct connection, no redirects and a bounded body.
// TTFB is measured from request start. Phase times can overlap and must not be summed.
func probe(ctx context.Context, c Config, dial func(context.Context, string, string) (net.Conn, error), roots ...*x509.CertPool) Result {
	result := Result{TestResult: "success", ProxyMode: "direct", Phases: map[string]Phase{}}
	for _, name := range []string{"dns", "connect", "tls", "ttfb"} {
		result.Phases[name] = Phase{State: "not_performed"}
	}
	var mu sync.Mutex
	starts := map[string]time.Time{}
	failed := ""
	start := time.Now()
	begin := func(name string) {
		mu.Lock()
		defer mu.Unlock()
		starts[name] = time.Now()
	}
	end := func(name string, err error) {
		mu.Lock()
		defer mu.Unlock()
		duration := milliseconds(time.Since(starts[name]))
		state := "performed"
		if err != nil {
			state = "failed"
			failed = name
		}
		result.Phases[name] = Phase{State: state, DurationMS: &duration}
	}
	trace := &httptrace.ClientTrace{
		DNSStart:          func(httptrace.DNSStartInfo) { begin("dns") },
		DNSDone:           func(info httptrace.DNSDoneInfo) { end("dns", info.Err) },
		ConnectStart:      func(_, _ string) { begin("connect") },
		ConnectDone:       func(_, _ string, err error) { end("connect", err) },
		TLSHandshakeStart: func() { begin("tls") },
		TLSHandshakeDone: func(state tls.ConnectionState, err error) {
			end("tls", err)
			if err == nil && len(state.PeerCertificates) > 0 {
				days := int(time.Until(state.PeerCertificates[0].NotAfter).Hours() / 24)
				result.CertDays = &days
			}
		},
		GotFirstResponseByte: func() {
			mu.Lock()
			defer mu.Unlock()
			duration := milliseconds(time.Since(start))
			result.Phases["ttfb"] = Phase{State: "performed", DurationMS: &duration}
		},
		GotConn: func(info httptrace.GotConnInfo) {
			mu.Lock()
			defer mu.Unlock()
			if address, ok := info.Conn.LocalAddr().(*net.TCPAddr); ok {
				result.LocalIP = address.IP.String()
			}
		},
	}
	if dial == nil {
		dialer := &net.Dialer{Timeout: time.Duration(c.TimeoutMS) * time.Millisecond, FallbackDelay: -1}
		dial = dialer.DialContext
	}
	tlsConfig := &tls.Config{MinVersion: tls.VersionTLS12}
	if len(roots) > 0 {
		tlsConfig.RootCAs = roots[0]
	}
	transport := &http.Transport{DialContext: dial, DisableKeepAlives: true, MaxResponseHeaderBytes: 32768,
		TLSHandshakeTimeout: time.Duration(c.TimeoutMS) * time.Millisecond, TLSClientConfig: tlsConfig}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: time.Duration(c.TimeoutMS) * time.Millisecond,
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	request, err := http.NewRequestWithContext(httptrace.WithClientTrace(ctx, trace), http.MethodGet, c.URL, nil)
	if err != nil {
		result.TestResult = "connectivity_failure"
		return result
	}
	response, err := client.Do(request)
	if err == nil {
		result.HTTPStatus = response.StatusCode
		result.BodyBytes, err = io.Copy(io.Discard, io.LimitReader(response.Body, 65537))
		response.Body.Close()
		if result.BodyBytes > 65536 {
			result.TestResult = "bad_content"
		}
		accepted := false
		for _, status := range c.ExpectedStatuses {
			accepted = accepted || status == response.StatusCode
		}
		if !accepted {
			result.TestResult = "bad_status"
		}
	}
	// Transport callbacks finish before Do returns. The lock also protects injected test dialers.
	mu.Lock()
	defer mu.Unlock()
	if err != nil {
		result.TestResult = "connectivity_failure"
		var dns *net.DNSError
		var network net.Error
		switch {
		case errors.As(err, &dns):
			result.TestResult = "dns_failure"
		case failed == "tls":
			result.TestResult = "tls_failure"
		case errors.As(err, &network) && network.Timeout():
			result.TestResult = "timeout"
		}
	}
	result.TotalMS = milliseconds(time.Since(start))
	return result
}

func record(c Config, result Result, observed time.Time) map[string]any {
	identifier := randomID()
	return map[string]any{"schema_version": "1", "payload_type": "service_test", "record_id": identifier,
		"producer_id": c.ProducerID, "enrollment_id": c.EnrollmentID, "observation_point_id": c.ObservationPointID,
		"observed_at": observed.UTC().Format(time.RFC3339Nano), "config_version": c.ConfigVersion,
		"service_id": c.ServiceID, "operation_id": c.OperationID, "run_id": identifier,
		"execution_context": c.ExecutionContext, "collection_interval_ms": c.IntervalMS,
		"collection_outcome": "complete", "payload": result}
}

func contextRecord(c Config, observed time.Time, snapshot NetworkContext) map[string]any {
	identifier := randomID()
	outcome := "complete"
	if len(snapshot.Unavailable) > 0 {
		outcome = "partial"
	}
	payload := map[string]any{
		"context_kind":           "system_network",
		"effective_from":         observed.UTC().Format(time.RFC3339Nano),
		"effective_until":        observed.Add(max(time.Duration(c.IntervalMS*2)*time.Millisecond, time.Minute)).UTC().Format(time.RFC3339Nano),
		"interface":              snapshot.Interface,
		"interface_type":         snapshot.InterfaceType,
		"default_interface":      snapshot.DefaultInterface,
		"default_interface_type": snapshot.DefaultInterfaceType,
		"local_ip":               snapshot.LocalIP,
		"gateway":                snapshot.Gateway,
		"resolvers":              snapshot.Resolvers,
		"wifi_state":             snapshot.WiFiState,
		"wifi_ssid_hash":         snapshot.WiFiSSIDHash,
		"vpn_state":              snapshot.VPNState,
		"vpn_interfaces":         snapshot.VPNInterfaces,
		"system_proxy":           snapshot.SystemProxy,
		"probe_proxy_mode":       "direct",
		"unavailable":            snapshot.Unavailable,
	}
	return map[string]any{"schema_version": "1", "payload_type": "network_context", "record_id": identifier,
		"producer_id": c.ProducerID, "enrollment_id": c.EnrollmentID, "observation_point_id": c.ObservationPointID,
		"observed_at": observed.UTC().Format(time.RFC3339Nano), "config_version": c.ConfigVersion,
		"collection_outcome": outcome, "payload": payload}
}

func randomID() string {
	var data [16]byte
	if _, err := rand.Read(data[:]); err != nil {
		panic("cryptographic random source unavailable")
	}
	return hex.EncodeToString(data[:])
}

type queued struct {
	Created time.Time      `json:"created"`
	Record  map[string]any `json:"record"`
}

func enqueue(directory string, value map[string]any, now time.Time) error {
	if err := os.MkdirAll(directory, 0700); err != nil {
		return err
	}
	content, err := json.Marshal(queued{Created: now, Record: value})
	if err != nil {
		return err
	}
	files, err := filepath.Glob(filepath.Join(directory, "*.json"))
	if err != nil {
		return err
	}
	total := int64(len(content))
	for _, file := range files {
		info, err := os.Stat(file)
		if err != nil {
			return err
		}
		total += info.Size()
	}
	if total > maxQueueBytes {
		return errors.New("queue byte budget reached")
	}
	temporary, err := os.CreateTemp(directory, ".pending-")
	if err != nil {
		return err
	}
	defer os.Remove(temporary.Name())
	_, err = temporary.Write(content)
	if err == nil {
		err = temporary.Sync()
	}
	closeErr := temporary.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	return os.Rename(temporary.Name(), filepath.Join(directory, value["record_id"].(string)+".json"))
}

func drain(ctx context.Context, c Config, client *http.Client, now time.Time) (int, int) {
	files, _ := filepath.Glob(filepath.Join(c.QueueDir, "*.json"))
	sort.Strings(files)
	delivered, dropped := 0, 0
	type candidate struct {
		file   string
		record map[string]any
	}
	var batch []candidate
	batchBytes := 0
	for _, file := range files {
		content, err := os.ReadFile(file)
		var item queued
		if err != nil || len(content) > 32768 || json.Unmarshal(content, &item) != nil || now.Before(item.Created) || now.Sub(item.Created) >= maxQueueAge {
			os.Remove(file)
			dropped++
			continue
		}
		if len(batch) < 8 && batchBytes+len(content) <= 200*1024 {
			batch = append(batch, candidate{file: file, record: item.Record})
			batchBytes += len(content)
		}
	}
	if len(batch) == 0 {
		return delivered, dropped
	}
	token, err := os.ReadFile(c.TokenFile)
	if err != nil {
		return delivered, dropped
	}
	records := make([]map[string]any, 0, len(batch))
	byID := make(map[string]string, len(batch))
	for _, item := range batch {
		identifier, ok := item.record["record_id"].(string)
		if !ok {
			continue
		}
		records = append(records, item.record)
		byID[identifier] = item.file
	}
	payload, _ := json.Marshal(records)
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, c.Intake, bytes.NewReader(payload))
	if err != nil {
		return delivered, dropped
	}
	request.Header.Set("Authorization", "Bearer "+strings.TrimSpace(string(token)))
	request.Header.Set("Content-Type", "application/json")
	response, err := client.Do(request)
	if err != nil {
		return delivered, dropped
	}
	var answer struct {
		Results []struct {
			RecordID string `json:"record_id"`
			Status   string `json:"status"`
		} `json:"results"`
	}
	err = json.NewDecoder(io.LimitReader(response.Body, 32768)).Decode(&answer)
	response.Body.Close()
	if response.StatusCode != 200 || err != nil || len(answer.Results) != len(records) {
		return delivered, dropped
	}
	for _, receipt := range answer.Results {
		file, exists := byID[receipt.RecordID]
		if !exists {
			return delivered, dropped
		}
		switch receipt.Status {
		case "accepted", "duplicate":
			os.Remove(file)
			delivered++
		case "expired", "invalid", "conflict", "unauthorized":
			os.Remove(file)
			dropped++
		case "retryable":
		default:
			return delivered, dropped
		}
		delete(byID, receipt.RecordID)
	}
	return delivered, dropped
}

func emitHeader(w io.Writer, c Config) {
	fmt.Fprintf(w, "CHART nawari.%s_%s '' 'Service request phases' 'milliseconds' 'experience' 'nawari.request_phases' line 1000 %d\n", c.ServiceID, c.OperationID, c.IntervalMS/1000)
	for _, name := range []string{"dns", "connect", "tls", "ttfb", "total"} {
		fmt.Fprintf(w, "DIMENSION %s '' absolute 1 1000\n", name)
	}
	fmt.Fprintf(w, "CHART nawari.%s_%s_status '' 'Service request result' 'state' 'experience' 'nawari.request_status' line 1001 %d\nDIMENSION success '' absolute 1 1\nDIMENSION failure '' absolute 1 1\n", c.ServiceID, c.OperationID, c.IntervalMS/1000)
	fmt.Fprintf(w, "CHART nawari.%s_%s_latency '' 'Network diagnostic latency' 'milliseconds' 'experience' 'nawari.network_latency' line 1002 %d\n", c.ServiceID, c.OperationID, c.IntervalMS/1000)
	for _, name := range []string{"dns_lookup", "icmp_target", "gateway"} {
		fmt.Fprintf(w, "DIMENSION %s '' absolute 1 1000\n", name)
	}
	fmt.Fprintf(w, "CHART nawari.%s_%s_loss '' 'Network diagnostic packet loss' 'percent' 'experience' 'nawari.network_loss' line 1003 %d\nDIMENSION icmp_target '' absolute 1 1000\nDIMENSION gateway '' absolute 1 1000\n", c.ServiceID, c.OperationID, c.IntervalMS/1000)
	fmt.Fprintf(w, "CHART nawari.%s_%s_context '' 'Endpoint network context state' 'state' 'experience' 'nawari.network_context' line 1004 %d\n", c.ServiceID, c.OperationID, c.IntervalMS/1000)
	for _, name := range []string{"dns_success", "gateway_reachable", "target_reachable", "wifi_connected", "vpn_connected", "proxy_configured", "interface_wifi", "interface_ethernet", "interface_tunnel"} {
		fmt.Fprintf(w, "DIMENSION %s '' absolute 1 1\n", name)
	}
	fmt.Fprintf(w, "CHART nawari.%s_%s_wifi '' 'Wi-Fi radio metrics' 'dBm' 'experience' 'nawari.wifi_radio' line 1005 %d\nDIMENSION signal '' absolute 1 1\nDIMENSION noise '' absolute 1 1\n", c.ServiceID, c.OperationID, c.IntervalMS/1000)
	fmt.Fprintf(w, "CHART nawari.%s_%s_tls_certificate '' 'TLS certificate validity' 'days' 'experience' 'nawari.tls_certificate' line 1006 %d\nDIMENSION days_remaining '' absolute 1 1\n", c.ServiceID, c.OperationID, c.IntervalMS/1000)
	fmt.Fprintf(w, "CHART nawari.%s_%s_path '' 'Bounded destination path' 'value' 'experience' 'nawari.path' line 1007 %d\nDIMENSION hops '' absolute 1 1\nDIMENSION reached '' absolute 1 1\nDIMENSION duration_ms '' absolute 1 1000\nDIMENSION age_seconds '' absolute 1 1\n", c.ServiceID, c.OperationID, c.IntervalMS/1000)
	if c.ApplicationDiscoveryEnabled {
		fmt.Fprintf(w, "CHART nawari.application_network '' 'Passive application and service inventory' 'observations' 'applications' 'nawari.application_network' line 1008 %d\nDIMENSION applications '' absolute 1 1\nDIMENSION established_connections '' absolute 1 1\nDIMENSION interfaces '' absolute 1 1\nDIMENSION sampled_apps '' absolute 1 1\nDIMENSION discovery_errors '' absolute 1 1\nDIMENSION dns_observations '' absolute 1 1\nDIMENSION dns_failures '' absolute 1 1\nDIMENSION dns_slow '' absolute 1 1\nDIMENSION services_correlated '' absolute 1 1\nDIMENSION services_degraded '' absolute 1 1\nDIMENSION catalog_stale '' absolute 1 1\n", c.ApplicationDiscoveryIntervalMS/1000)
	}
}

func emitOptionalFloat(w io.Writer, name string, value *float64) {
	if value == nil {
		fmt.Fprintf(w, "SET %s =\n", name)
		return
	}
	fmt.Fprintf(w, "SET %s = %d\n", name, int64(*value*1000))
}

func emitOptionalInt(w io.Writer, name string, value *int) {
	if value == nil {
		fmt.Fprintf(w, "SET %s =\n", name)
		return
	}
	fmt.Fprintf(w, "SET %s = %d\n", name, *value)
}

func boolValue(value *bool) string {
	if value == nil {
		return ""
	}
	if *value {
		return "1"
	}
	return "0"
}

func stateValue(value, positive string) string {
	if value == "unknown" || value == "" {
		return ""
	}
	if value == positive {
		return "1"
	}
	return "0"
}

func interfaceValue(value, expected string) string {
	if value == "unknown" || value == "" || value == "physical" {
		return ""
	}
	if value == expected {
		return "1"
	}
	return "0"
}

func emit(w io.Writer, c Config, result Result, snapshot NetworkContext, diagnostics Diagnostics) {
	fmt.Fprintf(w, "BEGIN nawari.%s_%s\n", c.ServiceID, c.OperationID)
	for _, name := range []string{"dns", "connect", "tls", "ttfb"} {
		phase := result.Phases[name]
		if phase.DurationMS != nil {
			fmt.Fprintf(w, "SET %s = %d\n", name, int64(*phase.DurationMS*1000))
		} else {
			fmt.Fprintf(w, "SET %s =\n", name)
		}
	}
	fmt.Fprintf(w, "SET total = %d\nEND\n", int64(result.TotalMS*1000))
	success := 0
	if result.TestResult == "success" {
		success = 1
	}
	fmt.Fprintf(w, "BEGIN nawari.%s_%s_status\nSET success = %d\nSET failure = %d\nEND\n", c.ServiceID, c.OperationID, success, 1-success)
	fmt.Fprintf(w, "BEGIN nawari.%s_%s_latency\n", c.ServiceID, c.OperationID)
	emitOptionalFloat(w, "dns_lookup", diagnostics.DNSLookupMS)
	emitOptionalFloat(w, "icmp_target", diagnostics.TargetRTTMS)
	emitOptionalFloat(w, "gateway", diagnostics.GatewayRTTMS)
	fmt.Fprintln(w, "END")
	fmt.Fprintf(w, "BEGIN nawari.%s_%s_loss\n", c.ServiceID, c.OperationID)
	emitOptionalFloat(w, "icmp_target", diagnostics.TargetLossPct)
	emitOptionalFloat(w, "gateway", diagnostics.GatewayLossPct)
	fmt.Fprintln(w, "END")
	gatewayReachable := (*bool)(nil)
	if diagnostics.GatewayLossPct != nil {
		value := *diagnostics.GatewayLossPct < 100
		gatewayReachable = &value
	}
	targetReachable := (*bool)(nil)
	if diagnostics.TargetLossPct != nil {
		value := *diagnostics.TargetLossPct < 100
		targetReachable = &value
	}
	channelType := snapshot.DefaultInterfaceType
	if channelType == "" {
		channelType = snapshot.InterfaceType
	}
	fmt.Fprintf(w, "BEGIN nawari.%s_%s_context\nSET dns_success = %s\nSET gateway_reachable = %s\nSET target_reachable = %s\nSET wifi_connected = %s\nSET vpn_connected = %s\nSET proxy_configured = %s\nSET interface_wifi = %s\nSET interface_ethernet = %s\nSET interface_tunnel = %s\nEND\n",
		c.ServiceID, c.OperationID, boolValue(diagnostics.DNSLookupOK), boolValue(gatewayReachable), boolValue(targetReachable),
		stateValue(snapshot.WiFiState, "connected"), stateValue(snapshot.VPNState, "connected"), stateValue(snapshot.SystemProxy, "configured"),
		interfaceValue(channelType, "wifi"), interfaceValue(channelType, "ethernet"), interfaceValue(channelType, "tunnel"))
	fmt.Fprintf(w, "BEGIN nawari.%s_%s_wifi\n", c.ServiceID, c.OperationID)
	emitOptionalInt(w, "signal", diagnostics.WiFiSignalDBM)
	emitOptionalInt(w, "noise", diagnostics.WiFiNoiseDBM)
	fmt.Fprintln(w, "END")
	fmt.Fprintf(w, "BEGIN nawari.%s_%s_tls_certificate\n", c.ServiceID, c.OperationID)
	emitOptionalInt(w, "days_remaining", result.CertDays)
	fmt.Fprintln(w, "END")
	fmt.Fprintf(w, "BEGIN nawari.%s_%s_path\n", c.ServiceID, c.OperationID)
	emitOptionalInt(w, "hops", diagnostics.PathHops)
	fmt.Fprintf(w, "SET reached = %s\n", boolValue(diagnostics.PathReached))
	emitOptionalFloat(w, "duration_ms", diagnostics.PathDurationMS)
	emitOptionalInt(w, "age_seconds", diagnostics.PathAgeSeconds)
	fmt.Fprintln(w, "END")
}

func emitApplicationSnapshot(w io.Writer, snapshot ApplicationSnapshot) {
	fmt.Fprintf(w, "BEGIN nawari.application_network\nSET applications = %d\nSET established_connections = %d\nSET interfaces = %d\nSET sampled_apps = %d\nSET discovery_errors = %d\nSET dns_observations = %d\nSET dns_failures = %d\nSET dns_slow = %d\nSET services_correlated = %d\nSET services_degraded = %d\nSET catalog_stale = %d\nEND\n",
		len(snapshot.Applications), snapshot.EstablishedConnections, snapshot.Interfaces, len(snapshot.Applications), snapshot.Errors,
		snapshot.DNSObservations, snapshot.DNSFailures, snapshot.DNSSlow, len(snapshot.Services), countDegraded(snapshot.Services), boolToInt(snapshot.CatalogStale))
}

func countDegraded(services []ServiceObservation) int {
	count := 0
	for _, service := range services {
		if service.Classification == "degraded" || service.Classification == "critical" {
			count++
		}
	}
	return count
}

func boolToInt(value bool) int {
	if value {
		return 1
	}
	return 0
}

func main() {
	configPath := flag.String("config", defaultConfigPath(), "approved configuration path")
	once := flag.Bool("once", false, "collect once for isolated validation")
	flag.Parse()
	// Netdata passes an update interval as the first positional argument. The manifest owns the request budget.
	if *configPath == "" {
		fmt.Fprintln(os.Stderr, "approved collector configuration required")
		os.Exit(1)
	}
	content, err := os.ReadFile(*configPath)
	var c Config
	if err != nil || len(content) > 16384 || json.Unmarshal(content, &c) != nil || c.validate() != nil {
		fmt.Fprintln(os.Stderr, "invalid collector configuration")
		os.Exit(1)
	}
	tlsConfig := &tls.Config{MinVersion: tls.VersionTLS12}
	if c.CAFile != "" {
		pem, err := os.ReadFile(c.CAFile)
		pool, poolErr := x509.SystemCertPool()
		if poolErr != nil {
			pool = x509.NewCertPool()
		}
		if err != nil || !pool.AppendCertsFromPEM(pem) {
			fmt.Fprintln(os.Stderr, "invalid intake trust configuration")
			os.Exit(1)
		}
		tlsConfig.RootCAs = pool
	}
	client := &http.Client{Timeout: 5 * time.Second, Transport: &http.Transport{TLSClientConfig: tlsConfig},
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	fmt.Fprintf(os.Stderr, "collector started config_version=%s structured_evidence=%t path_enabled=%t\n", c.ConfigVersion, c.StructuredEvidence, c.PathEnabled)
	emitHeader(os.Stdout, c)
	var lastPath time.Time
	var cachedPath Diagnostics
	var lastApplicationDiscovery time.Time
	var cachedApplications ApplicationSnapshot
	for {
		observed := time.Now()
		result := probe(ctx, c, nil, tlsConfig.RootCAs)
		snapshot := collectNetworkContext(ctx, c, result.LocalIP)
		runPath := c.PathEnabled && (lastPath.IsZero() || observed.Sub(lastPath) >= time.Duration(c.PathIntervalMS)*time.Millisecond || result.TestResult != "success")
		diagnostics := collectDiagnostics(ctx, c, snapshot, runPath)
		if runPath {
			lastPath = observed
			age := 0
			diagnostics.PathAgeSeconds = &age
			cachedPath.PathHops = diagnostics.PathHops
			cachedPath.PathReached = diagnostics.PathReached
			cachedPath.PathDurationMS = diagnostics.PathDurationMS
			cachedPath.PathAgeSeconds = diagnostics.PathAgeSeconds
			cachedPath.PathUnavailable = diagnostics.PathUnavailable
			fmt.Fprintf(os.Stderr, "bounded path attempted available=%t\n", !diagnostics.PathUnavailable)
		} else if !lastPath.IsZero() {
			age := int(observed.Sub(lastPath).Seconds())
			diagnostics.PathHops = cachedPath.PathHops
			diagnostics.PathReached = cachedPath.PathReached
			diagnostics.PathDurationMS = cachedPath.PathDurationMS
			diagnostics.PathAgeSeconds = &age
			diagnostics.PathUnavailable = cachedPath.PathUnavailable
		}
		emit(os.Stdout, c, result, snapshot, diagnostics)
		if c.ApplicationDiscoveryEnabled && (lastApplicationDiscovery.IsZero() || observed.Sub(lastApplicationDiscovery) >= time.Duration(c.ApplicationDiscoveryIntervalMS)*time.Millisecond) {
			cachedApplications = discoverApplications(ctx, c, snapshot)
			if c.DNSObservationPath != "" {
				observations, errors := loadDNSObservations(c.DNSObservationPath, observed)
				cachedApplications.DNSObservations = len(observations)
				cachedApplications.DNSErrorCount = errors
				cachedApplications.DNSFailures = countDNSFailures(observations)
				cachedApplications.DNSSlow = countDNSSlow(observations, c.DNSSlowThresholdMS)
				cachedApplications.Services = correlateServices(cachedApplications.Applications, observations, observed, c.DNSSlowThresholdMS)
			}
			lastApplicationDiscovery = observed
			if err := writeApplicationCatalog(filepath.Join(filepath.Dir(*configPath), "nawari-application-catalog.json"), cachedApplications); err != nil {
				fmt.Fprintln(os.Stderr, "application catalog update failed")
			}
		}
		if c.ApplicationDiscoveryEnabled {
			emitApplicationSnapshot(os.Stdout, cachedApplications)
		}
		if c.StructuredEvidence {
			if err := enqueue(c.QueueDir, record(c, result, observed), observed); err != nil {
				fmt.Fprintln(os.Stderr, "collector evidence queue admission failed")
			}
			if err := enqueue(c.QueueDir, contextRecord(c, observed, snapshot), observed); err != nil {
				fmt.Fprintln(os.Stderr, "collector network context queue admission failed")
			}
			_, dropped := drain(ctx, c, client, time.Now())
			if dropped > 0 {
				fmt.Fprintln(os.Stderr, "collector evidence records expired or rejected")
			}
		}
		if *once {
			return
		}
		jitter := 0
		if c.JitterMS > 0 {
			value, _ := strconv.ParseUint(randomID()[:8], 16, 32)
			jitter = int(value % uint64(c.JitterMS+1))
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(time.Duration(c.IntervalMS+jitter) * time.Millisecond):
		}
	}
}
