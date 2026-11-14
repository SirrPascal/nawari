//go:build darwin

package main

import (
	"context"
	"net"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
	"time"
)

var pingSummary = regexp.MustCompile(`([0-9.]+)% packet loss`)
var pingRTT = regexp.MustCompile(`round-trip min/avg/max/stddev = [0-9.]+/([0-9.]+)/`)
var pathHop = regexp.MustCompile(`(?m)^\s*([0-9]+)\s+`)
var wifiSignal = regexp.MustCompile(`(?i)(?:agrCtlRSSI|signal / noise)\s*[:=]\s*(-?[0-9]+)(?:\s*/\s*(-?[0-9]+))?`)

func platformDiagnostics(ctx context.Context, c Config, snapshot NetworkContext, runPath bool) Diagnostics {
	result := Diagnostics{}
	if snapshot.Gateway != "" && net.ParseIP(snapshot.Gateway) != nil {
		result.GatewayRTTMS, result.GatewayLossPct = boundedPing(ctx, snapshot.Gateway, c.TimeoutMS)
	}
	if c.ICMPTarget != "" {
		result.TargetRTTMS, result.TargetLossPct = boundedPing(ctx, c.ICMPTarget, c.TimeoutMS)
	}
	result.WiFiSignalDBM, result.WiFiNoiseDBM = collectWiFiRadio(ctx)
	if runPath && c.PathEnabled {
		result.PathHops, result.PathReached, result.PathDurationMS = boundedPath(ctx, approvedPathHost(c), c.PathMaxHops)
		result.PathUnavailable = result.PathHops == nil
	}
	return result
}

func boundedPing(parent context.Context, target string, timeoutMS int) (*float64, *float64) {
	seconds := max(1, (timeoutMS+999)/1000)
	ctx, cancel := context.WithTimeout(parent, time.Duration(seconds*3)*time.Second)
	defer cancel()
	output, _ := exec.CommandContext(ctx, "/sbin/ping", "-n", "-c", "3", "-W", strconv.Itoa(timeoutMS), target).CombinedOutput()
	if len(output) > 16*1024 {
		return nil, nil
	}
	text := string(output)
	var rtt *float64
	var loss *float64
	if match := pingRTT.FindStringSubmatch(text); len(match) == 2 {
		value, _ := strconv.ParseFloat(match[1], 64)
		rtt = &value
	}
	if match := pingSummary.FindStringSubmatch(text); len(match) == 2 {
		value, _ := strconv.ParseFloat(match[1], 64)
		loss = &value
	}
	return rtt, loss
}

func collectWiFiRadio(parent context.Context) (*int, *int) {
	paths := [][]string{
		{"/usr/bin/wdutil", "info"},
		{"/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"},
	}
	for _, command := range paths {
		ctx, cancel := context.WithTimeout(parent, 2*time.Second)
		output, _ := exec.CommandContext(ctx, command[0], command[1:]...).CombinedOutput()
		cancel()
		if len(output) > 64*1024 {
			continue
		}
		match := wifiSignal.FindStringSubmatch(string(output))
		if len(match) >= 2 {
			signal, _ := strconv.Atoi(match[1])
			var noise *int
			if len(match) >= 3 && strings.TrimSpace(match[2]) != "" {
				value, _ := strconv.Atoi(match[2])
				noise = &value
			}
			return &signal, noise
		}
	}
	return nil, nil
}

func boundedPath(parent context.Context, target string, maxHops int) (*int, *bool, *float64) {
	if !validProbeHost(target) {
		return nil, nil, nil
	}
	ctx, cancel := context.WithTimeout(parent, time.Duration(maxHops+2)*time.Second)
	defer cancel()
	started := time.Now()
	output, _ := exec.CommandContext(ctx, "/usr/sbin/traceroute", "-n", "-m", strconv.Itoa(maxHops), "-q", "1", "-w", "1", target).CombinedOutput()
	duration := milliseconds(time.Since(started))
	if len(output) > 64*1024 {
		return nil, nil, nil
	}
	matches := pathHop.FindAllStringSubmatch(string(output), -1)
	if len(matches) == 0 {
		return nil, nil, &duration
	}
	hops, _ := strconv.Atoi(matches[len(matches)-1][1])
	reached := false
	for _, line := range strings.Split(string(output), "\n") {
		if strings.Contains(line, target) {
			reached = true
		}
	}
	return &hops, &reached, &duration
}
