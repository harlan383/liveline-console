package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

const testTransitResourceID = "current-transit-resource"
const testTransitWorkerID = "current-transit-worker"
const testTransitLandingNodeID = "current-landing-node"
const testTransitInterfaceName = "eth0"

func TestParseDefaultRoute(t *testing.T) {
	info := parseDefaultRoute("default via 64.90.13.254 dev ens17 proto dhcp src 64.90.13.19 metric 100\n")
	if info.Interface != "ens17" {
		t.Fatalf("interface = %q, want ens17", info.Interface)
	}
	if info.Gateway != "64.90.13.254" {
		t.Fatalf("gateway = %q, want 64.90.13.254", info.Gateway)
	}
}

func TestLocalIPv4ForInterface(t *testing.T) {
	localIPs := []map[string]string{
		{"interface": "lo", "ip": "127.0.0.1"},
		{"interface": "ens17", "ip": "64.90.13.19"},
		{"interface": "ens17", "ip": "fe80::1"},
	}
	got := localIPv4ForInterface(localIPs, "ens17")
	if got != "64.90.13.19" {
		t.Fatalf("localIPv4ForInterface = %q, want 64.90.13.19", got)
	}
}

func TestListeningPortRowsFiltersInvalidRows(t *testing.T) {
	ssOutput := `Netid State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process
tcp   LISTEN 0      4096          0.0.0.0:22        0.0.0.0:*     users:(("sshd",pid=1,fd=3))
udp   UNCONN 0      0             0.0.0.0:68        0.0.0.0:*
tcp   LISTEN 0      4096          0.0.0.0:*         0.0.0.0:*     users:(("bad",pid=2,fd=3))
tcp   LISTEN 0      4096          [::]:443          [::]:*        users:(("xray",pid=3,fd=3))
`
	rows, skipped := listeningPortRows(ssOutput)
	if len(rows) != 2 {
		t.Fatalf("len(rows) = %d, want 2 rows: %#v", len(rows), rows)
	}
	if skipped != 1 {
		t.Fatalf("skipped = %d, want 1", skipped)
	}
	if rows[0]["port"] != 22 {
		t.Fatalf("first port = %#v, want 22", rows[0]["port"])
	}
	if rows[1]["port"] != 443 {
		t.Fatalf("second port = %#v, want 443", rows[1]["port"])
	}
}

func TestValidateManagedXrayBaseDirForPreflightAllowsEmptyPrecreatedDir(t *testing.T) {
	baseDir := filepath.Join(t.TempDir(), "liveline-xray")
	if err := os.Mkdir(baseDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := validateManagedXrayBaseDirForPreflight(baseDir); err != nil {
		t.Fatalf("validateManagedXrayBaseDirForPreflight returned error for empty dir: %v", err)
	}
}

func TestValidateManagedXrayBaseDirForPreflightAllowsEmptyKnownSubdirs(t *testing.T) {
	baseDir := filepath.Join(t.TempDir(), "liveline-xray")
	for _, dir := range []string{"bin", "config"} {
		if err := os.MkdirAll(filepath.Join(baseDir, dir), 0o755); err != nil {
			t.Fatal(err)
		}
	}
	if err := validateManagedXrayBaseDirForPreflight(baseDir); err != nil {
		t.Fatalf("validateManagedXrayBaseDirForPreflight returned error for empty known subdirs: %v", err)
	}
}

func TestValidateManagedXrayBaseDirForPreflightRejectsUnknownArtifacts(t *testing.T) {
	baseDir := filepath.Join(t.TempDir(), "liveline-xray")
	if err := os.Mkdir(baseDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(baseDir, "unknown.txt"), []byte("not managed"), 0o600); err != nil {
		t.Fatal(err)
	}
	err := validateManagedXrayBaseDirForPreflight(baseDir)
	if err == nil {
		t.Fatal("validateManagedXrayBaseDirForPreflight returned nil for unknown artifact")
	}
	if !strings.Contains(err.Error(), "unknown artifact") {
		t.Fatalf("error = %q, want unknown artifact", err.Error())
	}
}

func TestValidateManagedXrayBaseDirForPreflightRejectsNonEmptyKnownSubdir(t *testing.T) {
	baseDir := filepath.Join(t.TempDir(), "liveline-xray")
	binDir := filepath.Join(baseDir, "bin")
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(binDir, "xray"), []byte("binary"), 0o600); err != nil {
		t.Fatal(err)
	}
	err := validateManagedXrayBaseDirForPreflight(baseDir)
	if err == nil {
		t.Fatal("validateManagedXrayBaseDirForPreflight returned nil for non-empty known subdir")
	}
	if !strings.Contains(err.Error(), "not empty") {
		t.Fatalf("error = %q, want not empty", err.Error())
	}
}

func TestWorkerConfigPersistsServerID(t *testing.T) {
	configPath := filepath.Join(t.TempDir(), "config.yaml")
	original := config{
		ConsoleURL:               "https://console.example.invalid",
		WorkerID:                 testTransitWorkerID,
		ServerID:                 testTransitResourceID,
		WorkerSecret:             "fake-secret",
		Role:                     "transit",
		InterfaceName:            testTransitInterfaceName,
		HeartbeatIntervalSeconds: 60,
	}
	if err := writeConfig(configPath, original); err != nil {
		t.Fatal(err)
	}
	loaded, err := readConfig(configPath)
	if err != nil {
		t.Fatal(err)
	}
	if loaded.ServerID != testTransitResourceID {
		t.Fatalf("ServerID = %q, want %q", loaded.ServerID, testTransitResourceID)
	}
	if loaded.WorkerID != testTransitWorkerID || loaded.InterfaceName != testTransitInterfaceName {
		t.Fatalf("loaded identity mismatch: %#v", loaded)
	}
}

func TestDescribeHTTPPostErrorClassifiesHeadersTimeout(t *testing.T) {
	err := errors.New("context deadline exceeded (Client.Timeout exceeded while awaiting headers)")
	got := describeHTTPPostError(err)
	if !strings.Contains(got, "response_headers_timeout") {
		t.Fatalf("describeHTTPPostError = %q, want response_headers_timeout", got)
	}
}

func TestCurlFallbackTriggerReasonCoversPreResponseFailures(t *testing.T) {
	cases := []struct {
		name   string
		err    error
		reason string
	}{
		{
			name:   "headers timeout",
			err:    errors.New("post console.example/api/workers/commands/id/result failed before response: response_headers_timeout: context deadline exceeded"),
			reason: "response_headers_timeout",
		},
		{
			name:   "request eof",
			err:    errors.New("post console.example/api/workers/commands/id/result failed before response: request_error: EOF"),
			reason: "pre_response_eof",
		},
		{
			name:   "unexpected eof",
			err:    errors.New("post console.example/api/workers/commands/id/result failed before response: unexpected EOF"),
			reason: "unexpected_eof",
		},
		{
			name:   "connection reset",
			err:    errors.New("post console.example/api/workers/commands/id/result failed before response: read tcp: connection reset by peer"),
			reason: "connection_reset_by_peer",
		},
		{
			name:   "broken pipe",
			err:    errors.New("post console.example/api/workers/commands/id/result failed before response: write tcp: broken pipe"),
			reason: "broken_pipe",
		},
		{
			name:   "server closed idle connection",
			err:    errors.New("post console.example/api/workers/commands/id/result failed before response: http: server closed idle connection"),
			reason: "server_closed_idle_connection",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, ok := curlFallbackTriggerReason(tc.err)
			if !ok {
				t.Fatalf("curlFallbackTriggerReason(%v) did not trigger", tc.err)
			}
			if got != tc.reason {
				t.Fatalf("reason = %q, want %q", got, tc.reason)
			}
		})
	}

	if reason, ok := curlFallbackTriggerReason(errors.New("read console response status=200 failed: request_error: EOF")); ok {
		t.Fatalf("post-response EOF triggered curl fallback with reason %q", reason)
	}
}

func TestBuildResultSubmitDebugSummaryRedactsBodyAndSensitiveValues(t *testing.T) {
	fakeLinkMarker := "vless" + "://fake-redacted-example"
	result := map[string]any{
		"status":        "blocked",
		"worker_secret": "secret-value-that-must-not-appear",
		"token":         "token-value-that-must-not-appear",
		"checks": []any{
			map[string]any{
				"id":     "planned_port_available",
				"status": "blocked",
				"passed": false,
				"detail": fakeLinkMarker + " should be detected but not emitted",
			},
		},
	}

	summary := buildResultSubmitDebugSummary("transit_readonly_preflight", result)
	body, err := json.Marshal(summary)
	if err != nil {
		t.Fatal(err)
	}
	text := string(body)
	for _, forbidden := range []string{
		"secret-value-that-must-not-appear",
		"token-value-that-must-not-appear",
		fakeLinkMarker,
	} {
		if strings.Contains(text, forbidden) {
			t.Fatalf("debug summary leaked %q: %s", forbidden, text)
		}
	}
	if !summary.SensitiveMarkerDetected {
		t.Fatal("SensitiveMarkerDetected = false, want true")
	}
	if summary.ChecksCount != 1 {
		t.Fatalf("ChecksCount = %d, want 1", summary.ChecksCount)
	}
	if len(summary.Checks) != 1 || summary.Checks[0].DetailLength == 0 {
		t.Fatalf("check detail length missing: %#v", summary.Checks)
	}
}

func TestBuildResultSubmitDebugSummaryLargestFieldAndTruncation(t *testing.T) {
	longDetail := strings.Repeat("x", resultStringLimit+25)
	result := map[string]any{
		"summary": "short",
		"nested":  map[string]any{"long_detail": longDetail},
		"checks": []any{
			map[string]any{"id": "one", "status": "passed", "passed": true, "detail": longDetail},
		},
	}

	summary := buildResultSubmitDebugSummary("transit_readonly_preflight", result)
	if summary.LargestFieldPath != "$.checks[0].detail" && summary.LargestFieldPath != "$.nested.long_detail" {
		t.Fatalf("LargestFieldPath = %q, want a long field path", summary.LargestFieldPath)
	}
	if summary.LargestFieldLength != len(longDetail) {
		t.Fatalf("LargestFieldLength = %d, want %d", summary.LargestFieldLength, len(longDetail))
	}
	if !summary.TruncationFlags["string_over_limit"] {
		t.Fatalf("string_over_limit = false, flags=%#v", summary.TruncationFlags)
	}
	if summary.Checks[0].DetailLength != len(longDetail) {
		t.Fatalf("DetailLength = %d, want %d", summary.Checks[0].DetailLength, len(longDetail))
	}
}

func TestBuildResultSubmitDebugSummarySoftLimitAndNUL(t *testing.T) {
	result := map[string]any{
		"summary": strings.Repeat("a", resultPayloadSoftLimit+100),
		"checks": []any{
			map[string]any{"id": "nul", "status": "passed", "passed": true, "detail": "ok\x00with-nul"},
		},
	}

	summary := buildResultSubmitDebugSummary("transit_readonly_preflight", result)
	if !summary.ContainsNUL {
		t.Fatal("ContainsNUL = false, want true")
	}
	if !summary.TruncationFlags["string_over_limit"] {
		t.Fatalf("string_over_limit = false, flags=%#v", summary.TruncationFlags)
	}
	if summary.SanitizedPayloadExceedsSoftLimit || summary.FallbackWouldBeTriggered {
		t.Fatalf("sanitized payload should be truncated below soft limit, got size=%d fallback=%v", summary.SubmitPayloadSize, summary.FallbackWouldBeTriggered)
	}
}

func TestBuildResultSubmitDebugSummaryNonJSONFriendlyTypes(t *testing.T) {
	result := map[string]any{
		"status": "passed",
		"bad":    func() {},
		"checks": []any{},
	}

	summary := buildResultSubmitDebugSummary("transit_readonly_preflight", result)
	if len(summary.NonJSONFriendlyTypes) != 1 {
		t.Fatalf("NonJSONFriendlyTypes = %#v, want one item", summary.NonJSONFriendlyTypes)
	}
	if !strings.Contains(summary.NonJSONFriendlyTypes[0], "$.bad") {
		t.Fatalf("NonJSONFriendlyTypes = %#v, want $.bad path", summary.NonJSONFriendlyTypes)
	}
	if summary.RawResultSize != -1 {
		t.Fatalf("RawResultSize = %d, want -1 for non JSON-friendly raw result", summary.RawResultSize)
	}
	if summary.SubmitPayloadSize <= 0 {
		t.Fatalf("SubmitPayloadSize = %d, want positive sanitized payload size", summary.SubmitPayloadSize)
	}
}

func TestPrepareTransitReadonlyPreflightCompactPayloadUnderTarget(t *testing.T) {
	result := largeTransitReadonlyPreflightResult()
	sanitized := sanitizeCommandResult("transit_readonly_preflight", result)

	submitResult, info := prepareCommandResultForSubmit("transit_readonly_preflight", sanitized)
	submitPayloadSize := payloadSize(commandResultPayload{Result: submitResult})
	if submitPayloadSize > transitReadonlyCompactPayloadTarget {
		t.Fatalf("compact submit payload size = %d, want <= %d; payload=%#v", submitPayloadSize, transitReadonlyCompactPayloadTarget, submitResult)
	}
	if !info.CompactApplied {
		t.Fatal("CompactApplied = false, want true")
	}
	if info.OriginalSubmitPayloadSize <= info.CompactSubmitPayloadSize {
		t.Fatalf("compact did not shrink payload: original=%d compact=%d", info.OriginalSubmitPayloadSize, info.CompactSubmitPayloadSize)
	}
	if intResultValue(submitResult["checks_count"]) != 6 {
		t.Fatalf("checks_count = %#v, want 6", submitResult["checks_count"])
	}
	for _, key := range []string{"passed", "status", "summary", "checks_count", "worker_version", "planned_listen_port", "landing_target_port", "forwarding_method"} {
		if _, ok := submitResult[key]; !ok {
			t.Fatalf("compact payload missing key %q: %#v", key, submitResult)
		}
	}
	if stringResultValue(submitResult["worker_version"]) != workerVersion {
		t.Fatalf("worker_version = %#v, want %q", submitResult["worker_version"], workerVersion)
	}
	if intResultValue(submitResult["planned_listen_port"]) != 23843 {
		t.Fatalf("planned_listen_port = %#v, want 23843", submitResult["planned_listen_port"])
	}
	if intResultValue(submitResult["landing_target_port"]) != 27939 {
		t.Fatalf("landing_target_port = %#v, want 27939", submitResult["landing_target_port"])
	}
	if len(stringResultValue(submitResult["summary"])) > transitReadonlyCompactSummaryLimit {
		t.Fatalf("summary length = %d, want <= %d", len(stringResultValue(submitResult["summary"])), transitReadonlyCompactSummaryLimit)
	}
	if checks, ok := submitResult["checks"].([]any); ok {
		for _, item := range checks {
			check := item.(map[string]any)
			if _, exists := check["status"]; exists {
				t.Fatalf("compact check retained status: %#v", check)
			}
			if _, exists := check["id"]; exists {
				t.Fatalf("compact check retained id: %#v", check)
			}
			if detail := stringResultValue(check["detail"]); len(detail) > transitReadonlyCompactCheckDetailLimit+len("...[truncated]") {
				t.Fatalf("compact detail length = %d, want truncated detail: %#v", len(detail), check)
			}
		}
	} else if _, ok := submitResult["failed_check_names"]; !ok {
		t.Fatalf("compact payload has neither checks nor failed_check_names: %#v", submitResult)
	}
}

func TestPrepareTransitReadonlyPreflightCompactPayloadDropsDetailsWhenNeeded(t *testing.T) {
	result := largeTransitReadonlyPreflightResult()
	checks := result["checks"].([]any)
	for index := range checks {
		check := checks[index].(map[string]any)
		check["label"] = strings.Repeat("check-name-", 20) + string(rune('a'+index))
		check["detail"] = strings.Repeat("detail-", 500)
		check["passed"] = index%2 == 0
	}
	sanitized := sanitizeCommandResult("transit_readonly_preflight", result)

	submitResult, info := prepareCommandResultForSubmit("transit_readonly_preflight", sanitized)
	submitPayloadSize := payloadSize(commandResultPayload{Result: submitResult})
	if submitPayloadSize > transitReadonlyCompactPayloadTarget {
		t.Fatalf("detail-free compact submit payload size = %d, want <= %d; payload=%#v", submitPayloadSize, transitReadonlyCompactPayloadTarget, submitResult)
	}
	if !info.DetailsRemoved {
		t.Fatalf("DetailsRemoved = false, want true for oversized detail payload; info=%#v", info)
	}
	if _, ok := submitResult["checks"]; ok {
		t.Fatalf("detail-free compact payload should remove checks: %#v", submitResult)
	}
	failedNames, ok := submitResult["failed_check_names"].([]any)
	if !ok || len(failedNames) == 0 {
		t.Fatalf("failed_check_names missing: %#v", submitResult)
	}
}

func TestPrepareTransitRouteCreateCompactPayloadUnderTarget(t *testing.T) {
	result := largeTransitRouteCreateDryRunResult()
	sanitized := sanitizeCommandResult("transit_route_create", result)

	submitResult, info := prepareCommandResultForSubmit("transit_route_create", sanitized)
	submitPayloadSize := payloadSize(commandResultPayload{Result: submitResult})
	if submitPayloadSize > transitRouteCreateCompactPayloadTarget {
		t.Fatalf("compact submit payload size = %d, want <= %d; payload=%#v", submitPayloadSize, transitRouteCreateCompactPayloadTarget, submitResult)
	}
	if !info.CompactApplied {
		t.Fatal("CompactApplied = false, want true")
	}
	for _, key := range []string{
		"execution_mode",
		"real_execution",
		"status",
		"summary",
		"checks_count",
		"worker_version",
		"planned_listen_port",
		"landing_target_port",
		"forwarding_method",
		"route_name",
	} {
		if _, ok := submitResult[key]; !ok {
			t.Fatalf("compact transit route create payload missing key %q: %#v", key, submitResult)
		}
	}
	if stringResultValue(submitResult["execution_mode"]) != "dry_run" {
		t.Fatalf("execution_mode = %#v, want dry_run", submitResult["execution_mode"])
	}
	if boolResultValue(submitResult["real_execution"]) {
		t.Fatalf("real_execution = true, want false")
	}
	if intResultValue(submitResult["planned_listen_port"]) != approvedTransitListenPort {
		t.Fatalf("planned_listen_port = %#v, want %d", submitResult["planned_listen_port"], approvedTransitListenPort)
	}
	if intResultValue(submitResult["landing_target_port"]) != approvedTransitLandingTargetPort {
		t.Fatalf("landing_target_port = %#v, want %d", submitResult["landing_target_port"], approvedTransitLandingTargetPort)
	}
	if _, exists := submitResult["planned_actions"]; exists {
		t.Fatalf("compact payload retained planned_actions: %#v", submitResult)
	}
	if service, exists := submitResult["planned_service"]; exists {
		t.Fatalf("compact payload retained full planned_service: %#v", service)
	}
	if checks, ok := submitResult["checks"].([]any); ok {
		for _, item := range checks {
			check := item.(map[string]any)
			if detail := stringResultValue(check["detail"]); len(detail) > transitRouteCreateCompactCheckDetailLimit+len("...[truncated]") {
				t.Fatalf("compact route detail length = %d, want truncated detail: %#v", len(detail), check)
			}
		}
	}
}

func TestPrepareTransitRouteCreateCompactPayloadDropsDetailsWhenNeeded(t *testing.T) {
	result := largeTransitRouteCreateDryRunResult()
	checks := result["checks"].([]any)
	for index := range checks {
		check := checks[index].(map[string]any)
		check["name"] = strings.Repeat("route-check-name-", 20)
		check["detail"] = strings.Repeat("route dry-run detail ", 500)
		check["passed"] = index%2 == 0
	}
	result["summary"] = strings.Repeat("summary ", 200)

	submitResult, info := prepareCommandResultForSubmit("transit_route_create", sanitizeCommandResult("transit_route_create", result))
	submitPayloadSize := payloadSize(commandResultPayload{Result: submitResult})
	if submitPayloadSize > transitRouteCreateCompactPayloadTarget {
		t.Fatalf("detail-free compact submit payload size = %d, want <= %d; payload=%#v", submitPayloadSize, transitRouteCreateCompactPayloadTarget, submitResult)
	}
	if !info.DetailsRemoved {
		t.Fatalf("DetailsRemoved = false, want true for oversized detail payload; info=%#v", info)
	}
	if _, ok := submitResult["checks"]; ok {
		t.Fatalf("detail-free compact payload should remove checks: %#v", submitResult)
	}
	if failedNames, ok := submitResult["failed_check_names"].([]any); !ok || len(failedNames) == 0 {
		t.Fatalf("failed_check_names missing: %#v", submitResult)
	}
}

func TestPrepareFailureResultForSubmitCompactsTransitRouteCreatePayload(t *testing.T) {
	result := fallbackCommandResult(
		workerCommand{ID: "route-command", CommandType: "transit_route_create"},
		errors.New(strings.Repeat("submit failed ", 100)),
	)
	result["checks"] = largeTransitRouteCreateDryRunResult()["checks"]
	result["planned_actions"] = largeTransitRouteCreateDryRunResult()["planned_actions"]
	result["planned_service"] = largeTransitRouteCreateDryRunResult()["planned_service"]

	payload := commandFailurePayload{
		ErrorMessage: compactWorkerFailureMessage(errors.New(strings.Repeat("submit failed ", 100))),
		Result:       prepareFailureResultForSubmit("transit_route_create", result, errors.New(strings.Repeat("submit failed ", 100))),
	}
	if payloadSize(payload) > workerFailurePayloadTarget {
		t.Fatalf("failure payload size = %d, want <= %d; payload=%#v", payloadSize(payload), workerFailurePayloadTarget, payload)
	}
	text, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{"X-Worker-Secret", "full-body-value", "vless://"} {
		if strings.Contains(string(text), forbidden) {
			t.Fatalf("failure payload leaked %q: %s", forbidden, string(text))
		}
	}
}

func TestPrepareTransitRouteCreateRealFailurePayloadPreservesDiagnostics(t *testing.T) {
	result := largeTransitRouteCreateRealFailedResult()
	submitResult, info := prepareCommandResultForSubmit("transit_route_create", sanitizeCommandResult("transit_route_create", result))
	submitPayloadSize := payloadSize(commandResultPayload{Result: submitResult})
	if submitPayloadSize > transitRouteCreateCompactPayloadTarget {
		t.Fatalf("real failure compact submit payload size = %d, want <= %d; payload=%#v", submitPayloadSize, transitRouteCreateCompactPayloadTarget, submitResult)
	}
	if !info.CompactApplied {
		t.Fatal("CompactApplied = false, want true for real-create failed result")
	}
	if stringResultValue(submitResult["execution_mode"]) != "real_create" {
		t.Fatalf("execution_mode = %#v, want real_create", submitResult["execution_mode"])
	}
	if !boolResultValue(submitResult["real_execution"]) {
		t.Fatalf("real_execution = %#v, want true", submitResult["real_execution"])
	}
	if stringResultValue(submitResult["status"]) != "failed" {
		t.Fatalf("status = %#v, want failed", submitResult["status"])
	}
	if !boolResultValue(submitResult["rollback_attempted"]) {
		t.Fatalf("rollback_attempted = %#v, want true", submitResult["rollback_attempted"])
	}
	diagnostics, ok := submitResult["diagnostics"].(map[string]any)
	if !ok {
		t.Fatalf("diagnostics missing: %#v", submitResult)
	}
	if _, ok := diagnostics["journal"]; !ok {
		t.Fatalf("journal diagnostics missing: %#v", diagnostics)
	}
	lastAttempt, ok := submitResult["last_listen_attempt"].(map[string]any)
	if !ok || intResultValue(lastAttempt["attempt"]) == 0 {
		t.Fatalf("last listen attempt missing: %#v", submitResult)
	}
}

func TestCommandTypeForFailureFallsBackToCommandWhenResultOmitsIt(t *testing.T) {
	command := workerCommand{ID: "route-command", CommandType: "transit_route_create"}
	result := largeTransitRouteCreateRealFailedResult()
	delete(result, "command_type")
	if got := commandTypeForFailure(command, result); got != "transit_route_create" {
		t.Fatalf("commandTypeForFailure = %q, want transit_route_create", got)
	}
	if got := commandTypeForFailure(command, map[string]any{"command_type": "ping"}); got != "ping" {
		t.Fatalf("commandTypeForFailure = %q, want ping", got)
	}
}

func TestPrepareCommandResultForSubmitLeavesNonTransitUntouched(t *testing.T) {
	sanitized := map[string]any{"summary": "ok", "checks": []any{map[string]any{"detail": strings.Repeat("x", 200)}}}
	submitResult, info := prepareCommandResultForSubmit("ping", sanitized)
	if info.CompactApplied {
		t.Fatal("CompactApplied = true for non-transit command")
	}
	if payloadSize(commandResultPayload{Result: submitResult}) != payloadSize(commandResultPayload{Result: sanitized}) {
		t.Fatalf("non-transit payload size changed")
	}
	if submitResult["summary"] != "ok" {
		t.Fatalf("non-transit result changed: %#v", submitResult)
	}
}

func approvedTransitRouteCreatePayload() map[string]any {
	return map[string]any{
		"transit_resource_id": testTransitResourceID,
		"transit_worker_id":   testTransitWorkerID,
		"interface_name":      testTransitInterfaceName,
		"landing_node_id":     testTransitLandingNodeID,
		"planned_listen_port": approvedTransitListenPort,
		"landing_target_host": approvedTransitLandingTargetHost,
		"landing_target_port": approvedTransitLandingTargetPort,
		"forwarding_method":   approvedTransitForwardingMethod,
		"purpose":             "直播",
		"approval_stage":      approvedTransitCreateStage,
		"dry_run":             true,
		"approval_required":   true,
		"route_name":          approvedTransitRouteName,
		"safety_boundary":     []any{"dry-run plan only", "no arbitrary shell accepted"},
	}
}

func approvedTransitHaproxyRouteCreatePayload() map[string]any {
	return map[string]any{
		"command_intent":       "haproxy_route_create_dry_run",
		"transit_resource_id":  testTransitResourceID,
		"transit_worker_id":    testTransitWorkerID,
		"interface_name":       testTransitInterfaceName,
		"landing_node_id":      testTransitLandingNodeID,
		"planned_listen_port":  approvedTransitListenPort,
		"landing_target_host":  approvedTransitLandingTargetHost,
		"landing_target_port":  approvedTransitLandingTargetPort,
		"forwarding_method":    approvedTransitHaproxyForwardingMethod,
		"purpose":              "直播",
		"approval_stage":       approvedTransitHaproxyDryRunStage,
		"dry_run":              true,
		"approval_required":    true,
		"real_execution":       false,
		"route_created":        false,
		"haproxy_installed":    false,
		"listener_bound":       false,
		"firewall_modified":    false,
		"share_link_mutated":   false,
		"cutover":              false,
		"route_name":           "haproxy-tcp-23843",
		"planned_service_name": "liveline-haproxy-23843.service",
		"haproxy_config_plan": map[string]any{
			"mode":           "tcp",
			"frontend_bind":  "*:23843",
			"backend_target": "64.90.13.19:27939",
		},
		"safety_boundary": []any{"dry-run plan only", "no arbitrary shell accepted"},
	}
}

func approvedTransitRouteCreateConfig() config {
	return config{
		Role:          "transit",
		WorkerID:      testTransitWorkerID,
		ServerID:      testTransitResourceID,
		InterfaceName: testTransitInterfaceName,
	}
}

func TestTransitRouteCreateHaproxyDryRunReturnsPlanOnly(t *testing.T) {
	command := workerCommand{
		ID:          "12345678-1234-1234-1234-123456789abc",
		CommandType: "transit_route_create",
		Payload:     approvedTransitHaproxyRouteCreatePayload(),
	}
	result, err := executeTransitRouteCreate(
		approvedTransitRouteCreateConfig(),
		"WEPC202605221223335",
		command,
	)
	if err != nil {
		t.Fatalf("executeTransitRouteCreate returned error: %v", err)
	}
	if result["status"] != "approval_required" {
		t.Fatalf("status = %#v, want approval_required", result["status"])
	}
	if result["execution_mode"] != "dry_run" {
		t.Fatalf("execution_mode = %#v, want dry_run", result["execution_mode"])
	}
	if result["real_execution"] != false {
		t.Fatalf("real_execution = %#v, want false", result["real_execution"])
	}
	if result["forwarding_method"] != approvedTransitHaproxyForwardingMethod {
		t.Fatalf("forwarding_method = %#v, want %q", result["forwarding_method"], approvedTransitHaproxyForwardingMethod)
	}
	if intResultValue(result["planned_listen_port"]) != approvedTransitListenPort {
		t.Fatalf("planned_listen_port = %#v, want %d", result["planned_listen_port"], approvedTransitListenPort)
	}
	if result["approval_stage"] != approvedTransitHaproxyDryRunStage {
		t.Fatalf("approval_stage = %#v, want %q", result["approval_stage"], approvedTransitHaproxyDryRunStage)
	}
	if result["route_created"] != false || result["haproxy_installed"] != false || result["listener_bound"] != false {
		t.Fatalf("haproxy dry-run mutated route state: %#v", result)
	}
	if result["firewall_modified"] != false || result["share_link_mutated"] != false || result["cutover"] != false {
		t.Fatalf("haproxy dry-run crossed safety boundary: %#v", result)
	}
	if result["next_stage"] != "Stage 3.3.138-new-transit-haproxy-route-create-final-approval" {
		t.Fatalf("next_stage = %#v", result["next_stage"])
	}
}

func TestTransitRouteCreateDryRunReturnsPlanOnly(t *testing.T) {
	command := workerCommand{
		ID:          "12345678-1234-1234-1234-123456789abc",
		CommandType: "transit_route_create",
		Payload:     approvedTransitRouteCreatePayload(),
	}
	result, err := executeTransitRouteCreate(
		approvedTransitRouteCreateConfig(),
		"WEPC202605221223335",
		command,
	)
	if err != nil {
		t.Fatalf("executeTransitRouteCreate returned error: %v", err)
	}
	if result["execution_mode"] != "dry_run" {
		t.Fatalf("execution_mode = %#v, want dry_run", result["execution_mode"])
	}
	if result["real_execution"] != false {
		t.Fatalf("real_execution = %#v, want false", result["real_execution"])
	}
	if intResultValue(result["planned_listen_port"]) != approvedTransitListenPort {
		t.Fatalf("planned_listen_port = %#v, want %d", result["planned_listen_port"], approvedTransitListenPort)
	}
	if intResultValue(result["landing_target_port"]) != approvedTransitLandingTargetPort {
		t.Fatalf("landing_target_port = %#v, want %d", result["landing_target_port"], approvedTransitLandingTargetPort)
	}
	if result["forwarding_method"] == approvedTransitHaproxyForwardingMethod {
		t.Fatalf("socat dry-run used haproxy forwarding: %#v", result["forwarding_method"])
	}
	plannedService := result["planned_service"].(map[string]any)
	serviceName := stringResultValue(plannedService["name"])
	if !strings.HasPrefix(serviceName, "liveline-socat-") || !strings.HasSuffix(serviceName, ".service") {
		t.Fatalf("planned service name = %q, want liveline-socat service", serviceName)
	}
	forbiddenTopLevelKeys := []string{"service_written", "listener_bound", "service_started", "share_link"}
	for _, forbidden := range forbiddenTopLevelKeys {
		if _, exists := result[forbidden]; exists {
			t.Fatalf("dry-run result contains forbidden top-level key %q: %#v", forbidden, result)
		}
	}
}

func TestTransitRouteCreateDryRunRejectsArbitraryShellPayload(t *testing.T) {
	payload := approvedTransitRouteCreatePayload()
	payload["shell"] = "systemctl start something"
	_, err := parseTransitRouteCreateRequest(payload)
	if err == nil {
		t.Fatal("parseTransitRouteCreateRequest returned nil for shell payload")
	}
	if !strings.Contains(err.Error(), "unsupported execution field") {
		t.Fatalf("error = %q, want unsupported execution field", err.Error())
	}
}

func TestTransitRouteCreateHaproxyDryRunRejectsOldSocatStage(t *testing.T) {
	request, err := parseTransitRouteCreateRequest(approvedTransitHaproxyRouteCreatePayload())
	if err != nil {
		t.Fatal(err)
	}
	request.ApprovalStage = approvedTransitCreateStage
	err = validateTransitRouteCreateDryRunRequest(request)
	if err == nil {
		t.Fatal("validateTransitRouteCreateDryRunRequest returned nil for old socat stage")
	}
	if !strings.Contains(err.Error(), "Stage 3.3.137") {
		t.Fatalf("error = %q, want Stage 3.3.137 approval error", err.Error())
	}
}

func TestTransitRouteCreateHaproxyDryRunRejectsNonApprovedPort(t *testing.T) {
	request, err := parseTransitRouteCreateRequest(approvedTransitHaproxyRouteCreatePayload())
	if err != nil {
		t.Fatal(err)
	}
	request.PlannedListenPort = 24731
	err = validateTransitRouteCreateDryRunRequest(request)
	if err == nil {
		t.Fatal("validateTransitRouteCreateDryRunRequest returned nil for non-approved HAProxy port")
	}
	if !strings.Contains(err.Error(), "planned_listen_port is not approved") {
		t.Fatalf("error = %q, want planned_listen_port approval error", err.Error())
	}
}

func TestTransitRouteCreateHaproxyDryRunRejectsSocatForwardingMethod(t *testing.T) {
	payload := approvedTransitHaproxyRouteCreatePayload()
	payload["forwarding_method"] = approvedTransitForwardingMethod
	request, err := parseTransitRouteCreateRequest(payload)
	if err != nil {
		t.Fatal(err)
	}
	err = validateTransitRouteCreateDryRunRequest(request)
	if err == nil {
		t.Fatal("validateTransitRouteCreateDryRunRequest returned nil for socat forwarding with HAProxy stage")
	}
	if !strings.Contains(err.Error(), "Stage 3.3.71") {
		t.Fatalf("error = %q, want socat Stage 3.3.71 validation path", err.Error())
	}
}

func TestTransitRouteCreateDryRunRejectsNonApprovedPort(t *testing.T) {
	request, err := parseTransitRouteCreateRequest(approvedTransitRouteCreatePayload())
	if err != nil {
		t.Fatal(err)
	}
	request.PlannedListenPort = 24731
	err = validateTransitRouteCreateDryRunRequest(request)
	if err == nil {
		t.Fatal("validateTransitRouteCreateDryRunRequest returned nil for non-approved port")
	}
	if !strings.Contains(err.Error(), "planned_listen_port is not approved") {
		t.Fatalf("error = %q, want planned_listen_port approval error", err.Error())
	}
}

func TestTransitRouteCreateDryRunRejectsNonApprovedLandingTarget(t *testing.T) {
	request, err := parseTransitRouteCreateRequest(approvedTransitRouteCreatePayload())
	if err != nil {
		t.Fatal(err)
	}
	request.LandingTargetHost = "203.0.113.10"
	err = validateTransitRouteCreateDryRunRequest(request)
	if err == nil {
		t.Fatal("validateTransitRouteCreateDryRunRequest returned nil for non-approved target")
	}
	if !strings.Contains(err.Error(), "landing_target_host is not approved") {
		t.Fatalf("error = %q, want landing_target_host approval error", err.Error())
	}
}

func approvedTransitRouteCreateRealPayload() map[string]any {
	payload := approvedTransitRouteCreatePayload()
	payload["approval_stage"] = approvedTransitRealCreateStage
	payload["dry_run"] = false
	payload["approval_required"] = false
	payload["execution_mode"] = "real_create"
	payload["approved_real_execution"] = true
	payload["firewall_security_group_confirmed"] = true
	payload["cloud_firewall_confirmed"] = true
	payload["server_firewall_confirmed"] = true
	payload["no_node_share_link_change_confirmed"] = true
	payload["no_full_client_link_confirmed"] = true
	payload["no_cutover_confirmed"] = true
	return payload
}

func approvedTransitHaproxyRouteCreateRealPayload() map[string]any {
	payload := approvedTransitHaproxyRouteCreatePayload()
	payload["command_intent"] = "haproxy_route_create_real_execution"
	payload["approval_stage"] = approvedTransitHaproxyRealCreateStage
	payload["dry_run"] = false
	payload["approval_required"] = false
	payload["execution_mode"] = "real_create"
	payload["approved_real_execution"] = true
	payload["user_approved_real_execution"] = true
	payload["firewall_security_group_confirmed"] = true
	payload["cloud_firewall_confirmed"] = true
	payload["server_firewall_confirmed"] = true
	payload["no_node_share_link_change_confirmed"] = true
	payload["no_full_client_link_confirmed"] = true
	payload["no_cutover_confirmed"] = true
	delete(payload, "haproxy_config_plan")
	return payload
}

func TestTransitRouteCreateHaproxyRealRequestAllowsStage139(t *testing.T) {
	request, err := parseTransitRouteCreateRequest(approvedTransitHaproxyRouteCreateRealPayload())
	if err != nil {
		t.Fatal(err)
	}
	if err := validateTransitRouteCreateHaproxyRequest(approvedTransitRouteCreateConfig(), request); err != nil {
		t.Fatalf("validateTransitRouteCreateHaproxyRequest returned error for Stage 3.3.139: %v", err)
	}
}

func TestTransitRouteCreateHaproxyRealRequestRejectsOldRealStage(t *testing.T) {
	payload := approvedTransitHaproxyRouteCreateRealPayload()
	payload["approval_stage"] = approvedTransitRealCreateStage
	request, err := parseTransitRouteCreateRequest(payload)
	if err != nil {
		t.Fatal(err)
	}
	err = validateTransitRouteCreateHaproxyRequest(approvedTransitRouteCreateConfig(), request)
	if err == nil {
		t.Fatal("validateTransitRouteCreateHaproxyRequest returned nil for old real-create stage")
	}
	if !strings.Contains(err.Error(), "Stage 3.3.139") {
		t.Fatalf("error = %q, want Stage 3.3.139 approval error", err.Error())
	}
}

func TestTransitRouteCreateHaproxyRealRequestRejectsWrongPort(t *testing.T) {
	payload := approvedTransitHaproxyRouteCreateRealPayload()
	payload["planned_listen_port"] = 24731
	request, err := parseTransitRouteCreateRequest(payload)
	if err != nil {
		t.Fatal(err)
	}
	err = validateTransitRouteCreateHaproxyRequest(approvedTransitRouteCreateConfig(), request)
	if err == nil {
		t.Fatal("validateTransitRouteCreateHaproxyRequest returned nil for wrong port")
	}
	if !strings.Contains(err.Error(), "planned_listen_port is not approved") {
		t.Fatalf("error = %q, want planned listen approval error", err.Error())
	}
}

func TestTransitRouteCreateHaproxyRealRequestRejectsDryRun(t *testing.T) {
	payload := approvedTransitHaproxyRouteCreateRealPayload()
	payload["dry_run"] = true
	request, err := parseTransitRouteCreateRequest(payload)
	if err != nil {
		t.Fatal(err)
	}
	err = validateTransitRouteCreateHaproxyRequest(approvedTransitRouteCreateConfig(), request)
	if err == nil {
		t.Fatal("validateTransitRouteCreateHaproxyRequest returned nil for dry_run=true")
	}
	if !strings.Contains(err.Error(), "dry_run=false") {
		t.Fatalf("error = %q, want dry_run=false error", err.Error())
	}
}

func TestTransitRouteCreateRealRequestRejectsNonApprovedPort(t *testing.T) {
	request, err := parseTransitRouteCreateRequest(approvedTransitRouteCreateRealPayload())
	if err != nil {
		t.Fatal(err)
	}
	request.PlannedListenPort = 24731
	err = validateTransitRouteCreateRealRequest(approvedTransitRouteCreateConfig(), request)
	if err == nil {
		t.Fatal("validateTransitRouteCreateRealRequest returned nil for non-approved port")
	}
	if !strings.Contains(err.Error(), "planned_listen_port is not approved") {
		t.Fatalf("error = %q, want planned_listen_port approval error", err.Error())
	}
}

func TestTransitRouteCreateRealRequestRejectsNonApprovedTarget(t *testing.T) {
	request, err := parseTransitRouteCreateRequest(approvedTransitRouteCreateRealPayload())
	if err != nil {
		t.Fatal(err)
	}
	request.LandingTargetHost = "203.0.113.10"
	err = validateTransitRouteCreateRealRequest(approvedTransitRouteCreateConfig(), request)
	if err == nil {
		t.Fatal("validateTransitRouteCreateRealRequest returned nil for non-approved target")
	}
	if !strings.Contains(err.Error(), "landing_target_host is not approved") {
		t.Fatalf("error = %q, want landing_target_host approval error", err.Error())
	}
}

func TestTransitRouteCreateRealRequestRejectsNonApprovedTargetPort(t *testing.T) {
	request, err := parseTransitRouteCreateRequest(approvedTransitRouteCreateRealPayload())
	if err != nil {
		t.Fatal(err)
	}
	request.LandingTargetPort = 28000
	err = validateTransitRouteCreateRealRequest(approvedTransitRouteCreateConfig(), request)
	if err == nil {
		t.Fatal("validateTransitRouteCreateRealRequest returned nil for non-approved target port")
	}
	if !strings.Contains(err.Error(), "landing_target_port is not approved") {
		t.Fatalf("error = %q, want landing_target_port approval error", err.Error())
	}
}

func TestTransitRouteCreateRealRequestRejectsNonSocatForwarding(t *testing.T) {
	request, err := parseTransitRouteCreateRequest(approvedTransitRouteCreateRealPayload())
	if err != nil {
		t.Fatal(err)
	}
	request.ForwardingMethod = "gost"
	err = validateTransitRouteCreateRealRequest(approvedTransitRouteCreateConfig(), request)
	if err == nil {
		t.Fatal("validateTransitRouteCreateRealRequest returned nil for non-socat forwarding")
	}
	if !strings.Contains(err.Error(), "forwarding_method is not approved") {
		t.Fatalf("error = %q, want forwarding_method approval error", err.Error())
	}
}

func TestTransitRouteCreateRealRequestRejectsUnsafePayload(t *testing.T) {
	payload := approvedTransitRouteCreateRealPayload()
	payload["systemd_unit"] = "[Service]\nExecStart=/bin/true"
	_, err := parseTransitRouteCreateRequest(payload)
	if err == nil {
		t.Fatal("parseTransitRouteCreateRequest returned nil for systemd_unit payload")
	}
	if !strings.Contains(err.Error(), "unsupported execution field") {
		t.Fatalf("error = %q, want unsupported execution field", err.Error())
	}
}

func TestTransitRouteCreateRealRequestAllowsCurrentWorkerApproval(t *testing.T) {
	request, err := parseTransitRouteCreateRequest(approvedTransitRouteCreateRealPayload())
	if err != nil {
		t.Fatal(err)
	}
	if err := validateTransitRouteCreateRealRequest(approvedTransitRouteCreateConfig(), request); err != nil {
		t.Fatalf("validateTransitRouteCreateRealRequest returned error for current worker approval: %v", err)
	}
}

func TestTransitRouteCreateRealRequestRejectsWorkerMismatch(t *testing.T) {
	request, err := parseTransitRouteCreateRequest(approvedTransitRouteCreateRealPayload())
	if err != nil {
		t.Fatal(err)
	}
	err = validateTransitRouteCreateRealRequest(config{Role: "transit", WorkerID: "other-worker", ServerID: testTransitResourceID, InterfaceName: testTransitInterfaceName}, request)
	if err == nil {
		t.Fatal("validateTransitRouteCreateRealRequest returned nil for wrong worker")
	}
	if !strings.Contains(err.Error(), "TRANSIT_WORKER_ID_MISMATCH") {
		t.Fatalf("error = %q, want worker mismatch error", err.Error())
	}
}

func TestTransitRouteCreateRealRequestRejectsTransitResourceMismatch(t *testing.T) {
	request, err := parseTransitRouteCreateRequest(approvedTransitRouteCreateRealPayload())
	if err != nil {
		t.Fatal(err)
	}
	cfg := approvedTransitRouteCreateConfig()
	cfg.ServerID = "other-transit-resource"
	err = validateTransitRouteCreateRealRequest(cfg, request)
	if err == nil {
		t.Fatal("validateTransitRouteCreateRealRequest returned nil for wrong transit resource")
	}
	if !strings.Contains(err.Error(), "TRANSIT_RESOURCE_ID_MISMATCH") {
		t.Fatalf("error = %q, want resource mismatch error", err.Error())
	}
}

func TestTransitRouteCreateRealRequestRejectsInterfaceMismatch(t *testing.T) {
	request, err := parseTransitRouteCreateRequest(approvedTransitRouteCreateRealPayload())
	if err != nil {
		t.Fatal(err)
	}
	cfg := approvedTransitRouteCreateConfig()
	cfg.InterfaceName = "ens17"
	err = validateTransitRouteCreateRealRequest(cfg, request)
	if err == nil {
		t.Fatal("validateTransitRouteCreateRealRequest returned nil for wrong interface")
	}
	if !strings.Contains(err.Error(), "TRANSIT_INTERFACE_MISMATCH") {
		t.Fatalf("error = %q, want interface mismatch error", err.Error())
	}
}

func TestTransitRouteCreateRealRequestRejectsUnsafeRouteName(t *testing.T) {
	payload := approvedTransitRouteCreateRealPayload()
	payload["route_name"] = "hk socat; rm -rf"
	request, err := parseTransitRouteCreateRequest(payload)
	if err != nil {
		t.Fatal(err)
	}
	err = validateTransitRouteCreateRealRequest(approvedTransitRouteCreateConfig(), request)
	if err == nil {
		t.Fatal("validateTransitRouteCreateRealRequest returned nil for unsafe route_name")
	}
	if !strings.Contains(err.Error(), "route_name contains unsafe characters") {
		t.Fatalf("error = %q, want route_name safety error", err.Error())
	}
}

func TestTransitRouteCreateRealResultCompactKeepsServiceFields(t *testing.T) {
	result := map[string]any{
		"execution_mode":      "real_create",
		"real_execution":      true,
		"status":              "succeeded",
		"summary":             "approved route created",
		"hostname":            "WEPC202605221223335",
		"role":                "transit",
		"interface_name":      testTransitInterfaceName,
		"planned_listen_port": approvedTransitListenPort,
		"landing_target_host": approvedTransitLandingTargetHost,
		"landing_target_port": approvedTransitLandingTargetPort,
		"forwarding_method":   approvedTransitForwardingMethod,
		"route_name":          approvedTransitRouteName,
		"service_name":        approvedTransitSocatServiceName,
		"service_path":        approvedTransitSocatServicePath,
		"checks":              []any{map[string]any{"name": "listener_verified", "passed": true}},
	}
	submitResult, info := prepareCommandResultForSubmit("transit_route_create", sanitizeCommandResult("transit_route_create", result))
	if !info.CompactApplied {
		t.Fatal("CompactApplied = false, want true for transit_route_create")
	}
	if stringResultValue(submitResult["service_name"]) != approvedTransitSocatServiceName {
		t.Fatalf("service_name = %#v", submitResult["service_name"])
	}
	if stringResultValue(submitResult["service_path"]) != approvedTransitSocatServicePath {
		t.Fatalf("service_path = %#v", submitResult["service_path"])
	}
	text, err := json.Marshal(submitResult)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{"vless://", "X-Worker-Secret", "worker_secret"} {
		if strings.Contains(string(text), forbidden) {
			t.Fatalf("compact result leaked %q: %s", forbidden, string(text))
		}
	}
}

func TestTraceTransitReadonlyCompactResultRedactsBodyAndSecret(t *testing.T) {
	oldStderr := os.Stderr
	defer func() {
		os.Stderr = oldStderr
	}()

	readPipe, writePipe, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	os.Stderr = writePipe
	traceTransitReadonlyCompactResult(
		workerCommand{ID: "abc", CommandType: "transit_readonly_preflight"},
		"http://console.example:8200/api/workers/commands/abc/result",
		compactResultInfo{
			OriginalSubmitPayloadSize: 2306,
			CompactSubmitPayloadSize:  988,
			CompactApplied:            true,
			ChecksCount:               6,
			MaxDetailLength:           48,
		},
	)
	writePipe.Close()
	output, err := io.ReadAll(readPipe)
	if err != nil {
		t.Fatal(err)
	}
	logText := string(output)
	for _, forbidden := range []string{"secret-value", "full-body-value", "X-Worker-Secret"} {
		if strings.Contains(logText, forbidden) {
			t.Fatalf("compact trace leaked %q: %s", forbidden, logText)
		}
	}
	if !strings.Contains(logText, "compact_submit_payload_size=988") {
		t.Fatalf("compact trace missing payload size: %s", logText)
	}
}

func TestSafeEndpointLabelDropsQuery(t *testing.T) {
	got := safeEndpointLabel("http://console.example:8200/api/workers/commands/abc/result?" + "token" + "=secret")
	if got != "console.example:8200/api/workers/commands/abc/result" {
		t.Fatalf("safeEndpointLabel = %q", got)
	}
	if strings.Contains(got, "secret") || strings.Contains(got, "token") {
		t.Fatalf("safeEndpointLabel leaked query: %q", got)
	}
}

func TestSortedHeaderKeysDoesNotReturnValues(t *testing.T) {
	keys := sortedHeaderKeys(map[string]string{
		"X-Worker-Secret": "secret-value",
		"X-Worker-Id":     "worker-id",
	})
	got := strings.Join(keys, ",")
	if !strings.Contains(got, "X-Worker-Secret") || !strings.Contains(got, "X-Worker-Id") {
		t.Fatalf("header keys missing: %q", got)
	}
	if strings.Contains(got, "secret-value") || strings.Contains(got, "worker-id") {
		t.Fatalf("header values leaked: %q", got)
	}
}

func TestValidateCurlFallbackEndpointAllowsOnlyResultAndFail(t *testing.T) {
	allowed := []string{
		"http://console.example:8200/api/workers/commands/abc/result",
		"https://console.example/api/workers/commands/abc/fail",
	}
	for _, endpoint := range allowed {
		if err := validateCurlFallbackEndpoint(endpoint); err != nil {
			t.Fatalf("validateCurlFallbackEndpoint(%q) returned %v", endpoint, err)
		}
	}

	rejected := []string{
		"http://console.example:8200/api/workers/commands/abc/next",
		"http://console.example:8200/api/workers/commands/abc/result?" + "token" + "=secret",
		"http://console.example:8200/api/workers/commands/abc/result;rm",
		"http://console.example:8200/api/workers/commands/abc/result/extra",
		"file:///api/workers/commands/abc/result",
	}
	for _, endpoint := range rejected {
		if err := validateCurlFallbackEndpoint(endpoint); err == nil {
			t.Fatalf("validateCurlFallbackEndpoint(%q) returned nil, want rejection", endpoint)
		}
	}
}

func TestBuildCurlHeaderFileDoesNotExposeSecretInArgsModel(t *testing.T) {
	headerText := buildCurlHeaderFile(map[string]string{"X-Worker-Id": "worker-id", "X-Worker-Secret": "secret-value"})
	if !strings.Contains(headerText, "X-Worker-Secret: "+"secret-value") {
		t.Fatalf("curl header file should contain the secret header")
	}
	args := buildCurlFallbackArgs(
		"http://console.example:8200/api/workers/commands/abc/result",
		"/tmp/liveline-worker-curl-headers-example.txt",
		"/tmp/liveline-worker-curl-body-example.json",
	)
	joinedArgs := strings.Join(args, " ")
	if strings.Contains(joinedArgs, "--config") {
		t.Fatalf("curl args still contain --config: %q", joinedArgs)
	}
	if strings.Contains(joinedArgs, "--output") || strings.Contains(joinedArgs, "--write-out") {
		t.Fatalf("curl args still contain non-manual output capture flags: %q", joinedArgs)
	}
	if !strings.Contains(joinedArgs, "-i") {
		t.Fatalf("curl args do not include -i manual-compatible response capture: %q", joinedArgs)
	}
	if !strings.HasPrefix(args[len(args)-1], "http://") && !strings.HasPrefix(args[len(args)-1], "https://") {
		t.Fatalf("curl fixed URL lacks scheme: %q", args[len(args)-1])
	}
	if strings.Contains(joinedArgs, "secret-value") || strings.Contains(joinedArgs, "worker-id") {
		t.Fatalf("curl process args leaked header values: %q", joinedArgs)
	}
}

func TestPostJSONViaCurlUsesManualCompatibleTempHeaderBodyAndCleansFiles(t *testing.T) {
	fakeBin := t.TempDir()
	logPath := filepath.Join(t.TempDir(), "fake-curl.log")
	fakeCurl := filepath.Join(fakeBin, "curl")
	script := `#!/bin/sh
HEADER=""
BODY=""
URL=""
ARGS="$*"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --config)
      echo "unexpected --config" >&2
      exit 11
      ;;
    --header)
      HEADER="${2#@}"
      shift 2
      ;;
    --data-binary)
      BODY="${2#@}"
      shift 2
      ;;
    --output|--write-out)
      echo "unexpected output capture flag" >&2
      exit 14
      ;;
    --request|--max-time)
      shift 2
      ;;
    -i)
      shift
      ;;
    http://*|https://*)
      URL="$1"
      shift
      ;;
    *)
      shift
      ;;
  esac
done
if [ ! -f "$HEADER" ]; then
  echo "missing header" >&2
  exit 12
fi
if [ ! -f "$BODY" ]; then
  echo "missing body" >&2
  exit 13
fi
{
  printf 'header=%s\n' "$HEADER"
  printf 'body=%s\n' "$BODY"
  printf 'url=%s\n' "$URL"
  printf 'args=%s\n' "$ARGS"
  printf 'header_content=%s\n' "$(cat "$HEADER")"
  printf 'body_content=%s\n' "$(cat "$BODY")"
} > "$LIVELINE_FAKE_CURL_LOG"
printf 'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{"success":true,"message":"ok"}'
`
	if err := os.WriteFile(fakeCurl, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", fakeBin+string(os.PathListSeparator)+os.Getenv("PATH"))
	t.Setenv("LIVELINE_FAKE_CURL_LOG", logPath)

	var response apiResponse[map[string]any]
	err := postJSONViaCurl(
		"http://console.example:8200/api/workers/commands/abc/result",
		map[string]string{"X-Worker-Id": "worker-id", "X-Worker-Secret": "secret-value"},
		map[string]any{"result": map[string]any{"summary": "ok"}},
		&response,
	)
	if err != nil {
		t.Fatalf("postJSONViaCurl returned %v", err)
	}
	if !response.Success || response.Message != "ok" {
		t.Fatalf("response = %#v, want success ok", response)
	}
	logTextBytes, err := os.ReadFile(logPath)
	if err != nil {
		t.Fatal(err)
	}
	logFields := parseTestKeyValueLines(string(logTextBytes))
	for _, key := range []string{"header", "body"} {
		if logFields[key] == "" {
			t.Fatalf("fake curl log missing %s: %s", key, logTextBytes)
		}
		if _, err := os.Stat(logFields[key]); !errors.Is(err, os.ErrNotExist) {
			t.Fatalf("%s temp file still exists or stat failed: path=%q err=%v", key, logFields[key], err)
		}
	}
	if strings.Contains(logFields["args"], "secret-value") || strings.Contains(logFields["args"], "worker-id") {
		t.Fatalf("curl args leaked header values: %q", logFields["args"])
	}
	if strings.Contains(logFields["args"], "--config") {
		t.Fatalf("curl args unexpectedly used --config: %q", logFields["args"])
	}
	if strings.Contains(logFields["args"], "--output") || strings.Contains(logFields["args"], "--write-out") {
		t.Fatalf("curl args unexpectedly used output capture flags: %q", logFields["args"])
	}
	if !strings.Contains(logFields["args"], "-i") {
		t.Fatalf("curl args did not use -i: %q", logFields["args"])
	}
	if !strings.Contains(logFields["header_content"], "Content-Type: application/json") {
		t.Fatalf("header file content missing content type: %q", logFields["header_content"])
	}
	if !strings.Contains(logFields["body_content"], `"summary":"ok"`) {
		t.Fatalf("body file content missing JSON payload: %q", logFields["body_content"])
	}
}

func TestPostJSONViaCurlRoundTripWithRealCurlHeaderFile(t *testing.T) {
	if _, err := exec.LookPath("curl"); err != nil {
		t.Skip("curl is not available")
	}
	var receivedBody string
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Skipf("local listener unavailable: %v", err)
	}
	server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/workers/commands/abc/result" {
			t.Fatalf("path = %q, want Worker result path", r.URL.Path)
		}
		if r.Method != http.MethodPost {
			t.Fatalf("method = %q, want POST", r.Method)
		}
		body, err := io.ReadAll(r.Body)
		if err != nil {
			t.Fatal(err)
		}
		receivedBody = string(body)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":true,"message":"ok","data":{"stored":true}}`))
	}))
	server.Listener = listener
	server.Start()
	defer server.Close()

	var response apiResponse[map[string]any]
	err = postJSONViaCurl(
		server.URL+"/api/workers/commands/abc/result",
		map[string]string{"X-Worker-Id": "worker-id", "X-Worker-Secret": "secret-value"},
		map[string]any{"result": map[string]any{"summary": "ok"}},
		&response,
	)
	if err != nil {
		t.Fatalf("postJSONViaCurl returned %v", err)
	}
	if !response.Success {
		t.Fatalf("response = %#v, want success", response)
	}
	if !strings.Contains(receivedBody, `"summary":"ok"`) {
		t.Fatalf("server received body %q, want JSON payload", receivedBody)
	}
}

func TestWriteCurlFallbackTempFileUses0600(t *testing.T) {
	path, cleanup, err := writeCurlFallbackTempFile("liveline-worker-test-*.txt", []byte("ok"))
	if err != nil {
		t.Fatal(err)
	}
	defer cleanup()
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0o600 {
		t.Fatalf("temp file mode = %v, want 0600", info.Mode().Perm())
	}
}

func TestParseCurlIncludeOutputParses2xxAndBody(t *testing.T) {
	status, body, err := parseCurlIncludeOutput([]byte("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"success\":true}"))
	if err != nil {
		t.Fatal(err)
	}
	if status != 200 {
		t.Fatalf("status = %d, want 200", status)
	}
	if string(body) != `{"success":true}` {
		t.Fatalf("body = %q", body)
	}
}

func TestParseCurlIncludeOutputParsesNon2xx(t *testing.T) {
	status, body, err := parseCurlIncludeOutput([]byte("HTTP/1.1 500 Internal Server Error\r\nContent-Type: application/json\r\n\r\n{\"success\":false}"))
	if err != nil {
		t.Fatal(err)
	}
	if status != 500 {
		t.Fatalf("status = %d, want 500", status)
	}
	if string(body) != `{"success":false}` {
		t.Fatalf("body = %q", body)
	}
}

func TestPostJSONViaCurlTreatsNon2xxAsFailure(t *testing.T) {
	fakeBin := t.TempDir()
	fakeCurl := filepath.Join(fakeBin, "curl")
	script := `#!/bin/sh
printf 'HTTP/1.1 500 Internal Server Error\r\nContent-Type: application/json\r\n\r\n{"success":false,"message":"nope"}'
`
	if err := os.WriteFile(fakeCurl, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", fakeBin+string(os.PathListSeparator)+os.Getenv("PATH"))

	var response apiResponse[map[string]any]
	err := postJSONViaCurl(
		"http://console.example:8200/api/workers/commands/abc/result",
		map[string]string{"X-Worker-Id": "worker-id", "X-Worker-Secret": "secret-value"},
		map[string]any{"result": map[string]any{"summary": "ok"}},
		&response,
	)
	if err == nil {
		t.Fatal("postJSONViaCurl returned nil, want non-2xx error")
	}
	if !strings.Contains(err.Error(), "status=500") {
		t.Fatalf("error = %v, want status=500", err)
	}
	if strings.Contains(err.Error(), "secret-value") {
		t.Fatalf("error leaked secret: %v", err)
	}
}

func TestPostJSONWithCurlFallbackUsesCurlForEOFAndReturnsSuccess(t *testing.T) {
	oldPostJSONFunc := postJSONFunc
	oldPostJSONViaCurlFunc := postJSONViaCurlFunc
	defer func() {
		postJSONFunc = oldPostJSONFunc
		postJSONViaCurlFunc = oldPostJSONViaCurlFunc
	}()

	postJSONFunc = func(endpointURL string, headers map[string]string, payload any, out any) error {
		return errors.New("post console.example/api/workers/commands/abc/result failed before response: request_error: EOF")
	}
	curlCalled := false
	postJSONViaCurlFunc = func(endpointURL string, headers map[string]string, payload any, out any) error {
		curlCalled = true
		return nil
	}

	err := postJSONWithCurlFallback(
		"http://console.example:8200/api/workers/commands/abc/result",
		map[string]string{"X-Worker-Id": "worker-id", "X-Worker-Secret": "secret-value"},
		map[string]any{"result": "ok"},
		&map[string]any{},
	)
	if err != nil {
		t.Fatalf("postJSONWithCurlFallback returned %v, want nil", err)
	}
	if !curlCalled {
		t.Fatal("curl fallback was not called")
	}
}

func TestPostJSONWithCurlFallbackRejectsNonResultFailFallbackTargets(t *testing.T) {
	oldPostJSONFunc := postJSONFunc
	oldPostJSONViaCurlFunc := postJSONViaCurlFunc
	defer func() {
		postJSONFunc = oldPostJSONFunc
		postJSONViaCurlFunc = oldPostJSONViaCurlFunc
	}()

	originalErr := errors.New("post console.example failed before response: request_error: EOF")
	postJSONFunc = func(endpointURL string, headers map[string]string, payload any, out any) error {
		return originalErr
	}
	curlCalls := 0
	postJSONViaCurlFunc = func(endpointURL string, headers map[string]string, payload any, out any) error {
		curlCalls++
		return nil
	}

	rejected := []string{
		"http://console.example:8200/api/workers/commands/abc/next",
		"http://console.example:8200/api/workers/commands/abc/result?" + "token" + "=secret",
	}
	for _, endpoint := range rejected {
		err := postJSONWithCurlFallback(
			endpoint,
			map[string]string{"X-Worker-Id": "worker-id", "X-Worker-Secret": "secret-value"},
			map[string]any{"result": "ok"},
			&map[string]any{},
		)
		if !errors.Is(err, originalErr) {
			t.Fatalf("postJSONWithCurlFallback(%q) error = %v, want original error", endpoint, err)
		}
	}
	if curlCalls != 0 {
		t.Fatalf("curl fallback called %d times for rejected endpoints", curlCalls)
	}
}

func TestPostJSONWithCurlFallbackRedactsFailureTrace(t *testing.T) {
	oldPostJSONFunc := postJSONFunc
	oldPostJSONViaCurlFunc := postJSONViaCurlFunc
	oldStderr := os.Stderr
	defer func() {
		postJSONFunc = oldPostJSONFunc
		postJSONViaCurlFunc = oldPostJSONViaCurlFunc
		os.Stderr = oldStderr
	}()

	readPipe, writePipe, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	os.Stderr = writePipe

	postJSONFunc = func(endpointURL string, headers map[string]string, payload any, out any) error {
		return errors.New("post console failed before response: request_error: EOF secret-value")
	}
	postJSONViaCurlFunc = func(endpointURL string, headers map[string]string, payload any, out any) error {
		return errors.New("curl failed with secret-value")
	}

	_ = postJSONWithCurlFallback(
		"http://console.example:8200/api/workers/commands/abc/result",
		map[string]string{"X-Worker-Id": "worker-id", "X-Worker-Secret": "secret-value"},
		map[string]any{"result": "full-body-value"},
		&map[string]any{},
	)
	writePipe.Close()
	output, err := io.ReadAll(readPipe)
	if err != nil {
		t.Fatal(err)
	}
	logText := string(output)
	for _, forbidden := range []string{"secret-value", "worker-id", "full-body-value"} {
		if strings.Contains(logText, forbidden) {
			t.Fatalf("fallback trace leaked %q: %s", forbidden, logText)
		}
	}
}

func parseTestKeyValueLines(text string) map[string]string {
	values := map[string]string{}
	for _, line := range strings.Split(text, "\n") {
		if line == "" {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		values[parts[0]] = parts[1]
	}
	return values
}

func largeTransitReadonlyPreflightResult() map[string]any {
	checks := []any{}
	for index := 0; index < 6; index++ {
		checks = append(checks, map[string]any{
			"id":               fmt.Sprintf("check_%d", index),
			"label":            fmt.Sprintf("Readonly check %d", index),
			"status":           "passed",
			"passed":           true,
			"detail":           strings.Repeat("detail text ", 40),
			"category":         "readonly",
			"evidence_summary": strings.Repeat("evidence ", 30),
			"next_action":      strings.Repeat("next action ", 30),
		})
	}
	return map[string]any{
		"passed":              true,
		"status":              "passed",
		"summary":             strings.Repeat("Remote readonly preflight passed. ", 12),
		"checks":              checks,
		"worker_version":      workerVersion,
		"hostname":            "hk-transit-worker",
		"role":                "transit",
		"interface_name":      "ens17",
		"planned_listen_port": 23843,
		"landing_target_port": 27939,
		"forwarding_method":   "socat",
		"redacted_summary":    strings.Repeat("transit readonly preflight redacted summary ", 8),
		"safety_boundary": []any{
			"readonly checks only",
			"no arbitrary shell accepted",
			"no socat/gost install, start, stop, or restart",
			"no listener binding",
			"no firewall mutation",
			"no Xray mutation",
			"no nodes.share_link read or modification",
			"no cutover",
		},
	}
}

func largeTransitRouteCreateDryRunResult() map[string]any {
	checks := []any{}
	for index := 0; index < 5; index++ {
		checks = append(checks, map[string]any{
			"name":   fmt.Sprintf("route_create_check_%d", index),
			"passed": true,
			"detail": strings.Repeat("route create dry-run detail ", 30),
		})
	}
	return map[string]any{
		"status":              "approval_required",
		"execution_mode":      "dry_run",
		"real_execution":      false,
		"summary":             strings.Repeat("Transit route create dry-run accepted. ", 12),
		"worker_version":      workerVersion,
		"hostname":            "WEPC202605221223335",
		"role":                "transit",
		"interface_name":      "eth0",
		"transit_resource_id": testTransitResourceID,
		"landing_node_id":     testTransitLandingNodeID,
		"planned_listen_port": approvedTransitListenPort,
		"landing_target_host": approvedTransitLandingTargetHost,
		"landing_target_port": approvedTransitLandingTargetPort,
		"forwarding_method":   approvedTransitForwardingMethod,
		"purpose":             "直播",
		"approval_stage":      approvedTransitCreateStage,
		"route_name":          "hk-socat-live-23843",
		"planned_service": map[string]any{
			"name":       "liveline-socat-12345678123412341234123456789abc.service",
			"path":       "/etc/systemd/system/liveline-socat-12345678123412341234123456789abc.service",
			"exec_start": "fixed template: socat TCP-LISTEN:23843,fork,reuseaddr TCP:64.90.13.19:27939",
		},
		"planned_actions": []any{
			"validate approved Stage 3.3.70 parameters",
			"recheck planned listen port before real execution",
			"write LiveLine-managed socat systemd service in the later execution stage",
			"start and verify the service only after a future explicit authorization",
		},
		"checks": checks,
		"safety_boundary": []any{
			"dry-run plan only",
			"no arbitrary shell accepted",
			"no systemd unit content accepted from API",
			"no socat/gost install, start, stop, or restart",
			"no listener binding",
			"no firewall mutation",
			"no Xray mutation",
			"no nodes.share_link read or modification",
			"no cutover",
		},
	}
}

func largeTransitRouteCreateRealFailedResult() map[string]any {
	result := largeTransitRouteCreateDryRunResult()
	result["command_type"] = "transit_route_create"
	result["status"] = "failed"
	result["execution_mode"] = "real_create"
	result["real_execution"] = true
	result["summary"] = strings.Repeat("Approved socat transit route creation failed after listener verification. ", 8)
	result["redacted_error"] = "approved TCP port 23843 is not listening after socat start retries"
	result["approval_stage"] = approvedTransitRealCreateStage
	result["service_name"] = approvedTransitSocatServiceName
	result["service_path"] = approvedTransitSocatServicePath
	result["rollback_attempted"] = true
	result["listen_verification_attempts"] = []any{
		map[string]any{"attempt": 1, "service_active": "activating", "listener_detected": false},
		map[string]any{"attempt": 2, "service_active": "active", "listener_detected": false},
		map[string]any{"attempt": 3, "service_active": "active", "listener_detected": false},
	}
	result["diagnostics"] = map[string]any{
		"systemctl_is_active": map[string]any{"status": "ok", "detail": "active", "error": ""},
		"systemctl_status":    map[string]any{"status": "ok", "detail": strings.Repeat("status output ", 80), "error": ""},
		"journal":             map[string]any{"status": "ok", "detail": strings.Repeat("journal output ", 80), "error": ""},
		"listen_socket":       map[string]any{"status": "ok", "detail": "no listener line for :23843", "error": ""},
		"service_file": map[string]any{
			"exists":                 true,
			"size_bytes":             280,
			"contains_fixed_exec":    true,
			"contains_approved_name": true,
		},
	}
	result["checks"] = []any{
		map[string]any{"name": "approved_parameters_match", "passed": true},
		map[string]any{"name": "fixed_socat_template_only", "passed": true},
		map[string]any{"name": "listener_verified", "passed": false, "detail": "23843 was not confirmed listening before rollback"},
		map[string]any{"name": "rollback_attempted", "passed": true},
	}
	return result
}

func TestRemoteCleanupPayloadRejectsUnsafeShellKeys(t *testing.T) {
	command := workerCommand{
		ID:          "cleanup-command",
		CommandType: "cleanup_transit_route",
		Payload: map[string]any{
			"stage":                              remoteCleanupStage,
			"cleanup_type":                       "cleanup_transit_route",
			"target_id":                          "route-1",
			"remote_cleanup_required":            true,
			"system_record_delete_after_success": true,
			"confirmation":                       remoteCleanupConfirmation,
			"plans": []any{
				map[string]any{
					"route_id":          "route-1",
					"listen_port":       23843,
					"forwarding_method": "socat",
					"service_name":      "liveline-socat-23843.service",
					"service_path":      "/etc/systemd/system/liveline-socat-23843.service",
					"shell":             "rm -rf /",
				},
			},
		},
	}
	if _, err := parseRemoteCleanupRequest(command); err == nil {
		t.Fatal("parseRemoteCleanupRequest accepted unsafe shell key")
	}
}

func TestValidateCleanupSocatPlanRequiresLivelineService(t *testing.T) {
	good := remoteCleanupPlan{
		RouteID:          "route-1",
		ListenPort:       23843,
		ForwardingMethod: "socat",
		ServiceName:      "liveline-socat-23843.service",
		ServicePath:      "/etc/systemd/system/liveline-socat-23843.service",
	}
	if err := validateCleanupSocatPlan(good); err != nil {
		t.Fatalf("validateCleanupSocatPlan(good) returned error: %v", err)
	}
	bad := good
	bad.ServiceName = "socat.service"
	bad.ServicePath = "/etc/systemd/system/socat.service"
	if err := validateCleanupSocatPlan(bad); err == nil {
		t.Fatal("validateCleanupSocatPlan accepted non-LiveLine service")
	}
}

func TestValidateCleanupHaproxyPlanRequiresLivelineServiceAndConfig(t *testing.T) {
	good := remoteCleanupPlan{
		RouteID:          "route-1",
		ListenPort:       23843,
		TargetHost:       "64.90.13.19",
		TargetPort:       27939,
		ForwardingMethod: "haproxy_tcp",
		ServiceName:      "liveline-haproxy-23843.service",
		ServicePath:      "/etc/systemd/system/liveline-haproxy-23843.service",
		ConfigPath:       "/etc/haproxy/liveline/routes/liveline-haproxy-23843.cfg",
	}
	if err := validateCleanupHaproxyPlan(good); err != nil {
		t.Fatalf("validateCleanupHaproxyPlan(good) returned error: %v", err)
	}

	badConfig := good
	badConfig.ConfigPath = "/etc/haproxy/haproxy.cfg"
	if err := validateCleanupHaproxyPlan(badConfig); err == nil {
		t.Fatal("validateCleanupHaproxyPlan accepted non-LiveLine config path")
	}

	badMethod := good
	badMethod.ForwardingMethod = "socat"
	if err := validateCleanupHaproxyPlan(badMethod); err == nil {
		t.Fatal("validateCleanupHaproxyPlan accepted socat forwarding_method")
	}
}

func TestHaproxyConfigMatchesCleanupPlan(t *testing.T) {
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "liveline-haproxy-23843.cfg")
	config := `frontend liveline_transit_23843
    bind 0.0.0.0:23843
    default_backend liveline_landing_23843

backend liveline_landing_23843
    server landing 64.90.13.19:27939 check
`
	if err := os.WriteFile(configPath, []byte(config), 0o644); err != nil {
		t.Fatalf("write config: %v", err)
	}
	plan := remoteCleanupPlan{
		ListenPort: 23843,
		TargetHost: "64.90.13.19",
		TargetPort: 27939,
	}
	if !haproxyConfigMatchesCleanupPlan(configPath, plan) {
		t.Fatal("haproxyConfigMatchesCleanupPlan rejected matching config")
	}
	plan.TargetPort = 443
	if haproxyConfigMatchesCleanupPlan(configPath, plan) {
		t.Fatal("haproxyConfigMatchesCleanupPlan accepted wrong target port")
	}
}

func TestValidLiveLineXrayServiceName(t *testing.T) {
	for _, service := range []string{"liveline-xray.service", "liveline-xray-27939.service", "liveline-xray-a71472c6f62c.service"} {
		if !validLiveLineXrayServiceName(service) {
			t.Fatalf("validLiveLineXrayServiceName(%q) = false", service)
		}
	}
	for _, service := range []string{"xray.service", "liveline-xray", "../liveline-xray.service", "liveline-xray.service/extra"} {
		if validLiveLineXrayServiceName(service) {
			t.Fatalf("validLiveLineXrayServiceName(%q) = true", service)
		}
	}
}

func TestSafeLiveLineXrayConfigPathRejectsBroadDirectories(t *testing.T) {
	for _, path := range []string{"/", "/opt", "/usr", "/usr/local/bin", "/etc", "/tmp/liveline-xray/config.json", "/opt/liveline-xray/../x"} {
		if safeLiveLineXrayConfigPath(path) {
			t.Fatalf("safeLiveLineXrayConfigPath(%q) = true", path)
		}
	}
	if !safeLiveLineXrayConfigPath("/opt/liveline-xray/config/config.json") {
		t.Fatal("safeLiveLineXrayConfigPath rejected managed liveline config path")
	}
}

func TestRemoteCleanupFailureResultKeepsSystemRecordBoundary(t *testing.T) {
	request := remoteCleanupRequest{
		CleanupType: "cleanup_transit_route",
		Plans:       []remoteCleanupPlan{{RouteID: "route-1"}},
	}
	result := remoteCleanupFailureResult(config{Role: "transit", InterfaceName: "eth0"}, "host", request, nil, errors.New("service mismatch"))
	if result["status"] != "failed" {
		t.Fatalf("status = %#v, want failed", result["status"])
	}
	if result["system_record_delete_after_success"] != false {
		t.Fatal("failure result allowed system record delete")
	}
}

func TestLandingNodeSSMatchingLinesDetectsListenPort(t *testing.T) {
	ssOutput := `
State   Recv-Q Send-Q Local Address:Port Peer Address:Port Process
LISTEN  0      4096   0.0.0.0:27939     0.0.0.0:*     users:(("xray",pid=123,fd=7))
LISTEN  0      4096   [::]:27939        [::]:*        users:(("xray",pid=123,fd=8))
LISTEN  0      4096   *:27939           *:*           users:(("xray",pid=123,fd=9))
LISTEN  0      4096   127.0.0.1:22      0.0.0.0:*     users:(("sshd",pid=1,fd=3))
`
	if !portListeningInSSOutput(ssOutput, 27939) {
		t.Fatal("portListeningInSSOutput did not detect 27939")
	}
	matches := ssMatchingLinesForPort(ssOutput, 27939)
	if len(matches) != 3 {
		t.Fatalf("len(matches) = %d, want 3: %#v", len(matches), matches)
	}
	if portListeningInSSOutput(ssOutput, 27938) {
		t.Fatal("portListeningInSSOutput detected wrong port")
	}
}

func TestLandingNodeCreateFailedSubmitKeepsDiagnosticsAndDropsSecrets(t *testing.T) {
	result := map[string]any{
		"status":               "failed",
		"summary":              "approved TCP port 27939 is not listening after Xray start",
		"redacted_error":       "approved TCP port 27939 is not listening after Xray start",
		"worker_version":       workerVersion,
		"node_name":            "liveline-reality-27939",
		"listen_port":          formalLandingPort,
		"xray_service_active":  "active",
		"xray_service_enabled": "enabled",
		"xray_config_exists":   true,
		"xray_binary_exists":   true,
		"xray_config_test_ok":  true,
		"xray_config_inbounds_summary": []any{
			map[string]any{
				"tag":        "liveline-reality",
				"listen":     "0.0.0.0",
				"port":       formalLandingPort,
				"protocol":   "vless",
				"settings":   map[string]any{"clients": []any{map[string]any{"id": "must-not-survive"}}},
				"privateKey": "must-not-survive",
			},
		},
		"listen_check_attempts": []any{
			map[string]any{"attempt": 1, "xray_service_active": "active", "port_listening": false, "ss_matching_lines": []any{}},
		},
		"ss_listen_summary":      []any{"LISTEN 0 4096 0.0.0.0:22 0.0.0.0:* users:((\"sshd\"))"},
		"systemd_status_summary": "liveline-xray.service active",
		"journal_tail_summary":   "Started liveline-xray.service",
		"rollback_performed":     true,
		"rollback_summary":       []any{map[string]any{"action": "remove", "target": managedXrayConfigPath, "ok": true}},
		"phases":                 []map[string]any{{"name": "verify_listening", "status": "failed", "summary": "not listening"}},
		"secure_share_link":      "vless" + "://fake-redacted-example",
		"uuid":                   "must-not-survive",
		"reality_private_key":    "must-not-survive",
		"reality_short_id":       "must-not-survive",
	}

	submitResult, _ := prepareCommandResultForSubmit("landing_node_create", sanitizeCommandResult("landing_node_create", result))
	if submitResult["status"] != "failed" {
		t.Fatalf("status = %#v, want failed", submitResult["status"])
	}
	if submitResult["xray_service_active"] != "active" {
		t.Fatalf("xray_service_active = %#v, want active", submitResult["xray_service_active"])
	}
	if submitResult["secure_share_link"] != nil {
		t.Fatal("failed submit result retained secure_share_link")
	}
	if submitResult["uuid"] != nil || submitResult["reality_private_key"] != nil || submitResult["reality_short_id"] != nil {
		t.Fatal("failed submit result retained sensitive Reality fields")
	}
	inbounds, ok := submitResult["xray_config_inbounds_summary"].([]any)
	if !ok || len(inbounds) != 1 {
		t.Fatalf("xray_config_inbounds_summary = %#v, want one item", submitResult["xray_config_inbounds_summary"])
	}
	inbound, ok := inbounds[0].(map[string]any)
	if !ok {
		t.Fatalf("inbound summary item = %#v, want map", inbounds[0])
	}
	if inbound["settings"] != nil || inbound["privateKey"] != nil {
		t.Fatalf("inbound summary retained unsafe fields: %#v", inbound)
	}
	if inbound["port"] != formalLandingPort {
		t.Fatalf("inbound port = %#v, want %d", inbound["port"], formalLandingPort)
	}
	attempts, ok := submitResult["listen_check_attempts"].([]any)
	if !ok || len(attempts) != 1 {
		t.Fatalf("listen_check_attempts = %#v, want one item", submitResult["listen_check_attempts"])
	}
	phases, ok := submitResult["phases"].([]any)
	if !ok || len(phases) != 1 {
		t.Fatalf("phases = %#v, want one item", submitResult["phases"])
	}
}

func TestLandingNodeCreateSuccessSubmitKeepsSecureShareLinkForBackendIngest(t *testing.T) {
	shareLink := "vless" + "://fake-redacted-example"
	sanitized := sanitizeCommandResult("landing_node_create", map[string]any{
		"status":             "succeeded",
		"node_name":          "liveline-reality-27939",
		"listen_port":        formalLandingPort,
		"protocol":           "vless",
		"security":           "reality",
		"flow":               "xtls-rprx-vision",
		"uuid":               "00000000-0000-0000-0000-000000000000",
		"reality_public_key": "fake-public-key",
		"reality_short_id":   "abcdef",
		"secure_share_link":  shareLink,
		"share_link_present": true,
	})
	if sanitized["secure_share_link"] != shareLink {
		t.Fatalf("secure_share_link = %#v, want backend ingest value", sanitized["secure_share_link"])
	}
}
