//go:build !darwin && !windows

package main

import "context"

func platformNetworkContext(_ context.Context, _ Config, localIP string) NetworkContext {
	return NetworkContext{LocalIP: localIP, InterfaceType: "unknown", WiFiState: "unknown", VPNState: "unknown", SystemProxy: "unknown",
		Unavailable: []string{"destination_route", "resolvers", "gateway", "wifi", "vpn", "system_proxy"}}
}
