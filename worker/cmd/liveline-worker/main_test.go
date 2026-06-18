package main

import (
	"encoding/json"
	"errors"
	"os"
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
