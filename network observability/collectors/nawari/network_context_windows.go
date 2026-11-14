//go:build windows

package main

import (
	"context"
	"net"
)

func platformNetworkContext(_ context.Context, _ Config, localIP string) NetworkContext {
	result := NetworkContext{LocalIP: localIP, InterfaceType: "unknown", WiFiState: "unknown", VPNState: "unknown", SystemProxy: "unknown",
		Unavailable: []string{"destination_route", "resolvers", "gateway", "wifi", "vpn", "system_proxy"}}
	wanted := net.ParseIP(localIP)
	interfaces, _ := net.Interfaces()
	for _, item := range interfaces {
		addresses, _ := item.Addrs()
		for _, address := range addresses {
			ip, _, _ := net.ParseCIDR(address.String())
			if ip != nil && ip.Equal(wanted) {
				result.Interface = item.Name
				return result
			}
		}
	}
	return result
}
