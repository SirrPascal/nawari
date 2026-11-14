//go:build !darwin

package main

import (
	"context"
	"errors"
)

type ApplicationObservation struct {
	Process        string   `json:"process"`
	Connections    int      `json:"established_connections"`
	Interface      string   `json:"interface"`
	DestinationIPs []string `json:"destination_ips"`
}

type ApplicationSnapshot struct {
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

func discoverApplications(context.Context, Config, NetworkContext) ApplicationSnapshot {
	return ApplicationSnapshot{Errors: 1}
}

func writeApplicationCatalog(string, ApplicationSnapshot) error {
	return errors.New("application discovery is only supported on macOS")
}
