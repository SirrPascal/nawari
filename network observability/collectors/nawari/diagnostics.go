package main

import (
	"context"
	"net"
	"net/url"
	"time"
)

type Diagnostics struct {
	DNSLookupMS     *float64
	DNSLookupOK     *bool
	GatewayRTTMS    *float64
	GatewayLossPct  *float64
	TargetRTTMS     *float64
	TargetLossPct   *float64
	WiFiSignalDBM   *int
	WiFiNoiseDBM    *int
	PathHops        *int
	PathReached     *bool
	PathDurationMS  *float64
	PathAgeSeconds  *int
	PathUnavailable bool
}

func collectDiagnostics(ctx context.Context, c Config, snapshot NetworkContext, runPath bool) Diagnostics {
	result := platformDiagnostics(ctx, c, snapshot, runPath)
	if c.DNSTestName != "" {
		started := time.Now()
		lookupCtx, cancel := context.WithTimeout(ctx, time.Duration(c.TimeoutMS)*time.Millisecond)
		_, err := net.DefaultResolver.LookupHost(lookupCtx, c.DNSTestName)
		cancel()
		duration := milliseconds(time.Since(started))
		ok := err == nil
		result.DNSLookupMS = &duration
		result.DNSLookupOK = &ok
	}
	return result
}

func approvedPathHost(c Config) string {
	target, err := url.Parse(c.URL)
	if err != nil {
		return ""
	}
	return target.Hostname()
}
