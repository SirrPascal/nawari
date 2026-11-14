//go:build darwin

package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"net"
	"net/url"
	"os/exec"
	"regexp"
	"sort"
	"strings"
	"time"
)

var routeValue = regexp.MustCompile(`(?m)^\s*(interface|gateway):\s*(\S+)\s*$`)
var resolverValue = regexp.MustCompile(`(?m)^\s*nameserver\[[0-9]+\]\s*:\s*(\S+)\s*$`)
var wifiDeviceValue = regexp.MustCompile(`(?m)^Hardware Port: Wi-Fi\s*\nDevice:\s*(\S+)\s*$`)
var hardwarePortValue = regexp.MustCompile(`(?ms)^Hardware Port:\s*(.+?)\s*\nDevice:\s*(\S+)\s*$`)

func boundedCommand(parent context.Context, name string, arguments ...string) string {
	ctx, cancel := context.WithTimeout(parent, time.Second)
	defer cancel()
	value, err := exec.CommandContext(ctx, name, arguments...).Output()
	if err != nil || len(value) > 64*1024 {
		return ""
	}
	return string(value)
}

func interfaceKind(name string, hardwarePorts string) string {
	switch {
	case strings.HasPrefix(name, "utun"):
		return "tunnel"
	case strings.HasPrefix(name, "lo"):
		return "loopback"
	}
	for _, match := range hardwarePortValue.FindAllStringSubmatch(hardwarePorts, -1) {
		if match[2] != name {
			continue
		}
		port := strings.ToLower(strings.TrimSpace(match[1]))
		if strings.Contains(port, "wi-fi") || strings.Contains(port, "wifi") {
			return "wifi"
		}
		return "ethernet"
	}
	if strings.HasPrefix(name, "en") {
		return "physical"
	}
	return "unknown"
}

func platformNetworkContext(ctx context.Context, c Config, localIP string) NetworkContext {
	result := NetworkContext{LocalIP: localIP, WiFiState: "unknown", VPNState: "unknown", SystemProxy: "unknown"}
	hardwarePorts := boundedCommand(ctx, "/usr/sbin/networksetup", "-listallhardwareports")
	destination, _ := url.Parse(c.URL)
	route := boundedCommand(ctx, "/sbin/route", "-n", "get", destination.Hostname())
	for _, match := range routeValue.FindAllStringSubmatch(route, -1) {
		if match[1] == "interface" {
			result.Interface = match[2]
			result.InterfaceType = interfaceKind(match[2], hardwarePorts)
		} else if match[1] == "gateway" {
			result.Gateway = match[2]
		}
	}
	if result.Gateway == "" {
		defaultRoute := boundedCommand(ctx, "/sbin/route", "-n", "get", "default")
		for _, match := range routeValue.FindAllStringSubmatch(defaultRoute, -1) {
			if match[1] == "interface" {
				result.DefaultInterface = match[2]
				result.DefaultInterfaceType = interfaceKind(match[2], hardwarePorts)
			} else if match[1] == "gateway" {
				result.Gateway = match[2]
			}
		}
	} else {
		defaultRoute := boundedCommand(ctx, "/sbin/route", "-n", "get", "default")
		for _, match := range routeValue.FindAllStringSubmatch(defaultRoute, -1) {
			if match[1] == "interface" {
				result.DefaultInterface = match[2]
				result.DefaultInterfaceType = interfaceKind(match[2], hardwarePorts)
				break
			}
		}
	}
	if result.Interface == "" && localIP != "" {
		for _, item := range interfacesForIP(localIP) {
			result.Interface = item
			result.InterfaceType = interfaceKind(item, hardwarePorts)
			break
		}
	}
	dns := boundedCommand(ctx, "/usr/sbin/scutil", "--dns")
	seen := map[string]bool{}
	for _, match := range resolverValue.FindAllStringSubmatch(dns, -1) {
		if ip := net.ParseIP(strings.Trim(match[1], "[]")); ip != nil && !seen[ip.String()] {
			seen[ip.String()] = true
			result.Resolvers = append(result.Resolvers, ip.String())
		}
	}
	sort.Strings(result.Resolvers)

	proxy := boundedCommand(ctx, "/usr/sbin/scutil", "--proxy")
	switch {
	case proxy == "":
		result.SystemProxy = "unknown"
	case strings.Contains(proxy, "Enable : 1"):
		result.SystemProxy = "configured"
	default:
		result.SystemProxy = "not_configured"
	}
	vpn := boundedCommand(ctx, "/usr/sbin/scutil", "--nc", "list")
	switch {
	case vpn == "":
		result.VPNState = "unknown"
	case strings.Contains(vpn, "(Connected)"):
		result.VPNState = "connected"
	default:
		result.VPNState = "disconnected"
	}
	interfaces, _ := net.Interfaces()
	for _, item := range interfaces {
		if strings.HasPrefix(item.Name, "utun") && item.Flags&net.FlagUp != 0 {
			result.VPNInterfaces = append(result.VPNInterfaces, item.Name)
		}
	}
	sort.Strings(result.VPNInterfaces)

	wifiDevice := ""
	if match := wifiDeviceValue.FindStringSubmatch(hardwarePorts); len(match) == 2 {
		wifiDevice = match[1]
	}
	if wifiDevice != "" {
		wifi := boundedCommand(ctx, "/usr/sbin/networksetup", "-getairportnetwork", wifiDevice)
		if strings.Contains(wifi, "Current Wi-Fi Network:") {
			ssid := strings.TrimSpace(strings.SplitN(wifi, ":", 2)[1])
			digest := sha256.Sum256([]byte(ssid))
			result.WiFiState = "connected"
			result.WiFiSSIDHash = hex.EncodeToString(digest[:8])
		} else if wifi != "" {
			result.WiFiState = "disconnected_or_not_wifi"
		}
	}
	if result.Interface == "" {
		result.Unavailable = append(result.Unavailable, "destination_route")
	}
	if len(result.Resolvers) == 0 {
		result.Unavailable = append(result.Unavailable, "resolvers")
	}
	if result.WiFiState == "unknown" {
		result.Unavailable = append(result.Unavailable, "wifi")
	}
	if result.VPNState == "unknown" {
		result.Unavailable = append(result.Unavailable, "vpn")
	}
	if result.SystemProxy == "unknown" {
		result.Unavailable = append(result.Unavailable, "system_proxy")
	}
	return result
}

func interfacesForIP(value string) []string {
	wanted := net.ParseIP(value)
	var result []string
	interfaces, _ := net.Interfaces()
	for _, item := range interfaces {
		addresses, _ := item.Addrs()
		for _, address := range addresses {
			ip, _, _ := net.ParseCIDR(address.String())
			if ip != nil && ip.Equal(wanted) {
				result = append(result, item.Name)
			}
		}
	}
	return result
}
