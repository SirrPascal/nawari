//go:build darwin

package main

import (
	"context"
	"os"
	"testing"
)

func TestInterfaceKindDistinguishesWiFiEthernetAndTunnels(t *testing.T) {
	hardwarePorts := "Hardware Port: Wi-Fi\nDevice: en0\n\nHardware Port: USB 10/100/1000 LAN\nDevice: en12\n"
	for _, test := range []struct {
		name, expected string
	}{
		{"en0", "wifi"},
		{"en12", "ethernet"},
		{"utun4", "tunnel"},
		{"lo0", "loopback"},
	} {
		if actual := interfaceKind(test.name, hardwarePorts); actual != test.expected {
			t.Fatalf("%s: got %q, want %q", test.name, actual, test.expected)
		}
	}
}

func TestDefaultRouteInterfaceIsSeparateFromDestinationRoute(t *testing.T) {
	value := NetworkContext{
		Interface:            "lo0",
		InterfaceType:        "loopback",
		DefaultInterface:     "en0",
		DefaultInterfaceType: "wifi",
	}
	if value.InterfaceType == value.DefaultInterfaceType {
		t.Fatal("destination and default route channels should remain distinct")
	}
}

func TestLiveDefaultRouteContext(t *testing.T) {
	if os.Getenv("NAWARI_LIVE_CONTEXT_TEST") != "1" {
		t.Skip("set NAWARI_LIVE_CONTEXT_TEST=1 for an opt-in host-context check")
	}
	value := platformNetworkContext(context.Background(), Config{URL: "https://1.1.1.1/"}, "")
	if value.Interface == "" {
		t.Fatalf("default route interface unavailable: %v", value.Unavailable)
	}
	// A scoped VPN route can legitimately expose a tunnel interface without a
	// next-hop gateway. Do not invent one in that state.
	if value.Gateway == "" && value.InterfaceType != "tunnel" {
		t.Fatalf("default route gateway unavailable outside a tunnel: interface=%q unavailable=%v", value.Interface, value.Unavailable)
	}
	if len(value.Resolvers) == 0 {
		t.Fatalf("resolver inventory unavailable: %v", value.Unavailable)
	}
}
