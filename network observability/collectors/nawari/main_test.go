package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func testConfig(target string) Config {
	return Config{EnrollmentID: "endpoint", ProducerID: "nawari-plugin", ObservationPointID: "endpoint",
		ServiceID: "portal", OperationID: "page", ConfigVersion: "v1", ExecutionContext: "fixture",
		URL: target, Intake: "http://127.0.0.1:18090/api/v1/evidence", TokenFile: "token", QueueDir: "queue", IntervalMS: 15000,
		TimeoutMS: 1000, ExpectedStatuses: []int{200}, Fixture: true, StructuredEvidence: true}
}

func TestMetricsOnlyConfigurationDoesNotRequireIntake(t *testing.T) {
	c := testConfig("http://127.0.0.1/")
	c.StructuredEvidence = false
	c.Intake = ""
	c.TokenFile = ""
	c.QueueDir = ""
	if err := c.validate(); err != nil {
		t.Fatal(err)
	}
}

func TestDNSObservationPolicyRequiresProtectedPathAndThreshold(t *testing.T) {
	c := testConfig("http://127.0.0.1/")
	c.StructuredEvidence = false
	c.DNSObservationPath = filepath.Join(t.TempDir(), "dns.ndjson")
	if c.validate() == nil {
		t.Fatal("DNS observation path accepted without threshold")
	}
	c.DNSSlowThresholdMS = 1000
	if err := c.validate(); err != nil {
		t.Fatal(err)
	}
}

func TestDNSCorrelationPreservesUncertaintyAndClassifiesFailures(t *testing.T) {
	now := time.Now().UTC()
	apps := []ApplicationObservation{{Process: "Browser", DestinationIPs: []string{"192.0.2.10"}}}
	services := correlateServices(apps, []DNSObservation{
		{Domain: "portal.example", Addresses: []string{"192.0.2.10"}, ObservedAt: now, DurationMS: 1500, Status: "success"},
		{Domain: "dns.example", ObservedAt: now, Status: "SERVFAIL"},
	}, now, 1000)
	if len(services) != 2 || services[0].Classification != "critical" {
		t.Fatalf("unexpected services: %+v", services)
	}
	if services[1].Classification != "degraded" || services[1].Confidence != "probable" || services[1].Application != "Browser" {
		t.Fatalf("unexpected correlation: %+v", services[1])
	}
}

func TestDNSCorrelationMarksSharedAddressUnresolved(t *testing.T) {
	now := time.Now().UTC()
	apps := []ApplicationObservation{{Process: "Browser", DestinationIPs: []string{"2001:db8::10"}}}
	services := correlateServices(apps, []DNSObservation{
		{Domain: "cdn-a.example", Addresses: []string{"2001:db8::10"}, ObservedAt: now, Status: "success"},
		{Domain: "cdn-b.example", Addresses: []string{"2001:db8::10"}, ObservedAt: now, Status: "success"},
	}, now, 1000)
	for _, service := range services {
		if service.Confidence != "unresolved" {
			t.Fatalf("shared address was attributed: %+v", service)
		}
	}
}

func TestStructuredEvidenceRequiresSeparateSecurityConfiguration(t *testing.T) {
	c := testConfig("http://127.0.0.1/")
	c.Intake = ""
	if err := c.validate(); err == nil {
		t.Fatal("structured evidence accepted without intake configuration")
	}
}

func TestProbeResponseAndAbsentPhases(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/slow":
			time.Sleep(100 * time.Millisecond)
		case "/bad":
			w.WriteHeader(503)
		case "/redirect":
			http.Redirect(w, r, "/healthy", 302)
		}
		w.Write([]byte("fixture"))
	}))
	defer server.Close()
	for _, item := range []struct{ path, outcome string }{{"/healthy", "success"}, {"/slow", "success"}, {"/bad", "bad_status"}, {"/redirect", "bad_status"}} {
		t.Run(item.path, func(t *testing.T) {
			result := probe(context.Background(), testConfig(server.URL+item.path), nil)
			if result.TestResult != item.outcome {
				t.Fatalf("outcome %s", result.TestResult)
			}
			if result.Phases["dns"].State != "not_performed" || result.Phases["dns"].DurationMS != nil {
				t.Fatal("literal IP performed DNS")
			}
			if result.Phases["tls"].State != "not_performed" {
				t.Fatal("HTTP performed TLS")
			}
			if item.path == "/slow" && result.TotalMS < 90 {
				t.Fatal("delay not measured")
			}
		})
	}
}

func TestDNSConnectivityTLSAndTimeout(t *testing.T) {
	c := testConfig("http://fixture.invalid/")
	dns := probe(context.Background(), c, func(context.Context, string, string) (net.Conn, error) {
		return nil, &net.DNSError{Err: "fixture", Name: "fixture.invalid", IsNotFound: true}
	})
	if dns.TestResult != "dns_failure" {
		t.Fatal(dns.TestResult)
	}
	connection := probe(context.Background(), c, func(context.Context, string, string) (net.Conn, error) { return nil, errors.New("fixture") })
	if connection.TestResult != "connectivity_failure" {
		t.Fatal(connection.TestResult)
	}
	tlsServer := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	defer tlsServer.Close()
	tlsResult := probe(context.Background(), testConfig(tlsServer.URL), nil)
	if tlsResult.TestResult != "tls_failure" {
		t.Fatal(tlsResult.TestResult)
	}
	slow := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { time.Sleep(200 * time.Millisecond) }))
	defer slow.Close()
	c = testConfig(slow.URL)
	c.TimeoutMS = 100
	if result := probe(context.Background(), c, nil); result.TestResult != "timeout" {
		t.Fatal(result.TestResult)
	}
}

func TestProtocolDoesNotInventPhases(t *testing.T) {
	result := Result{TotalMS: 12, TestResult: "success", Phases: map[string]Phase{}}
	var output bytes.Buffer
	c := testConfig("http://127.0.0.1/")
	emitHeader(&output, c)
	emit(&output, c, result, NetworkContext{}, Diagnostics{})
	if !strings.Contains(output.String(), "SET dns =\n") || strings.Contains(output.String(), "http://") {
		t.Fatal(output.String())
	}
}

func TestDurableQueueReceiptsExpiryAndAmbiguity(t *testing.T) {
	for _, status := range []string{"accepted", "duplicate", "invalid", "conflict", "retryable"} {
		t.Run(status, func(t *testing.T) {
			dir := t.TempDir()
			c := testConfig("http://127.0.0.1/")
			c.QueueDir = dir
			c.TokenFile = filepath.Join(t.TempDir(), "token")
			os.WriteFile(c.TokenFile, []byte(strings.Repeat("t", 36)), 0600)
			var received string
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				var batch []map[string]any
				json.NewDecoder(r.Body).Decode(&batch)
				received = batch[0]["record_id"].(string)
				json.NewEncoder(w).Encode(map[string]any{"results": []map[string]string{{"record_id": received, "status": status}}})
			}))
			defer server.Close()
			c.Intake = server.URL
			now := time.Now()
			value := record(c, Result{}, now)
			if err := enqueue(dir, value, now); err != nil {
				t.Fatal(err)
			}
			drain(context.Background(), c, server.Client(), now)
			files, _ := filepath.Glob(filepath.Join(dir, "*.json"))
			if (len(files) == 1) != (status == "retryable") {
				t.Fatal(status, len(files))
			}
			if status == "retryable" {
				drain(context.Background(), c, server.Client(), now)
				if received != value["record_id"] {
					t.Fatal("ID changed")
				}
			}
			if err := enqueue(dir, record(c, Result{}, now), now.Add(-25*time.Hour)); err != nil {
				t.Fatal(err)
			}
			_, dropped := drain(context.Background(), c, server.Client(), now)
			if dropped < 1 {
				t.Fatal("expired copy retained")
			}
		})
	}
}

func TestFixtureDestinationBoundary(t *testing.T) {
	c := testConfig("https://example.com/")
	if c.validate() == nil {
		t.Fatal("external fixture allowed")
	}
	c = testConfig("http://127.0.0.1/")
	if err := c.validate(); err != nil {
		t.Fatal(err)
	}
	c.ExecutionContext = "employee"
	if c.validate() == nil {
		t.Fatal("unsupported session claimed")
	}
}

func TestContextRecordPreservesUnavailableState(t *testing.T) {
	c := testConfig("http://127.0.0.1/")
	observed := time.Now()
	value := contextRecord(c, observed, NetworkContext{Interface: "lo0", InterfaceType: "loopback", LocalIP: "127.0.0.1",
		Resolvers: []string{"127.0.0.1"}, WiFiState: "unknown", VPNState: "disconnected", SystemProxy: "not_configured",
		Unavailable: []string{"wifi"}})
	if value["collection_outcome"] != "partial" || value["payload_type"] != "network_context" {
		t.Fatal(value)
	}
	payload := value["payload"].(map[string]any)
	if payload["wifi_state"] != "unknown" || payload["interface"] != "lo0" {
		t.Fatal(payload)
	}
}

func TestDrainBatchesServiceAndContextInOneRequest(t *testing.T) {
	directory := t.TempDir()
	c := testConfig("http://127.0.0.1/")
	c.QueueDir = directory
	c.TokenFile = filepath.Join(t.TempDir(), "token")
	if err := os.WriteFile(c.TokenFile, []byte(strings.Repeat("t", 36)), 0600); err != nil {
		t.Fatal(err)
	}
	requests := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests++
		var batch []map[string]any
		if err := json.NewDecoder(r.Body).Decode(&batch); err != nil || len(batch) != 2 {
			t.Fatalf("batch: %v %d", err, len(batch))
		}
		results := make([]map[string]string, 0, len(batch))
		for _, item := range batch {
			results = append(results, map[string]string{"record_id": item["record_id"].(string), "status": "accepted"})
		}
		json.NewEncoder(w).Encode(map[string]any{"results": results})
	}))
	defer server.Close()
	c.Intake = server.URL
	now := time.Now()
	if err := enqueue(directory, record(c, Result{}, now), now); err != nil {
		t.Fatal(err)
	}
	if err := enqueue(directory, contextRecord(c, now, NetworkContext{}), now); err != nil {
		t.Fatal(err)
	}
	delivered, dropped := drain(context.Background(), c, server.Client(), now)
	if requests != 1 || delivered != 2 || dropped != 0 {
		t.Fatalf("requests=%d delivered=%d dropped=%d", requests, delivered, dropped)
	}
}

func TestDefaultConfigUsesNetdataConfigDirectory(t *testing.T) {
	t.Setenv("NAWARI_COLLECTOR_CONFIG", "")
	t.Setenv("NETDATA_USER_CONFIG_DIR", t.TempDir())
	if filepath.Base(defaultConfigPath()) != "nawari-collector.json" {
		t.Fatal(defaultConfigPath())
	}
}
