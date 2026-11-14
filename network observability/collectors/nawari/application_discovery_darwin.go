//go:build darwin

package main

import (
	"context"
	"encoding/json"
	"net"
	"os"
	"os/exec"
	"sort"
	"strings"
	"time"
)

type ApplicationObservation struct {
	Process        string    `json:"process"`
	Connections    int       `json:"established_connections"`
	Interface      string    `json:"interface"`
	DestinationIPs []string  `json:"destination_ips"`
	ObservedAt     time.Time `json:"observed_at"`
}

type ApplicationSnapshot struct {
	ObservedAt             time.Time                `json:"observed_at"`
	Applications           []ApplicationObservation `json:"applications"`
	EstablishedConnections int                      `json:"established_connections"`
	Interfaces             int                      `json:"interfaces"`
	Errors                 int                      `json:"discovery_errors"`
	DNSObservations        int                      `json:"dns_observations"`
	DNSErrorCount          int                      `json:"dns_errors"`
	DNSFailures            int                      `json:"dns_failures"`
	DNSSlow                int                      `json:"dns_slow"`
	Services               []ServiceObservation     `json:"services"`
	CatalogStale           bool                     `json:"catalog_stale"`
}

func discoverApplications(parent context.Context, c Config, snapshot NetworkContext) ApplicationSnapshot {
	result := ApplicationSnapshot{ObservedAt: time.Now().UTC()}
	ctx, cancel := context.WithTimeout(parent, 2*time.Second)
	defer cancel()
	output, err := exec.CommandContext(ctx, "/usr/sbin/lsof", "-nP", "-a", "-iTCP", "-sTCP:ESTABLISHED", "-F", "pcn").Output()
	if err != nil {
		result.Errors++
		return result
	}
	type aggregate struct {
		connections  int
		interfaces   map[string]bool
		destinations map[string]bool
	}
	byProcess := map[string]*aggregate{}
	var process string
	for _, line := range strings.Split(string(output), "\n") {
		if len(line) < 2 {
			continue
		}
		switch line[0] {
		case 'c':
			process = sanitizeProcess(line[1:])
		case 'n':
			if process == "" {
				continue
			}
			item := byProcess[process]
			if item == nil {
				item = &aggregate{interfaces: map[string]bool{}, destinations: map[string]bool{}}
				byProcess[process] = item
			}
			item.connections++
			result.EstablishedConnections++
			address := remoteAddress(line[1:])
			item.interfaces[routeInterface(ctx, address, snapshot.DefaultInterface)] = true
			if net.ParseIP(address) != nil {
				item.destinations[address] = true
			}
		}
	}
	names := make([]string, 0, len(byProcess))
	for name := range byProcess {
		names = append(names, name)
	}
	sort.Slice(names, func(i, j int) bool {
		return byProcess[names[i]].connections > byProcess[names[j]].connections
	})
	limit := c.ApplicationDiscoveryMaxApps
	if limit <= 0 || limit > len(names) {
		limit = len(names)
	}
	seenInterfaces := map[string]bool{}
	for _, name := range names[:limit] {
		interfaces := make([]string, 0, len(byProcess[name].interfaces))
		for value := range byProcess[name].interfaces {
			if value != "" {
				interfaces = append(interfaces, value)
				seenInterfaces[value] = true
			}
		}
		sort.Strings(interfaces)
		destinations := make([]string, 0, len(byProcess[name].destinations))
		for value := range byProcess[name].destinations {
			destinations = append(destinations, value)
		}
		sort.Strings(destinations)
		result.Applications = append(result.Applications, ApplicationObservation{
			Process: name, Connections: byProcess[name].connections, Interface: strings.Join(interfaces, ","),
			DestinationIPs: destinations, ObservedAt: result.ObservedAt,
		})
	}
	result.Interfaces = len(seenInterfaces)
	return result
}

func sanitizeProcess(value string) string {
	value = strings.TrimSpace(value)
	if len(value) > 64 {
		return value[:64]
	}
	return value
}

func remoteAddress(value string) string {
	parts := strings.SplitN(value, "->", 2)
	if len(parts) != 2 {
		return ""
	}
	remote := strings.TrimSpace(strings.SplitN(parts[1], " ", 2)[0])
	if host, _, err := net.SplitHostPort(remote); err == nil {
		return host
	}
	return strings.Trim(remote, "[]")
}

func routeInterface(ctx context.Context, address, fallback string) string {
	if net.ParseIP(address) == nil {
		return fallback
	}
	value, err := exec.CommandContext(ctx, "/sbin/route", "-n", "get", address).Output()
	if err != nil {
		return fallback
	}
	for _, line := range strings.Split(string(value), "\n") {
		fields := strings.Fields(line)
		if len(fields) == 2 && fields[0] == "interface:" {
			return fields[1]
		}
	}
	return fallback
}

func writeApplicationCatalog(path string, snapshot ApplicationSnapshot) error {
	content, err := json.MarshalIndent(snapshot, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(content, '\n'), 0600)
}
