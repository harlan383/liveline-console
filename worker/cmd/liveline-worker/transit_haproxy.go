package main

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

const transitHaproxyForwardingMethod = "haproxy_tcp"
const transitHaproxyServicePrefix = "liveline-haproxy"
const transitHaproxyConfigDir = "/etc/haproxy/liveline/routes"

var livelineHaproxyServiceNameRE = regexp.MustCompile(`^liveline-haproxy-[0-9]+\.service$`)

type transitHaproxyCreateArtifacts struct {
	ConfigWritten   bool
	ServiceWritten  bool
	DaemonReloaded  bool
	ServiceEnabled  bool
	ServiceStarted  bool
	RollbackAttempt bool
	ConfigPath      string
	ServiceName     string
	ServicePath     string
}

func isTransitHaproxyForwardingMethod(method string) bool {
	cleaned := strings.TrimSpace(strings.ToLower(strings.ReplaceAll(method, "-", "_")))
	return cleaned == "haproxy" || cleaned == transitHaproxyForwardingMethod
}

func normalizeTransitHaproxyForwardingMethod(method string) string {
	if isTransitHaproxyForwardingMethod(method) {
		return transitHaproxyForwardingMethod
	}
	return strings.TrimSpace(strings.ToLower(method))
}

func transitHaproxyServiceNameForPort(port int) string {
	return fmt.Sprintf("%s-%d.service", transitHaproxyServicePrefix, port)
}

func transitHaproxyServicePathForPort(port int) string {
	return filepath.Join(transitSystemdDir, transitHaproxyServiceNameForPort(port))
}

func transitHaproxyConfigPathForPort(port int) string {
	return filepath.Join(transitHaproxyConfigDir, fmt.Sprintf("%s-%d.cfg", transitHaproxyServicePrefix, port))
}

func findHaproxyBinary() (string, error) {
	candidates := []string{"/usr/sbin/haproxy", "/usr/bin/haproxy"}
	for _, candidate := range candidates {
		if info, err := os.Stat(candidate); err == nil && !info.IsDir() {
			return candidate, nil
		}
	}
	if path, err := exec.LookPath("haproxy"); err == nil && strings.TrimSpace(path) != "" {
		return path, nil
	}
	return "", errors.New("HAPROXY_NOT_INSTALLED: haproxy binary was not found on this transit server")
}

func validateTransitRouteCreateHaproxyRequest(cfg config, request transitRouteCreateRequest) error {
	if request.DryRun {
		return errors.New("haproxy_tcp real execution requires dry_run=false")
	}
	if request.ApprovalRequired {
		return errors.New("haproxy_tcp real execution requires approval_required=false")
	}
	if request.ExecutionMode != "real_create" {
		return errors.New("haproxy_tcp real execution requires execution_mode=real_create")
	}
	if request.ApprovalStage != approvedTransitRealCreateStage {
		return errors.New("haproxy_tcp approval_stage does not match protected real-create stage")
	}
	if !request.ApprovedReal {
		return errors.New("haproxy_tcp requires approved_real_execution=true")
	}
	if !request.SecurityGroupOK || !request.CloudFirewallOK || !request.ServerFirewallOK {
		return errors.New("haproxy_tcp requires firewall confirmations")
	}
	if !request.NoShareLinkChange || !request.NoFullClientLink || !request.NoCutover {
		return errors.New("haproxy_tcp requires no share-link, no full-link, and no-cutover confirmations")
	}
	if err := validateTransitRouteCreateWorkerApproval(cfg, request); err != nil {
		return err
	}
	if normalizeTransitHaproxyForwardingMethod(request.ForwardingMethod) != transitHaproxyForwardingMethod {
		return errors.New("haproxy_tcp create path requires forwarding_method=haproxy_tcp")
	}
	if !validTCPPort(request.PlannedListenPort) || !validTCPPort(request.LandingTargetPort) {
		return errors.New("haproxy_tcp ports must be 1-65535")
	}
	if reason, reserved := protectedTransitListenPorts[request.PlannedListenPort]; reserved {
		return fmt.Errorf("haproxy_tcp planned listen port is protected: %s", reason)
	}
	if !safeDialTargetHost(request.LandingTargetHost) {
		return errors.New("haproxy_tcp landing target host is invalid")
	}
	if !transitRouteNameRE.MatchString(request.RouteName) {
		return errors.New("haproxy_tcp route_name contains unsafe characters")
	}
	serviceName := transitHaproxyServiceNameForPort(request.PlannedListenPort)
	if !livelineHaproxyServiceNameRE.MatchString(serviceName) {
		return errors.New("haproxy_tcp generated service_name is not an approved LiveLine HAProxy service")
	}
	return nil
}

func executeTransitRouteCreateHaproxy(cfg config, hostname string, request transitRouteCreateRequest) (map[string]any, error) {
	if err := validateTransitRouteCreateHaproxyRequest(cfg, request); err != nil {
		return nil, err
	}
	if os.Geteuid() != 0 {
		return nil, errors.New("haproxy_tcp real execution must run as root because systemd service is managed")
	}
	haproxyBinary, err := findHaproxyBinary()
	if err != nil {
		return nil, err
	}
	if _, err := exec.LookPath("systemctl"); err != nil {
		return nil, errors.New("haproxy_tcp requires systemctl")
	}

	configPath := transitHaproxyConfigPathForPort(request.PlannedListenPort)
	serviceName := transitHaproxyServiceNameForPort(request.PlannedListenPort)
	servicePath := transitHaproxyServicePathForPort(request.PlannedListenPort)
	if err := ensureTransitHaproxyPathAvailable(configPath); err != nil {
		return nil, err
	}
	if err := ensureTransitHaproxyPathAvailable(servicePath); err != nil {
		return nil, err
	}
	if portListening(request.PlannedListenPort) {
		return nil, fmt.Errorf("haproxy_tcp TCP port %d is already listening", request.PlannedListenPort)
	}
	reachable, reachDetail := tcpReachability(request.LandingTargetHost, request.LandingTargetPort)
	if !reachable {
		return nil, fmt.Errorf("haproxy_tcp landing target is not reachable: %s", reachDetail)
	}

	artifacts := &transitHaproxyCreateArtifacts{
		ConfigPath:  configPath,
		ServiceName: serviceName,
		ServicePath: servicePath,
	}
	failWithRollback := func(commandErr error, listenAttempts []any) (map[string]any, error) {
		diagnostics := collectTransitHaproxyDiagnostics(serviceName, servicePath, configPath, request.PlannedListenPort)
		rollbackTransitHaproxyCreate(artifacts, request.PlannedListenPort)
		return transitRouteCreateHaproxyFailureResult(cfg, hostname, request, commandErr, diagnostics, listenAttempts, true), commandErr
	}

	if err := os.MkdirAll(transitHaproxyConfigDir, 0o755); err != nil {
		return failWithRollback(fmt.Errorf("haproxy_tcp failed to create config directory: %w", err), nil)
	}
	if err := os.WriteFile(configPath, []byte(transitHaproxyConfigContent(request)), 0o644); err != nil {
		return failWithRollback(fmt.Errorf("haproxy_tcp failed to write config: %w", err), nil)
	}
	artifacts.ConfigWritten = true
	if _, err := runCommand(20*time.Second, haproxyBinary, "-c", "-f", configPath); err != nil {
		return failWithRollback(fmt.Errorf("haproxy_tcp config validation failed: %w", err), nil)
	}
	if err := os.WriteFile(servicePath, []byte(transitHaproxyServiceContent(haproxyBinary, configPath, request.PlannedListenPort)), 0o644); err != nil {
		return failWithRollback(fmt.Errorf("haproxy_tcp failed to write systemd service: %w", err), nil)
	}
	artifacts.ServiceWritten = true
	if _, err := runCommand(30*time.Second, "systemctl", "daemon-reload"); err != nil {
		return failWithRollback(fmt.Errorf("haproxy_tcp daemon-reload failed: %w", err), nil)
	}
	artifacts.DaemonReloaded = true
	if _, err := runCommand(45*time.Second, "systemctl", "enable", "--now", serviceName); err != nil {
		return failWithRollback(fmt.Errorf("haproxy_tcp enable/start failed: %w", err), nil)
	}
	artifacts.ServiceEnabled = true
	artifacts.ServiceStarted = true
	listenAttempts, err := verifyTransitHaproxyActiveAndListening(serviceName, request.PlannedListenPort)
	if err != nil {
		return failWithRollback(err, listenAttempts)
	}

	return map[string]any{
		"status":              "succeeded",
		"execution_mode":      "real_create",
		"real_execution":      true,
		"summary":             fmt.Sprintf("HAProxy TCP transit route created and verified for listen %d to landing target %d.", request.PlannedListenPort, request.LandingTargetPort),
		"worker_version":      workerVersion,
		"hostname":            hostname,
		"role":                cfg.Role,
		"interface_name":      cfg.InterfaceName,
		"transit_resource_id": request.TransitResourceID,
		"landing_node_id":     request.LandingNodeID,
		"planned_listen_port": request.PlannedListenPort,
		"landing_target_host": request.LandingTargetHost,
		"landing_target_port": request.LandingTargetPort,
		"forwarding_method":   transitHaproxyForwardingMethod,
		"purpose":             request.Purpose,
		"approval_stage":      request.ApprovalStage,
		"route_name":          request.RouteName,
		"service_name":        serviceName,
		"service_path":        servicePath,
		"config_path":         configPath,
		"checks": []any{
			map[string]any{"name": "worker_binding_match", "passed": true},
			map[string]any{"name": "haproxy_binary_found", "passed": true},
			map[string]any{"name": "haproxy_config_valid", "passed": true},
			map[string]any{"name": "planned_port_available", "passed": true},
			map[string]any{"name": "landing_target_reachable", "passed": true},
			map[string]any{"name": "haproxy_service_active", "passed": true},
			map[string]any{"name": "listener_verified", "passed": true},
			map[string]any{"name": "no_node_share_link_read_or_modified", "passed": true},
		},
		"listen_verification_attempts": listenAttempts,
		"safety_boundary": []any{
			"approved real create only",
			"fixed HAProxy TCP template only",
			"no arbitrary shell accepted",
			"no firewall mutation",
			"no Xray mutation",
			"no nodes.share_link read or modification",
			"no full client link export",
			"no cutover",
		},
	}, nil
}

func ensureTransitHaproxyPathAvailable(path string) error {
	if _, err := os.Stat(path); err == nil {
		return fmt.Errorf("haproxy_tcp refuses to overwrite existing path %s", path)
	} else if !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("haproxy_tcp cannot inspect path %s: %w", path, err)
	}
	return nil
}

func transitHaproxyConfigContent(request transitRouteCreateRequest) string {
	return fmt.Sprintf(`global
    log /dev/log local0
    maxconn 4096

defaults
    mode tcp
    log global
    option tcplog
    timeout connect 5s
    timeout client 6h
    timeout server 6h

frontend liveline_transit_%d
    bind 0.0.0.0:%d
    default_backend liveline_landing_%d

backend liveline_landing_%d
    mode tcp
    option tcp-check
    server landing %s:%d check
`, request.PlannedListenPort, request.PlannedListenPort, request.PlannedListenPort, request.PlannedListenPort, request.LandingTargetHost, request.LandingTargetPort)
}

func transitHaproxyServiceContent(haproxyBinary string, configPath string, listenPort int) string {
	return fmt.Sprintf(`[Unit]
Description=LiveLine HAProxy TCP transit route %d
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=%s -f %s -db
ExecReload=/bin/kill -USR2 $MAINPID
Restart=always
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
`, listenPort, haproxyBinary, configPath)
}

func verifyTransitHaproxyActiveAndListening(serviceName string, listenPort int) ([]any, error) {
	attempts := []any{}
	var lastActive string
	var lastListener bool
	var lastErr error
	for index := 1; index <= 8; index++ {
		output, err := runCommand(8*time.Second, "systemctl", "is-active", serviceName)
		active := strings.TrimSpace(output)
		if active == "" && err != nil {
			active = "unknown"
		}
		listener := portListening(listenPort)
		attempts = append(attempts, map[string]any{
			"attempt":           index,
			"service_active":    active,
			"listener_detected": listener,
		})
		fmt.Printf("haproxy_tcp listen_verification attempt=%d service_active=%s listener_detected=%v\n", index, active, listener)
		lastActive = active
		lastListener = listener
		lastErr = err
		if err == nil && active == "active" && listener {
			return attempts, nil
		}
		if index < 8 {
			time.Sleep(1 * time.Second)
		}
	}
	if lastErr != nil {
		return attempts, fmt.Errorf("haproxy_tcp service did not become verifiably active/listening: active=%s listener=%v error=%w", lastActive, lastListener, lastErr)
	}
	if lastActive != "active" {
		return attempts, fmt.Errorf("%s is not active after retry: %s", serviceName, lastActive)
	}
	return attempts, fmt.Errorf("TCP port %d is not listening after HAProxy start retries", listenPort)
}

func collectTransitHaproxyDiagnostics(serviceName string, servicePath string, configPath string, listenPort int) map[string]any {
	diagnostics := map[string]any{}
	if output, err := runCommand(8*time.Second, "systemctl", "is-active", serviceName); err != nil {
		diagnostics["systemctl_is_active"] = compactDiagnosticOutput(output, err)
	} else {
		diagnostics["systemctl_is_active"] = compactDiagnosticOutput(output, nil)
	}
	if output, err := runCommand(12*time.Second, "systemctl", "status", "--no-pager", "-l", serviceName); err != nil {
		diagnostics["systemctl_status"] = compactDiagnosticOutput(output, err)
	} else {
		diagnostics["systemctl_status"] = compactDiagnosticOutput(output, nil)
	}
	if output, err := runCommand(12*time.Second, "journalctl", "-u", serviceName, "-n", "80", "--no-pager"); err != nil {
		diagnostics["journal"] = compactDiagnosticOutput(output, err)
	} else {
		diagnostics["journal"] = compactDiagnosticOutput(output, nil)
	}
	if output, err := runCommand(8*time.Second, "ss", "-lntp"); err != nil {
		diagnostics["listen_socket"] = compactDiagnosticOutput(filterTransitHaproxyListenSocket(output, listenPort), err)
	} else {
		diagnostics["listen_socket"] = compactDiagnosticOutput(filterTransitHaproxyListenSocket(output, listenPort), nil)
	}
	diagnostics["service_file"] = transitHaproxyFileSummary(servicePath, "liveline HAProxy service")
	diagnostics["config_file"] = transitHaproxyFileSummary(configPath, "liveline_transit")
	return diagnostics
}

func filterTransitHaproxyListenSocket(output string, listenPort int) string {
	needleSpace := fmt.Sprintf(":%d ", listenPort)
	needleTab := fmt.Sprintf(":%d\t", listenPort)
	lines := []string{}
	for _, line := range strings.Split(output, "\n") {
		if strings.Contains(line, needleSpace) || strings.Contains(line, needleTab) {
			lines = append(lines, strings.TrimSpace(line))
		}
	}
	if len(lines) == 0 {
		return fmt.Sprintf("no listener line for :%d", listenPort)
	}
	return strings.Join(lines, "\n")
}

func transitHaproxyFileSummary(path string, expectedMarker string) map[string]any {
	content, err := os.ReadFile(path)
	if err != nil {
		return map[string]any{
			"exists": false,
			"error":  truncateTransitHaproxyString(err.Error(), 180),
		}
	}
	text := string(content)
	return map[string]any{
		"exists":          true,
		"size_bytes":      len(content),
		"contains_marker": strings.Contains(text, expectedMarker),
	}
}

func transitRouteCreateHaproxyFailureResult(cfg config, hostname string, request transitRouteCreateRequest, commandErr error, diagnostics map[string]any, listenAttempts []any, rollbackAttempted bool) map[string]any {
	return map[string]any{
		"command_type":                 "transit_route_create",
		"status":                       "failed",
		"execution_mode":               "real_create",
		"real_execution":               true,
		"summary":                      "HAProxy TCP transit route creation failed; rollback was attempted before reporting.",
		"redacted_error":               truncateTransitHaproxyString(errorString(commandErr), 220),
		"worker_version":               workerVersion,
		"hostname":                     hostname,
		"role":                         cfg.Role,
		"interface_name":               cfg.InterfaceName,
		"transit_resource_id":          request.TransitResourceID,
		"landing_node_id":              request.LandingNodeID,
		"planned_listen_port":          request.PlannedListenPort,
		"landing_target_host":          request.LandingTargetHost,
		"landing_target_port":          request.LandingTargetPort,
		"forwarding_method":            transitHaproxyForwardingMethod,
		"purpose":                      request.Purpose,
		"approval_stage":               request.ApprovalStage,
		"route_name":                   request.RouteName,
		"service_name":                 transitHaproxyServiceNameForPort(request.PlannedListenPort),
		"service_path":                 transitHaproxyServicePathForPort(request.PlannedListenPort),
		"config_path":                  transitHaproxyConfigPathForPort(request.PlannedListenPort),
		"diagnostics":                  diagnostics,
		"listen_verification_attempts": listenAttempts,
		"rollback_attempted":           rollbackAttempted,
		"checks": []any{
			map[string]any{"name": "fixed_haproxy_tcp_template_only", "passed": true},
			map[string]any{"name": "listener_verified", "passed": false},
			map[string]any{"name": "rollback_attempted", "passed": rollbackAttempted},
			map[string]any{"name": "no_node_share_link_read_or_modified", "passed": true},
		},
		"safety_boundary": []any{
			"approved real create only",
			"fixed HAProxy TCP template only",
			"no firewall mutation",
			"no Xray mutation",
			"no nodes.share_link read or modification",
			"no full client link export",
			"no cutover",
		},
	}
}

func rollbackTransitHaproxyCreate(artifacts *transitHaproxyCreateArtifacts, listenPort int) {
	if artifacts == nil {
		return
	}
	artifacts.RollbackAttempt = true
	if artifacts.ServiceStarted {
		_, _ = runCommand(30*time.Second, "systemctl", "stop", artifacts.ServiceName)
	}
	if artifacts.ServiceEnabled {
		_, _ = runCommand(30*time.Second, "systemctl", "disable", artifacts.ServiceName)
	}
	if artifacts.ServiceWritten && safeTransitHaproxyServicePath(artifacts.ServicePath, listenPort) {
		_ = os.Remove(artifacts.ServicePath)
	}
	if artifacts.ConfigWritten && safeTransitHaproxyConfigPath(artifacts.ConfigPath, listenPort) {
		_ = os.Remove(artifacts.ConfigPath)
	}
	if artifacts.DaemonReloaded || artifacts.ServiceWritten {
		_, _ = runCommand(30*time.Second, "systemctl", "daemon-reload")
		_, _ = runCommand(15*time.Second, "systemctl", "reset-failed", artifacts.ServiceName)
	}
}

func safeTransitHaproxyServicePath(path string, listenPort int) bool {
	return path == transitHaproxyServicePathForPort(listenPort) && filepath.Dir(path) == transitSystemdDir
}

func safeTransitHaproxyConfigPath(path string, listenPort int) bool {
	return path == transitHaproxyConfigPathForPort(listenPort) && filepath.Dir(path) == transitHaproxyConfigDir
}

func truncateTransitHaproxyString(value string, limit int) string {
	cleaned := strings.TrimSpace(value)
	if limit <= 0 || len(cleaned) <= limit {
		return cleaned
	}
	return cleaned[:limit] + "..."
}
