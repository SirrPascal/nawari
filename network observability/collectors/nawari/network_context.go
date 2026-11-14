package main

import (
	"context"
	"os"
	"path/filepath"
)

type NetworkContext struct {
	Interface            string
	InterfaceType        string
	DefaultInterface     string
	DefaultInterfaceType string
	LocalIP              string
	Gateway              string
	Resolvers            []string
	WiFiState            string
	WiFiSSIDHash         string
	VPNState             string
	VPNInterfaces        []string
	SystemProxy          string
	Unavailable          []string
}

func defaultConfigPath() string {
	if value := os.Getenv("NAWARI_COLLECTOR_CONFIG"); value != "" {
		return value
	}
	if directory := os.Getenv("NETDATA_USER_CONFIG_DIR"); directory != "" {
		return filepath.Join(directory, "nawari-collector.json")
	}
	return ""
}

func collectNetworkContext(ctx context.Context, c Config, localIP string) NetworkContext {
	return platformNetworkContext(ctx, c, localIP)
}
