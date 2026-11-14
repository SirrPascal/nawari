//go:build !darwin

package main

import "context"

func platformDiagnostics(_ context.Context, _ Config, _ NetworkContext, runPath bool) Diagnostics {
	return Diagnostics{PathUnavailable: runPath}
}
