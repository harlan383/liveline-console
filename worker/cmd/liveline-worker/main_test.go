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
