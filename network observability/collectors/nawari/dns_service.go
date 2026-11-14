package main

import (
	"bufio"
	"encoding/json"
	"net"
	"os"
	"sort"
	"time"
)

type DNSObservation struct {
	Domain     string    `json:"domain"`
	CNAMEs     []string  `json:"cname_chain,omitempty"`
	Addresses  []string  `json:"addresses"`
	Resolver   string    `json:"resolver,omitempty"`
	ObservedAt time.Time `json:"observed_at"`
	DurationMS float64   `json:"duration_ms,omitempty"`
	Status     string    `json:"status"`
	TTL        int       `json:"ttl,omitempty"`
	Process    string    `json:"process,omitempty"`
}

type ServiceObservation struct {
	Domain         string    `json:"domain"`
	Application    string    `json:"application,omitempty"`
	Addresses      []string  `json:"addresses"`
	Classification string    `json:"classification"`
	Confidence     string    `json:"confidence"`
	Evidence       []string  `json:"evidence"`
	LastSeen       time.Time `json:"last_seen"`
	DNSDurationMS  float64   `json:"dns_duration_ms,omitempty"`
}

func loadDNSObservations(path string, now time.Time) ([]DNSObservation, int) {
	info, err := os.Stat(path)
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0022 != 0 || info.Size() > 1024*1024 {
		return nil, 1
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, 1
	}
	defer file.Close()
	var observations []DNSObservation
	errors := 0
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 4096), 64*1024)
	for scanner.Scan() {
		if len(observations) >= 256 {
			errors++
			break
		}
		var item DNSObservation
		if json.Unmarshal(scanner.Bytes(), &item) != nil || !validDNSObservation(item, now) {
			errors++
			continue
		}
		observations = append(observations, item)
	}
	if scanner.Err() != nil {
		errors++
	}
	return observations, errors
}

func validDNSObservation(item DNSObservation, now time.Time) bool {
	maxAge := 5 * time.Minute
	if item.TTL > 0 && time.Duration(item.TTL)*time.Second > maxAge {
		maxAge = time.Duration(item.TTL) * time.Second
	}
	if maxAge > 24*time.Hour {
		maxAge = 24 * time.Hour
	}
	if item.Domain == "" || len(item.Domain) > 253 || item.ObservedAt.IsZero() || item.ObservedAt.After(now.Add(2*time.Minute)) || now.Sub(item.ObservedAt) > maxAge {
		return false
	}
	if item.Status == "" || item.DurationMS < 0 || item.DurationMS > 30000 || item.TTL < 0 || item.TTL > 86400 || len(item.Addresses) > 32 || len(item.CNAMEs) > 16 {
		return false
	}
	for _, address := range item.Addresses {
		if net.ParseIP(address) == nil {
			return false
		}
	}
	for _, name := range item.CNAMEs {
		if name == "" || len(name) > 253 {
			return false
		}
	}
	return true
}

func countDNSFailures(observations []DNSObservation) int {
	count := 0
	for _, item := range observations {
		if item.Status != "success" {
			count++
		}
	}
	return count
}

func countDNSSlow(observations []DNSObservation, threshold int) int {
	count := 0
	for _, item := range observations {
		if item.Status == "success" && item.DurationMS >= float64(threshold) {
			count++
		}
	}
	return count
}

func correlateServices(applications []ApplicationObservation, observations []DNSObservation, now time.Time, slowThresholdMS int) []ServiceObservation {
	addressDomains := map[string]map[string]bool{}
	for _, dns := range observations {
		for _, address := range dns.Addresses {
			if addressDomains[address] == nil {
				addressDomains[address] = map[string]bool{}
			}
			addressDomains[address][dns.Domain] = true
		}
	}
	var services []ServiceObservation
	for _, dns := range observations {
		matches := map[string]bool{}
		for _, app := range applications {
			if dns.Process != "" && dns.Process != app.Process {
				continue
			}
			if hasAddressOverlap(dns.Addresses, app.DestinationIPs) {
				matches[app.Process] = true
			}
		}
		service := ServiceObservation{Domain: dns.Domain, Addresses: dns.Addresses, LastSeen: dns.ObservedAt, DNSDurationMS: dns.DurationMS}
		if dns.Status != "success" {
			service.Classification = "critical"
			service.Confidence = "confirmed"
			service.Evidence = []string{"dns_failure"}
		} else if dns.DurationMS >= float64(slowThresholdMS) {
			service.Classification = "degraded"
			service.Confidence = "unresolved"
			service.Evidence = []string{"dns_latency_threshold"}
		} else {
			service.Classification = "healthy"
			service.Confidence = "unresolved"
			service.Evidence = []string{"dns_observation_only"}
		}
		if len(matches) == 1 {
			for app := range matches {
				service.Application = app
			}
			sharedAddress := false
			for _, address := range dns.Addresses {
				if len(addressDomains[address]) > 1 {
					sharedAddress = true
				}
			}
			if sharedAddress && dns.Process == "" {
				service.Confidence = "unresolved"
				service.Evidence = append(service.Evidence, "shared_destination")
			} else if dns.Process != "" {
				service.Confidence = "confirmed"
				service.Evidence = append(service.Evidence, "process_dns_observation")
			} else {
				service.Confidence = "probable"
				service.Evidence = append(service.Evidence, "address_time_correlation")
			}
		} else if len(matches) > 1 {
			service.Confidence = "unresolved"
			service.Evidence = append(service.Evidence, "shared_destination")
		}
		services = append(services, service)
	}
	sort.Slice(services, func(i, j int) bool {
		if services[i].Classification != services[j].Classification {
			return services[i].Classification == "critical"
		}
		return services[i].Domain < services[j].Domain
	})
	return services
}

func hasAddressOverlap(left, right []string) bool {
	for _, a := range left {
		for _, b := range right {
			if a == b {
				return true
			}
		}
	}
	return false
}
