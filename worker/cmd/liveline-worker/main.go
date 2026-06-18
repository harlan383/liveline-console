package main

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
)

const workerVersion = "0.1.18-stage-3.3.72"
const commandPollIntervalSeconds = 20
const readonlyCommandTimeout = 5 * time.Second
const readonlyOutputLimit = 12000
const commandOutputLimit = 12000
const resultStringLimit = 1000
const resultListLimit = 50
const resultPayloadSoftLimit = 64 * 1024
const transitReadonlyCompactPayloadTarget = 1200
const transitReadonlyCompactSummaryLimit = 160
const transitReadonlyCompactCheckDetailLimit = 48
const transitRouteCreateCompactPayloadTarget = 1100
const transitRouteCreateCompactSummaryLimit = 160
const transitRouteCreateCompactCheckDetailLimit = 48
const workerFailurePayloadTarget = 1100
const workerFailureErrorMessageLimit = 220
const responseBodyLogLimit = 1200
const postJSONTimeout = 15 * time.Second
const commandTimeout = 180 * time.Second
const formalLandingPort = 27939
const approvedTransitCreateStage = "Stage 3.3.71-transit-route-worker-create-path"
const approvedTransitResourceID = "1e222459-9fa2-4c62-800f-a3b35edb7df8"
const approvedTransitLandingNodeID = "a71472c6-f62c-43b5-a223-9f5f070ae4ef"
const approvedTransitListenPort = 23843
const approvedTransitLandingTargetHost = "64.90.13.19"
const approvedTransitLandingTargetPort = 27939
const approvedTransitForwardingMethod = "socat"
const approvedTransitInterfaceName = "eth0"
const transitSocatServicePrefix = "liveline-socat"
const transitSystemdDir = "/etc/systemd/system"
const xrayDownloadURL = "https://github.com/XTLS/Xray-core/releases/download/v25.1.1/Xray-linux-64.zip"
const managedXrayBaseDir = "/opt/liveline-xray"
const managedXrayBinDir = "/opt/liveline-xray/bin"
const managedXrayBinaryPath = "/opt/liveline-xray/bin/xray"
const managedXrayConfigDir = "/opt/liveline-xray/config"
const managedXrayConfigPath = "/opt/liveline-xray/config/config.json"
const managedXrayStateDir = "/opt/liveline-xray/state"
const managedXrayServiceName = "liveline-xray.service"
const managedXrayServicePath = "/etc/systemd/system/liveline-xray.service"

var postJSONHTTPClient = &http.Client{Timeout: postJSONTimeout}
var postJSONFunc = postJSON
var postJSONViaCurlFunc = postJSONViaCurl

var protectedTransitListenPorts = map[int]string{
	22:    "22 is reserved for SSH management",
	8443:  "8443 is reserved for gost fallback",
	18443: "18443 is reserved for the current socat formal route",
	20575: "20575 is a historical unsafe transit port",
}

type config struct {
	ConsoleURL               string
	WorkerID                 string
	WorkerSecret             string
	Role                     string
	InterfaceName            string
	HeartbeatIntervalSeconds int
}

type apiResponse[T any] struct {
	Success   bool   `json:"success"`
	Data      T      `json:"data"`
	Message   string `json:"message"`
	ErrorCode string `json:"error_code"`
}

type registerPayload struct {
	Token         string         `json:"token"`
	Role          string         `json:"role"`
	InterfaceName string         `json:"interface_name"`
	Hostname      string         `json:"hostname"`
	PublicIP      string         `json:"public_ip,omitempty"`
	WorkerVersion string         `json:"worker_version"`
	SystemInfo    map[string]any `json:"system_info"`
}

type registerResult struct {
	WorkerID                 string `json:"worker_id"`
	ServerID                 string `json:"server_id"`
	Role                     string `json:"role"`
	WorkerSecret             string `json:"worker_secret"`
	HeartbeatIntervalSeconds int    `json:"heartbeat_interval_seconds"`
	ServerTime               string `json:"server_time"`
}

type heartbeatPayload struct {
	WorkerVersion string         `json:"worker_version"`
	Role          string         `json:"role"`
	InterfaceName string         `json:"interface_name"`
	Hostname      string         `json:"hostname"`
	PublicIP      string         `json:"public_ip,omitempty"`
	UptimeSeconds int64          `json:"uptime_seconds,omitempty"`
	OS            string         `json:"os,omitempty"`
	Kernel        string         `json:"kernel,omitempty"`
	CPU           map[string]any `json:"cpu,omitempty"`
	Memory        map[string]any `json:"memory,omitempty"`
	Disk          map[string]any `json:"disk,omitempty"`
	Services      map[string]any `json:"services,omitempty"`
}

type heartbeatResult struct {
	OK                   bool   `json:"ok"`
	ServerTime           string `json:"server_time"`
	NextHeartbeatSeconds int    `json:"next_heartbeat_seconds"`
}

type workerCommand struct {
	ID          string         `json:"id"`
	CommandType string         `json:"command_type"`
	Payload     map[string]any `json:"payload"`
}

type commandNextResult struct {
	OK              bool           `json:"ok"`
	Command         *workerCommand `json:"command"`
	NextPollSeconds int            `json:"next_poll_seconds"`
}

type commandResultPayload struct {
	Result map[string]any `json:"result"`
}

type commandFailurePayload struct {
	ErrorMessage string         `json:"error_message"`
	Result       map[string]any `json:"result,omitempty"`
}

type compactResultInfo struct {
	OriginalSubmitPayloadSize int
	CompactSubmitPayloadSize  int
	CompactApplied            bool
	ChecksCount               int
	MaxDetailLength           int
	DetailsRemoved            bool
}

func main() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(2)
	}

	var err error
	switch os.Args[1] {
	case "register":
		err = runRegister(os.Args[2:])
	case "run":
		err = runWorker(os.Args[2:])
	case "diagnose-transit-readonly-payload":
		err = runDiagnoseTransitReadonlyPayload(os.Args[2:])
	case "version", "--version", "-v":
		fmt.Println(workerVersion)
		return
	default:
		printUsage()
		os.Exit(2)
	}

	if err != nil {
		fmt.Fprintf(os.Stderr, "liveline-worker: %v\n", err)
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Fprintln(os.Stderr, "usage:")
	fmt.Fprintln(os.Stderr, "  liveline-worker register --config /etc/liveline-worker/config.yaml --console-url URL --token TOKEN --role landing|transit --interface eth0")
	fmt.Fprintln(os.Stderr, "  liveline-worker run --config /etc/liveline-worker/config.yaml")
	fmt.Fprintln(os.Stderr, "  liveline-worker diagnose-transit-readonly-payload --config /etc/liveline-worker/config.yaml --payload-json JSON")
	fmt.Fprintln(os.Stderr, "  liveline-worker version")
}

func runRegister(args []string) error {
	fs := flag.NewFlagSet("register", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	configPath := fs.String("config", "/etc/liveline-worker/config.yaml", "config file path")
	consoleURL := fs.String("console-url", "", "console base URL")
	rawToken := fs.String("token", "", "one-time worker token")
	role := fs.String("role", "", "worker role")
	interfaceName := fs.String("interface", "", "network interface name")
	if err := fs.Parse(args); err != nil {
		return err
	}

	cleanRole, err := validateRole(*role)
	if err != nil {
		return err
	}
	if strings.TrimSpace(*consoleURL) == "" {
		return errors.New("console-url is required")
	}
	if strings.TrimSpace(*rawToken) == "" {
		return errors.New("token is required")
	}
	if strings.TrimSpace(*interfaceName) == "" {
		return errors.New("interface is required")
	}

	hostname, _ := os.Hostname()
	if hostname == "" {
		hostname = "unknown"
	}
	publicIP := interfaceAddress(*interfaceName)
	systemInfo := collectSystemInfo(cleanRole, *interfaceName)

	payload := registerPayload{
		Token:         strings.TrimSpace(*rawToken),
		Role:          cleanRole,
		InterfaceName: strings.TrimSpace(*interfaceName),
		Hostname:      hostname,
		PublicIP:      publicIP,
		WorkerVersion: workerVersion,
		SystemInfo:    systemInfo,
	}

	var response apiResponse[registerResult]
	if err := postJSON(joinURL(*consoleURL, "/api/workers/register"), nil, payload, &response); err != nil {
		return err
	}
	if !response.Success {
		return fmt.Errorf("register failed: %s", response.Message)
	}
	if response.Data.WorkerID == "" || response.Data.WorkerSecret == "" {
		return errors.New("register response missing worker credentials")
	}

	interval := response.Data.HeartbeatIntervalSeconds
	if interval <= 0 {
		interval = 60
	}
	cfg := config{
		ConsoleURL:               strings.TrimRight(strings.TrimSpace(*consoleURL), "/"),
		WorkerID:                 response.Data.WorkerID,
		WorkerSecret:             response.Data.WorkerSecret,
		Role:                     cleanRole,
		InterfaceName:            strings.TrimSpace(*interfaceName),
		HeartbeatIntervalSeconds: interval,
	}
	if err := writeConfig(*configPath, cfg); err != nil {
		return err
	}

	fmt.Printf("LiveLine Worker registered. worker_id=%s role=%s heartbeat=%ds\n", cfg.WorkerID, cfg.Role, cfg.HeartbeatIntervalSeconds)
	return nil
}

func runWorker(args []string) error {
	fs := flag.NewFlagSet("run", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	configPath := fs.String("config", "/etc/liveline-worker/config.yaml", "config file path")
	once := fs.Bool("once", false, "send one heartbeat and exit")
	if err := fs.Parse(args); err != nil {
		return err
	}

	cfg, err := readConfig(*configPath)
	if err != nil {
		return err
	}
	if err := validateConfig(cfg); err != nil {
		return err
	}

	if err := sendHeartbeat(cfg); err != nil {
		fmt.Fprintf(os.Stderr, "liveline-worker heartbeat failed: %v\n", err)
	} else {
		fmt.Println("liveline-worker heartbeat sent")
	}
	if *once {
		return nil
	}

	interval := time.Duration(cfg.HeartbeatIntervalSeconds) * time.Second
	if interval < 10*time.Second {
		interval = 60 * time.Second
	}
	heartbeatTicker := time.NewTicker(interval)
	defer heartbeatTicker.Stop()

	commandTicker := time.NewTicker(time.Duration(commandPollIntervalSeconds) * time.Second)
	defer commandTicker.Stop()

	if err := pollWorkerCommand(cfg); err != nil {
		fmt.Fprintf(os.Stderr, "liveline-worker command poll failed: %v\n", err)
	}

	for {
		select {
		case <-heartbeatTicker.C:
			if err := sendHeartbeat(cfg); err != nil {
				fmt.Fprintf(os.Stderr, "liveline-worker heartbeat failed: %v\n", err)
			} else {
				fmt.Println("liveline-worker heartbeat sent")
			}
		case <-commandTicker.C:
			if err := pollWorkerCommand(cfg); err != nil {
				fmt.Fprintf(os.Stderr, "liveline-worker command poll failed: %v\n", err)
			}
		}
	}
}

func runDiagnoseTransitReadonlyPayload(args []string) error {
	fs := flag.NewFlagSet("diagnose-transit-readonly-payload", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	configPath := fs.String("config", "/etc/liveline-worker/config.yaml", "config file path")
	payloadJSON := fs.String("payload-json", "", "transit_readonly_preflight payload JSON")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if strings.TrimSpace(*payloadJSON) == "" {
		return errors.New("payload-json is required")
	}

	cfg, err := readConfig(*configPath)
	if err != nil {
		return err
	}
	if err := validateConfig(cfg); err != nil {
		return err
	}
	if cfg.Role != "transit" {
		return errors.New("diagnose-transit-readonly-payload requires transit worker role")
	}

	var payload map[string]any
	if err := json.Unmarshal([]byte(*payloadJSON), &payload); err != nil {
		return fmt.Errorf("payload-json must be a JSON object: %w", err)
	}
	if payload == nil {
		return errors.New("payload-json must be a JSON object")
	}

	hostname, _ := os.Hostname()
	if hostname == "" {
		hostname = "unknown"
	}
	result, err := collectTransitReadonlyPreflight(cfg, hostname, payload)
	if err != nil {
		return err
	}
	result["timestamp"] = time.Now().UTC().Format(time.RFC3339)

	summary := buildResultSubmitDebugSummary("transit_readonly_preflight", result)
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	return encoder.Encode(summary)
}

func validateConfig(cfg config) error {
	if strings.TrimSpace(cfg.ConsoleURL) == "" {
		return errors.New("console_url is required")
	}
	if strings.TrimSpace(cfg.WorkerID) == "" {
		return errors.New("worker_id is required")
	}
	if strings.TrimSpace(cfg.WorkerSecret) == "" {
		return errors.New("worker_secret is required")
	}
	if _, err := validateRole(cfg.Role); err != nil {
		return err
	}
	if strings.TrimSpace(cfg.InterfaceName) == "" {
		return errors.New("interface_name is required")
	}
	return nil
}

func sendHeartbeat(cfg config) error {
	hostname, _ := os.Hostname()
	if hostname == "" {
		hostname = "unknown"
	}
	payload := heartbeatPayload{
		WorkerVersion: workerVersion,
		Role:          cfg.Role,
		InterfaceName: cfg.InterfaceName,
		Hostname:      hostname,
		PublicIP:      interfaceAddress(cfg.InterfaceName),
	}
	for key, value := range collectSystemInfo(cfg.Role, cfg.InterfaceName) {
		switch key {
		case "uptime_seconds":
			if v, ok := value.(int64); ok {
				payload.UptimeSeconds = v
			}
		case "os":
			payload.OS = fmt.Sprint(value)
		case "kernel":
			payload.Kernel = fmt.Sprint(value)
		case "cpu":
			if v, ok := value.(map[string]any); ok {
				payload.CPU = v
			}
		case "memory":
			if v, ok := value.(map[string]any); ok {
				payload.Memory = v
			}
		case "disk":
			if v, ok := value.(map[string]any); ok {
				payload.Disk = v
			}
		case "services":
			if v, ok := value.(map[string]any); ok {
				payload.Services = v
			}
		}
	}

	headers := map[string]string{
		"X-Worker-Id":     cfg.WorkerID,
		"X-Worker-Secret": cfg.WorkerSecret,
	}
	var response apiResponse[heartbeatResult]
	if err := postJSON(joinURL(cfg.ConsoleURL, "/api/workers/heartbeat"), headers, payload, &response); err != nil {
		return err
	}
	if !response.Success {
		return fmt.Errorf("heartbeat rejected: %s", response.Message)
	}
	return nil
}

func pollWorkerCommand(cfg config) error {
	headers := map[string]string{
		"X-Worker-Id":     cfg.WorkerID,
		"X-Worker-Secret": cfg.WorkerSecret,
	}
	var response apiResponse[commandNextResult]
	if err := postJSON(joinURL(cfg.ConsoleURL, "/api/workers/commands/next"), headers, map[string]any{}, &response); err != nil {
		return err
	}
	if !response.Success {
		return fmt.Errorf("command poll rejected: %s", response.Message)
	}
	if response.Data.Command == nil {
		return nil
	}

	command := *response.Data.Command
	result, err := executeWorkerCommand(cfg, command)
	if err != nil {
		if reportErr := postWorkerCommandFailure(cfg, command.ID, err, nil); reportErr != nil {
			return fmt.Errorf("command %s failed: %v; failure report failed: %w", command.ID, err, reportErr)
		}
		return fmt.Errorf("command %s failed: %w", command.ID, err)
	}
	if err := postWorkerCommandResult(cfg, command, result); err != nil {
		fallback := fallbackCommandResult(command, err)
		fallbackErr := fmt.Errorf("result submit failed: %w", err)
		if reportErr := postWorkerCommandFailure(cfg, command.ID, fallbackErr, fallback); reportErr != nil {
			return fmt.Errorf("command %s result submit failed: %v; fallback failure report failed: %w", command.ID, err, reportErr)
		}
		return fmt.Errorf("command %s result submit failed and was marked failed with fallback: %w", command.ID, err)
	}
	fmt.Printf("liveline-worker command %s completed type=%s\n", command.ID, command.CommandType)
	return nil
}

func executeWorkerCommand(cfg config, command workerCommand) (map[string]any, error) {
	now := time.Now().UTC().Format(time.RFC3339)
	hostname, _ := os.Hostname()
	if hostname == "" {
		hostname = "unknown"
	}
	switch command.CommandType {
	case "ping":
		return map[string]any{
			"pong":           true,
			"worker_version": workerVersion,
			"hostname":       hostname,
			"role":           cfg.Role,
			"interface_name": cfg.InterfaceName,
			"timestamp":      now,
		}, nil
	case "collect_status":
		result := collectSystemInfo(cfg.Role, cfg.InterfaceName)
		result["hostname"] = hostname
		result["timestamp"] = now
		return result, nil
	case "service_status":
		return map[string]any{
			"worker_version": workerVersion,
			"hostname":       hostname,
			"role":           cfg.Role,
			"interface_name": cfg.InterfaceName,
			"services":       serviceSummary(cfg.Role),
			"timestamp":      now,
		}, nil
	case "landing_preflight":
		if cfg.Role != "landing" {
			return nil, fmt.Errorf("landing_preflight requires landing worker role")
		}
		result := collectLandingPreflight(cfg, hostname)
		result["timestamp"] = now
		return result, nil
	case "landing_node_create":
		if cfg.Role != "landing" {
			return nil, fmt.Errorf("landing_node_create requires landing worker role")
		}
		result, err := executeLandingNodeCreate(cfg, command.Payload)
		if err != nil {
			return nil, err
		}
		result["worker_version"] = workerVersion
		result["hostname"] = hostname
		result["timestamp"] = now
		return result, nil
	case "transit_readonly_preflight":
		if cfg.Role != "transit" {
			return nil, fmt.Errorf("transit_readonly_preflight requires transit worker role")
		}
		result, err := collectTransitReadonlyPreflight(cfg, hostname, command.Payload)
		if err != nil {
			return nil, err
		}
		result["timestamp"] = now
		return result, nil
	case "transit_route_create":
		if cfg.Role != "transit" {
			return nil, fmt.Errorf("transit_route_create requires transit worker role")
		}
		result, err := executeTransitRouteCreateDryRun(cfg, hostname, command)
		if err != nil {
			return nil, err
		}
		result["timestamp"] = now
		return result, nil
	default:
		return nil, fmt.Errorf("unsupported command_type %q", command.CommandType)
	}
}

type transitRouteCreateRequest struct {
	TransitResourceID string
	LandingNodeID     string
	PlannedListenPort int
	LandingTargetHost string
	LandingTargetPort int
	ForwardingMethod  string
	Purpose           string
	ApprovalStage     string
	DryRun            bool
	ApprovalRequired  bool
	RouteName         string
}

func executeTransitRouteCreateDryRun(cfg config, hostname string, command workerCommand) (map[string]any, error) {
	request, err := parseTransitRouteCreateRequest(command.Payload)
	if err != nil {
		return nil, err
	}
	if err := validateTransitRouteCreateRequest(request); err != nil {
		return nil, err
	}
	if cfg.InterfaceName != approvedTransitInterfaceName {
		return nil, fmt.Errorf("transit_route_create interface %s is not approved", cfg.InterfaceName)
	}

	serviceName := transitSocatServiceNameFor(command.ID)
	servicePath := filepath.Join(transitSystemdDir, serviceName)
	return map[string]any{
		"status":              "approval_required",
		"execution_mode":      "dry_run",
		"real_execution":      false,
		"summary":             "Transit route create dry-run accepted; no socat service was written, started, or bound.",
		"worker_version":      workerVersion,
		"hostname":            hostname,
		"role":                cfg.Role,
		"interface_name":      cfg.InterfaceName,
		"transit_resource_id": request.TransitResourceID,
		"landing_node_id":     request.LandingNodeID,
		"planned_listen_port": request.PlannedListenPort,
		"landing_target_host": request.LandingTargetHost,
		"landing_target_port": request.LandingTargetPort,
		"forwarding_method":   request.ForwardingMethod,
		"purpose":             request.Purpose,
		"approval_stage":      request.ApprovalStage,
		"route_name":          request.RouteName,
		"planned_service": map[string]any{
			"name":       serviceName,
			"path":       servicePath,
			"exec_start": fmt.Sprintf("fixed template: socat TCP-LISTEN:%d,fork,reuseaddr TCP:%s:%d", request.PlannedListenPort, request.LandingTargetHost, request.LandingTargetPort),
		},
		"planned_actions": []any{
			"validate approved Stage 3.3.70 parameters",
			"recheck planned listen port before real execution",
			"write LiveLine-managed socat systemd service in the later execution stage",
			"start and verify the service only after a future explicit Stage 3.3.72 authorization",
		},
		"checks": []any{
			map[string]any{"name": "dry_run_required", "passed": true},
			map[string]any{"name": "approved_parameters_match", "passed": true},
			map[string]any{"name": "fixed_socat_template_only", "passed": true},
			map[string]any{"name": "no_arbitrary_shell_payload", "passed": true},
			map[string]any{"name": "no_listener_created", "passed": true},
		},
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
		"next_stage": "Stage 3.3.72-transit-route-create-execution",
	}, nil
}

func parseTransitRouteCreateRequest(payload map[string]any) (transitRouteCreateRequest, error) {
	if path, ok := firstUnsafeTransitCreatePayloadKey(payload); ok {
		return transitRouteCreateRequest{}, fmt.Errorf("transit_route_create payload contains unsupported execution field %s", path)
	}
	request := transitRouteCreateRequest{
		TransitResourceID: stringPayload(payload, "transit_resource_id"),
		LandingNodeID:     stringPayload(payload, "landing_node_id"),
		PlannedListenPort: intPayload(payload, "planned_listen_port"),
		LandingTargetHost: stringPayload(payload, "landing_target_host"),
		LandingTargetPort: intPayload(payload, "landing_target_port"),
		ForwardingMethod:  defaultStringPayload(payload, "forwarding_method", "socat"),
		Purpose:           stringPayload(payload, "purpose"),
		ApprovalStage:     stringPayload(payload, "approval_stage"),
		DryRun:            boolPayload(payload, "dry_run"),
		ApprovalRequired:  boolPayload(payload, "approval_required"),
		RouteName:         defaultStringPayload(payload, "route_name", "hk-socat-live-23843"),
	}
	return request, nil
}

func validateTransitRouteCreateRequest(request transitRouteCreateRequest) error {
	if !request.DryRun {
		return errors.New("transit_route_create requires dry_run=true until Stage 3.3.72")
	}
	if !request.ApprovalRequired {
		return errors.New("transit_route_create requires approval_required=true")
	}
	if request.ApprovalStage != approvedTransitCreateStage {
		return errors.New("transit_route_create approval_stage does not match Stage 3.3.71")
	}
	if request.TransitResourceID != approvedTransitResourceID {
		return errors.New("transit_route_create transit_resource_id is not approved")
	}
	if request.LandingNodeID != approvedTransitLandingNodeID {
		return errors.New("transit_route_create landing_node_id is not approved")
	}
	if request.PlannedListenPort != approvedTransitListenPort {
		return errors.New("transit_route_create planned_listen_port is not approved")
	}
	if request.LandingTargetHost != approvedTransitLandingTargetHost {
		return errors.New("transit_route_create landing_target_host is not approved")
	}
	if request.LandingTargetPort != approvedTransitLandingTargetPort {
		return errors.New("transit_route_create landing_target_port is not approved")
	}
	if request.ForwardingMethod != approvedTransitForwardingMethod {
		return errors.New("transit_route_create only approved socat forwarding")
	}
	if !validTCPPort(request.PlannedListenPort) || !validTCPPort(request.LandingTargetPort) {
		return errors.New("transit_route_create ports must be 1-65535")
	}
	if reason, reserved := protectedTransitListenPorts[request.PlannedListenPort]; reserved {
		return fmt.Errorf("transit_route_create planned listen port is protected: %s", reason)
	}
	if !safeDialTargetHost(request.LandingTargetHost) {
		return errors.New("transit_route_create landing target host is invalid")
	}
	return nil
}

func transitSocatServiceNameFor(commandID string) string {
	return fmt.Sprintf("%s-%s.service", transitSocatServicePrefix, strings.ReplaceAll(commandID, "-", ""))
}

func firstUnsafeTransitCreatePayloadKey(value any) (string, bool) {
	unsafeKeys := map[string]bool{
		"shell":           true,
		"command":         true,
		"commands":        true,
		"args":            true,
		"argv":            true,
		"script":          true,
		"systemd_unit":    true,
		"unit_content":    true,
		"service_content": true,
		"exec_start":      true,
	}
	return firstUnsafeTransitCreatePayloadKeyAt(value, "$", unsafeKeys)
}

func firstUnsafeTransitCreatePayloadKeyAt(value any, path string, unsafeKeys map[string]bool) (string, bool) {
	switch typed := value.(type) {
	case map[string]any:
		for key, item := range typed {
			childPath := path + "." + key
			if unsafeKeys[strings.ToLower(key)] {
				return childPath, true
			}
			if foundPath, ok := firstUnsafeTransitCreatePayloadKeyAt(item, childPath, unsafeKeys); ok {
				return foundPath, true
			}
		}
	case []any:
		for index, item := range typed {
			if foundPath, ok := firstUnsafeTransitCreatePayloadKeyAt(item, fmt.Sprintf("%s[%d]", path, index), unsafeKeys); ok {
				return foundPath, true
			}
		}
	}
	return "", false
}

type transitReadonlyPreflightRequest struct {
	TransitResourceID string
	LandingNodeID     string
	PlannedListenPort int
	LandingTargetHost string
	LandingTargetPort int
	ForwardingMethod  string
	Purpose           string
	Readonly          bool
}

func collectTransitReadonlyPreflight(cfg config, hostname string, payload map[string]any) (map[string]any, error) {
	request, err := parseTransitReadonlyPreflightRequest(payload)
	if err != nil {
		return nil, err
	}

	checks := []map[string]any{}
	addCheck := func(id string, label string, passed bool, status string, detail string) {
		checks = append(checks, map[string]any{
			"id":     id,
			"label":  label,
			"status": status,
			"passed": passed,
			"detail": truncateReadonlyOutput(detail, 600),
		})
	}

	addCheck(
		"worker_identity",
		"Worker identity / version",
		true,
		"passed",
		fmt.Sprintf("worker_version=%s role=%s interface=%s hostname=%s", workerVersion, cfg.Role, cfg.InterfaceName, hostname),
	)

	ssOutput, ssErr := readonlyCommandOutput("ss", "-lntup")
	portRows, _ := listeningPortRows(ssOutput)
	portChecks := portChecksFromRows(portRows, []int{request.PlannedListenPort})
	portListening := false
	portDetail := "planned port is not listening"
	if ssErr != "" {
		portDetail = "ss read unavailable: " + ssErr
	} else if len(portChecks) > 0 {
		if listening, ok := portChecks[0]["listening"].(bool); ok {
			portListening = listening
		}
		portDetail = fmt.Sprintf("planned port %d listening=%v", request.PlannedListenPort, portListening)
	}
	addCheck(
		"planned_port_available",
		"Planned listen port availability",
		ssErr == "" && !portListening,
		statusFromPassed(ssErr == "" && !portListening),
		portDetail,
	)

	socatState := serviceState("socat", "socat")
	addCheck(
		"socat_status",
		"socat service / process status",
		true,
		"passed",
		fmt.Sprintf("binary_present=%v systemd_active=%v", socatState["binary_present"], socatState["systemd_active"]),
	)

	gostState := serviceState("gost", "gost")
	addCheck(
		"gost_status",
		"gost service / process status",
		true,
		"passed",
		fmt.Sprintf("binary_present=%v systemd_active=%v", gostState["binary_present"], gostState["systemd_active"]),
	)

	reachable, reachDetail := tcpReachability(request.LandingTargetHost, request.LandingTargetPort)
	addCheck(
		"transit_to_landing_tcp_connectivity",
		"Transit to landing TCP connectivity",
		reachable,
		statusFromPassed(reachable),
		reachDetail,
	)

	firewall, firewallWarnings := firewallReadonlySummary()
	firewallDetail := fmt.Sprintf(
		"ufw=%s firewalld=%s iptables_summary=%s warnings=%d",
		truncateReadonlyOutput(fmt.Sprint(firewall["ufw_status"]), 120),
		truncateReadonlyOutput(fmt.Sprint(firewall["firewalld_state"]), 120),
		truncateReadonlyOutput(fmt.Sprint(firewall["iptables_rules_summary"]), 220),
		len(firewallWarnings),
	)
	addCheck(
		"firewall_readonly_summary",
		"Local firewall readonly summary",
		true,
		"passed",
		firewallDetail,
	)

	passed := true
	for _, check := range checks {
		if checkPassed, ok := check["passed"].(bool); ok && !checkPassed {
			passed = false
			break
		}
	}
	status := "passed"
	summary := fmt.Sprintf("Remote readonly preflight passed for planned listen %d to landing target port %d.", request.PlannedListenPort, request.LandingTargetPort)
	if !passed {
		status = "blocked"
		summary = "Remote readonly preflight found blockers. No real forwarding was created."
	}

	return map[string]any{
		"passed":              passed,
		"status":              status,
		"summary":             summary,
		"checks":              checks,
		"worker_version":      workerVersion,
		"hostname":            hostname,
		"role":                cfg.Role,
		"interface_name":      cfg.InterfaceName,
		"planned_listen_port": request.PlannedListenPort,
		"landing_target_port": request.LandingTargetPort,
		"forwarding_method":   request.ForwardingMethod,
		"redacted_summary": fmt.Sprintf(
			"transit_readonly_preflight status=%s planned_listen_port=%d landing_target_port=%d method=%s",
			status,
			request.PlannedListenPort,
			request.LandingTargetPort,
			request.ForwardingMethod,
		),
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
	}, nil
}

func parseTransitReadonlyPreflightRequest(payload map[string]any) (transitReadonlyPreflightRequest, error) {
	request := transitReadonlyPreflightRequest{
		TransitResourceID: stringPayload(payload, "transit_resource_id"),
		LandingNodeID:     stringPayload(payload, "landing_node_id"),
		PlannedListenPort: intPayload(payload, "planned_listen_port"),
		LandingTargetHost: stringPayload(payload, "landing_target_host"),
		LandingTargetPort: intPayload(payload, "landing_target_port"),
		ForwardingMethod:  defaultStringPayload(payload, "forwarding_method", "socat"),
		Purpose:           stringPayload(payload, "purpose"),
		Readonly:          boolPayload(payload, "readonly"),
	}
	if !request.Readonly {
		return request, errors.New("transit_readonly_preflight requires readonly=true")
	}
	if request.TransitResourceID == "" || request.LandingNodeID == "" {
		return request, errors.New("transit_readonly_preflight missing resource or node id")
	}
	if !validTCPPort(request.PlannedListenPort) || !validTCPPort(request.LandingTargetPort) {
		return request, errors.New("transit_readonly_preflight ports must be 1-65535")
	}
	if reason, reserved := protectedTransitListenPorts[request.PlannedListenPort]; reserved {
		return request, fmt.Errorf("planned listen port is protected: %s", reason)
	}
	if request.ForwardingMethod != "socat" && request.ForwardingMethod != "gost" {
		return request, errors.New("transit_readonly_preflight forwarding_method must be socat or gost")
	}
	if !safeDialTargetHost(request.LandingTargetHost) {
		return request, errors.New("transit_readonly_preflight landing target host is invalid")
	}
	_ = request.Purpose
	return request, nil
}

type landingNodeCreateRequest struct {
	ServerID           string
	ServerIP           string
	WorkerID           string
	InterfaceName      string
	ListenPort         int
	Protocol           string
	Security           string
	Flow               string
	ServerName         string
	Dest               string
	Fingerprint        string
	NodeName           string
	ManagedConfigPath  string
	ManagedServiceName string
	ManagedServicePath string
}

type landingNodeCreateArtifacts struct {
	ConfigWritten    bool
	ServiceWritten   bool
	BinaryWritten    bool
	DaemonReloaded   bool
	ServiceStarted   bool
	BaseDirCreated   bool
	BinDirCreated    bool
	ConfigDirCreated bool
	StateDirCreated  bool
}

func executeLandingNodeCreate(cfg config, payload map[string]any) (map[string]any, error) {
	request, err := parseLandingNodeCreateRequest(cfg, payload)
	if err != nil {
		return nil, err
	}
	phases := []map[string]any{}
	artifacts := &landingNodeCreateArtifacts{}

	addPhase := func(name string, status string, summary string) {
		phases = append(phases, map[string]any{
			"name":    name,
			"status":  status,
			"summary": summary,
		})
	}

	if err := landingNodePreflightRecheck(request); err != nil {
		addPhase("preflight_recheck", "failed", err.Error())
		return landingNodeFailureResult(request, phases), err
	}
	addPhase("preflight_recheck", "passed", "27939/TCP 未监听，Xray / x-ui / 3x-ui 未安装，已有 Xray 配置未发现。")

	if err := installXrayBinary(artifacts); err != nil {
		addPhase("install_xray_core", "failed", err.Error())
		rollbackLandingNodeCreate(artifacts)
		return landingNodeFailureResult(request, phases), err
	}
	artifacts.BinaryWritten = true
	addPhase("install_xray_core", "passed", "Xray-core binary 已安装到 LiveLine 审批路径。")

	reality, err := generateRealityMaterial()
	if err != nil {
		addPhase("generate_reality_material", "failed", err.Error())
		rollbackLandingNodeCreate(artifacts)
		return landingNodeFailureResult(request, phases), err
	}
	addPhase("generate_reality_material", "passed", "VLESS UUID、Reality public key 和 shortId 已生成；private key 仅写入本机配置。")

	if err := writeManagedXrayConfig(request, reality, artifacts); err != nil {
		addPhase("write_xray_config", "failed", err.Error())
		rollbackLandingNodeCreate(artifacts)
		return landingNodeFailureResult(request, phases), err
	}
	artifacts.ConfigWritten = true
	addPhase("write_xray_config", "passed", "LiveLine 管理的 Xray 配置已写入。")

	if err := writeManagedXrayService(); err != nil {
		addPhase("write_systemd_service", "failed", err.Error())
		rollbackLandingNodeCreate(artifacts)
		return landingNodeFailureResult(request, phases), err
	}
	artifacts.ServiceWritten = true
	addPhase("write_systemd_service", "passed", "LiveLine 管理的 systemd service 已写入。")

	if _, err := runCommand(commandTimeout, managedXrayBinaryPath, "run", "-test", "-config", managedXrayConfigPath); err != nil {
		addPhase("xray_config_test", "failed", err.Error())
		rollbackLandingNodeCreate(artifacts)
		return landingNodeFailureResult(request, phases), err
	}
	addPhase("xray_config_test", "passed", "Xray 配置测试通过。")

	if _, err := runCommand(commandTimeout, "systemctl", "daemon-reload"); err != nil {
		addPhase("systemd_daemon_reload", "failed", err.Error())
		rollbackLandingNodeCreate(artifacts)
		return landingNodeFailureResult(request, phases), err
	}
	artifacts.DaemonReloaded = true
	if _, err := runCommand(commandTimeout, "systemctl", "enable", managedXrayServiceName); err != nil {
		addPhase("systemd_enable", "failed", err.Error())
		rollbackLandingNodeCreate(artifacts)
		return landingNodeFailureResult(request, phases), err
	}
	if _, err := runCommand(commandTimeout, "systemctl", "restart", managedXrayServiceName); err != nil {
		addPhase("systemd_restart", "failed", err.Error())
		rollbackLandingNodeCreate(artifacts)
		return landingNodeFailureResult(request, phases), err
	}
	artifacts.ServiceStarted = true
	addPhase("systemd_start", "passed", "LiveLine 管理的 Xray service 已 enable 并 restart。")

	if err := verifyManagedXrayActiveAndListening(request.ListenPort); err != nil {
		addPhase("verify_listening", "failed", err.Error())
		rollbackLandingNodeCreate(artifacts)
		return landingNodeFailureResult(request, phases), err
	}
	addPhase("verify_listening", "passed", "Xray service active，27939/TCP 已监听。")

	shareLink := buildVLESSRealityShareLink(request, reality)
	return map[string]any{
		"status":              "succeeded",
		"phases":              phases,
		"node_name":           request.NodeName,
		"listen_port":         request.ListenPort,
		"protocol":            request.Protocol,
		"security":            request.Security,
		"flow":                request.Flow,
		"server_name":         request.ServerName,
		"dest":                request.Dest,
		"fingerprint":         request.Fingerprint,
		"uuid":                reality.UUID,
		"reality_public_key":  reality.PublicKey,
		"reality_short_id":    reality.ShortID,
		"managed_config_path": managedXrayConfigPath,
		"managed_service":     managedXrayServiceName,
		"share_link_present":  true,
		"masked_share_link":   maskShareLink(shareLink),
		"secure_share_link":   shareLink,
		"safety_boundary": []any{
			"node.share_link is written only by backend after this success result",
			"Reality private key was not returned",
			"rollback scope is current run artifacts only",
		},
	}, nil
}

func parseLandingNodeCreateRequest(cfg config, payload map[string]any) (landingNodeCreateRequest, error) {
	request := landingNodeCreateRequest{
		ServerID:           stringPayload(payload, "server_id"),
		ServerIP:           stringPayload(payload, "server_ip"),
		WorkerID:           stringPayload(payload, "worker_id"),
		InterfaceName:      stringPayload(payload, "interface_name"),
		ListenPort:         intPayload(payload, "listen_port"),
		Protocol:           defaultStringPayload(payload, "protocol", "vless"),
		Security:           defaultStringPayload(payload, "security", "reality"),
		Flow:               defaultStringPayload(payload, "flow", "xtls-rprx-vision"),
		ServerName:         defaultStringPayload(payload, "server_name", "www.microsoft.com"),
		Dest:               defaultStringPayload(payload, "dest", "www.microsoft.com:443"),
		Fingerprint:        defaultStringPayload(payload, "fingerprint", "chrome"),
		NodeName:           defaultStringPayload(payload, "node_name", "liveline-reality-27939"),
		ManagedConfigPath:  defaultStringPayload(payload, "managed_config_path", managedXrayConfigPath),
		ManagedServiceName: defaultStringPayload(payload, "managed_service_name", managedXrayServiceName),
		ManagedServicePath: defaultStringPayload(payload, "managed_service_path", managedXrayServicePath),
	}
	if request.WorkerID != cfg.WorkerID {
		return request, errors.New("landing_node_create worker_id does not match local worker")
	}
	if request.InterfaceName != cfg.InterfaceName {
		return request, errors.New("landing_node_create interface does not match local worker config")
	}
	if request.ListenPort != formalLandingPort {
		return request, fmt.Errorf("landing_node_create approved port must be %d", formalLandingPort)
	}
	if request.Protocol != "vless" || request.Security != "reality" || request.Flow == "" || request.ServerName == "" || request.Dest == "" {
		return request, errors.New("landing_node_create payload contains unsupported protocol or Reality fields")
	}
	if net.ParseIP(request.ServerIP) == nil {
		return request, errors.New("landing_node_create server_ip is invalid")
	}
	if request.ManagedConfigPath != managedXrayConfigPath || request.ManagedServicePath != managedXrayServicePath || request.ManagedServiceName != managedXrayServiceName {
		return request, errors.New("landing_node_create managed paths do not match LiveLine safety boundary")
	}
	return request, nil
}

func stringPayload(payload map[string]any, key string) string {
	value, _ := payload[key].(string)
	return strings.TrimSpace(value)
}

func defaultStringPayload(payload map[string]any, key string, fallback string) string {
	value := stringPayload(payload, key)
	if value == "" {
		return fallback
	}
	return value
}

func intPayload(payload map[string]any, key string) int {
	switch value := payload[key].(type) {
	case int:
		return value
	case float64:
		return int(value)
	case string:
		parsed, _ := strconv.Atoi(value)
		return parsed
	default:
		return 0
	}
}

func boolPayload(payload map[string]any, key string) bool {
	value, _ := payload[key].(bool)
	return value
}

func validTCPPort(port int) bool {
	return port >= 1 && port <= 65535
}

func statusFromPassed(passed bool) string {
	if passed {
		return "passed"
	}
	return "blocked"
}

func safeDialTargetHost(host string) bool {
	cleaned := strings.TrimSpace(host)
	if cleaned == "" || len(cleaned) > 255 {
		return false
	}
	if strings.ContainsAny(cleaned, " \t\r\n/\\\"'`$;&|<>") {
		return false
	}
	if ip := net.ParseIP(cleaned); ip != nil {
		return true
	}
	for _, label := range strings.Split(cleaned, ".") {
		if label == "" || len(label) > 63 {
			return false
		}
		for _, char := range label {
			if (char >= 'a' && char <= 'z') || (char >= 'A' && char <= 'Z') || (char >= '0' && char <= '9') || char == '-' {
				continue
			}
			return false
		}
	}
	return true
}

func tcpReachability(host string, port int) (bool, string) {
	address := net.JoinHostPort(host, strconv.Itoa(port))
	conn, err := net.DialTimeout("tcp", address, readonlyCommandTimeout)
	if err != nil {
		return false, fmt.Sprintf("TCP connect to target port %d failed: %v", port, err)
	}
	_ = conn.Close()
	return true, fmt.Sprintf("TCP connect to target port %d succeeded.", port)
}

func landingNodePreflightRecheck(request landingNodeCreateRequest) error {
	if os.Geteuid() != 0 {
		return errors.New("landing_node_create must run as root because Xray and systemd files are managed")
	}
	if portListening(request.ListenPort) {
		return fmt.Errorf("approved TCP port %d is already listening", request.ListenPort)
	}
	for _, path := range []string{
		managedXrayBinaryPath,
		"/usr/bin/xray",
		managedXrayConfigPath,
		managedXrayStateDir,
		"/usr/local/bin/xray",
		"/usr/local/etc/liveline-xray/config.json",
		"/usr/local/etc/liveline-xray",
		"/usr/local/etc/xray/config.json",
		"/etc/xray/config.json",
		managedXrayServicePath,
		"/etc/systemd/system/xray.service",
		"/etc/systemd/system/x-ui.service",
		"/etc/systemd/system/3x-ui.service",
	} {
		if _, err := os.Stat(path); err == nil {
			return fmt.Errorf("preflight refused because %s already exists", path)
		} else if !errors.Is(err, os.ErrNotExist) {
			return fmt.Errorf("preflight cannot inspect %s: %w", path, err)
		}
	}
	if err := validateManagedXrayBaseDirForPreflight(managedXrayBaseDir); err != nil {
		return err
	}
	for _, binary := range []string{"xray", "x-ui", "3x-ui"} {
		if path, err := exec.LookPath(binary); err == nil && path != "" {
			return fmt.Errorf("preflight refused because %s is already installed at %s", binary, path)
		}
	}
	if _, err := exec.LookPath("systemctl"); err != nil {
		return errors.New("systemctl is required")
	}
	return nil
}

func validateManagedXrayBaseDirForPreflight(baseDir string) error {
	info, err := os.Lstat(baseDir)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("preflight cannot inspect %s: %w", baseDir, err)
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("preflight refused because %s is a symlink", baseDir)
	}
	if !info.IsDir() {
		return fmt.Errorf("preflight refused because %s exists but is not a directory", baseDir)
	}
	entries, err := os.ReadDir(baseDir)
	if err != nil {
		return fmt.Errorf("preflight cannot inspect %s: %w", baseDir, err)
	}
	for _, entry := range entries {
		childPath := filepath.Join(baseDir, entry.Name())
		if entry.Type()&os.ModeSymlink != 0 {
			return fmt.Errorf("preflight refused because %s contains unsupported artifact %s", baseDir, childPath)
		}
		if entry.Name() != "bin" && entry.Name() != "config" {
			return fmt.Errorf("preflight refused because %s contains unknown artifact %s", baseDir, childPath)
		}
		childInfo, err := entry.Info()
		if err != nil {
			return fmt.Errorf("preflight cannot inspect %s: %w", childPath, err)
		}
		if !childInfo.IsDir() {
			return fmt.Errorf("preflight refused because %s contains non-directory artifact %s", baseDir, childPath)
		}
		childEntries, err := os.ReadDir(childPath)
		if err != nil {
			return fmt.Errorf("preflight cannot inspect %s: %w", childPath, err)
		}
		if len(childEntries) > 0 {
			return fmt.Errorf("preflight refused because %s is not empty", childPath)
		}
	}
	return nil
}

func installXrayBinary(artifacts *landingNodeCreateArtifacts) error {
	tmpDir, err := os.MkdirTemp("", "liveline-xray-*")
	if err != nil {
		return err
	}
	defer os.RemoveAll(tmpDir)

	zipPath := filepath.Join(tmpDir, "xray.zip")
	if err := downloadFile(xrayDownloadURL, zipPath); err != nil {
		return err
	}
	xrayPath := filepath.Join(tmpDir, "xray")
	if err := extractZipFile(zipPath, "xray", xrayPath); err != nil {
		return err
	}
	if err := os.Chmod(xrayPath, 0o755); err != nil {
		return err
	}
	if err := ensureManagedXrayDirs(artifacts); err != nil {
		return err
	}
	return copyFile(xrayPath, managedXrayBinaryPath, 0o755)
}

func ensureManagedXrayDirs(artifacts *landingNodeCreateArtifacts) error {
	created, err := ensureDir(managedXrayBaseDir, 0o755)
	if err != nil {
		return err
	}
	artifacts.BaseDirCreated = artifacts.BaseDirCreated || created
	created, err = ensureDir(managedXrayBinDir, 0o755)
	if err != nil {
		return err
	}
	artifacts.BinDirCreated = artifacts.BinDirCreated || created
	created, err = ensureDir(managedXrayConfigDir, 0o700)
	if err != nil {
		return err
	}
	artifacts.ConfigDirCreated = artifacts.ConfigDirCreated || created
	created, err = ensureDir(managedXrayStateDir, 0o700)
	if err != nil {
		return err
	}
	artifacts.StateDirCreated = artifacts.StateDirCreated || created
	return nil
}

func ensureDir(path string, mode os.FileMode) (bool, error) {
	info, err := os.Stat(path)
	if err == nil {
		if !info.IsDir() {
			return false, fmt.Errorf("%s exists but is not a directory", path)
		}
		return false, nil
	}
	if !errors.Is(err, os.ErrNotExist) {
		return false, err
	}
	if err := os.Mkdir(path, mode); err != nil {
		return false, err
	}
	return true, nil
}

func downloadFile(rawURL string, destination string) error {
	client := &http.Client{Timeout: 120 * time.Second}
	response, err := client.Get(rawURL)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return fmt.Errorf("download failed status=%d", response.StatusCode)
	}
	file, err := os.OpenFile(destination, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	defer file.Close()
	written, err := io.Copy(file, io.LimitReader(response.Body, 200<<20))
	if err != nil {
		return err
	}
	if written <= 0 {
		return errors.New("downloaded Xray archive is empty")
	}
	return nil
}

func extractZipFile(zipPath string, wantedName string, destination string) error {
	reader, err := zip.OpenReader(zipPath)
	if err != nil {
		return err
	}
	defer reader.Close()
	for _, item := range reader.File {
		if filepath.Base(item.Name) != wantedName {
			continue
		}
		source, err := item.Open()
		if err != nil {
			return err
		}
		defer source.Close()
		target, err := os.OpenFile(destination, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o700)
		if err != nil {
			return err
		}
		if _, err := io.Copy(target, source); err != nil {
			target.Close()
			return err
		}
		return target.Close()
	}
	return fmt.Errorf("xray binary %q not found in archive", wantedName)
}

func copyFile(source string, destination string, mode os.FileMode) error {
	input, err := os.Open(source)
	if err != nil {
		return err
	}
	defer input.Close()
	output, err := os.OpenFile(destination, os.O_CREATE|os.O_EXCL|os.O_WRONLY, mode)
	if err != nil {
		return err
	}
	if _, err := io.Copy(output, input); err != nil {
		output.Close()
		return err
	}
	if err := output.Close(); err != nil {
		return err
	}
	return os.Chmod(destination, mode)
}

type realityMaterial struct {
	UUID       string
	PrivateKey string
	PublicKey  string
	ShortID    string
}

func generateRealityMaterial() (realityMaterial, error) {
	output, err := runCommand(commandTimeout, managedXrayBinaryPath, "x25519")
	if err != nil {
		return realityMaterial{}, err
	}
	privateKey, publicKey := parseX25519Keys(output)
	if privateKey == "" || publicKey == "" {
		return realityMaterial{}, errors.New("xray x25519 output did not include expected key pair")
	}
	uuidValue, err := randomUUID()
	if err != nil {
		return realityMaterial{}, err
	}
	shortID, err := randomHex(8)
	if err != nil {
		return realityMaterial{}, err
	}
	return realityMaterial{
		UUID:       uuidValue,
		PrivateKey: privateKey,
		PublicKey:  publicKey,
		ShortID:    shortID,
	}, nil
}

func parseX25519Keys(output string) (string, string) {
	privateKey := ""
	publicKey := ""
	for _, line := range strings.Split(output, "\n") {
		cleaned := strings.TrimSpace(line)
		lowered := strings.ToLower(cleaned)
		if strings.HasPrefix(lowered, "private key:") {
			privateKey = strings.TrimSpace(cleaned[len("Private key:"):])
		}
		if strings.HasPrefix(lowered, "public key:") {
			publicKey = strings.TrimSpace(cleaned[len("Public key:"):])
		}
	}
	return privateKey, publicKey
}

func randomUUID() (string, error) {
	buffer := make([]byte, 16)
	if _, err := rand.Read(buffer); err != nil {
		return "", err
	}
	buffer[6] = (buffer[6] & 0x0f) | 0x40
	buffer[8] = (buffer[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", buffer[0:4], buffer[4:6], buffer[6:8], buffer[8:10], buffer[10:16]), nil
}

func randomHex(byteCount int) (string, error) {
	buffer := make([]byte, byteCount)
	if _, err := rand.Read(buffer); err != nil {
		return "", err
	}
	return hex.EncodeToString(buffer), nil
}

func writeManagedXrayConfig(request landingNodeCreateRequest, reality realityMaterial, artifacts *landingNodeCreateArtifacts) error {
	config := map[string]any{
		"log": map[string]any{"loglevel": "warning"},
		"inbounds": []any{
			map[string]any{
				"listen":   "0.0.0.0",
				"port":     request.ListenPort,
				"protocol": "vless",
				"settings": map[string]any{
					"clients": []any{
						map[string]any{
							"id":   reality.UUID,
							"flow": request.Flow,
						},
					},
					"decryption": "none",
				},
				"streamSettings": map[string]any{
					"network":  "tcp",
					"security": "reality",
					"realitySettings": map[string]any{
						"show":        false,
						"dest":        request.Dest,
						"xver":        0,
						"serverNames": []any{request.ServerName},
						"privateKey":  reality.PrivateKey,
						"shortIds":    []any{reality.ShortID},
					},
				},
			},
		},
		"outbounds": []any{
			map[string]any{
				"protocol": "freedom",
				"tag":      "direct",
			},
		},
	}
	content, err := json.MarshalIndent(config, "", "  ")
	if err != nil {
		return err
	}
	if err := ensureManagedXrayDirs(artifacts); err != nil {
		return err
	}
	return os.WriteFile(managedXrayConfigPath, append(content, '\n'), 0o600)
}

func writeManagedXrayService() error {
	content := `[Unit]
Description=LiveLine managed Xray Reality node
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/opt/liveline-xray/bin/xray run -config /opt/liveline-xray/config/config.json
Restart=on-failure
RestartSec=5
User=root
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
`
	return os.WriteFile(managedXrayServicePath, []byte(content), 0o644)
}

func verifyManagedXrayActiveAndListening(port int) error {
	output, err := runCommand(commandTimeout, "systemctl", "is-active", managedXrayServiceName)
	if err != nil {
		return err
	}
	if strings.TrimSpace(output) != "active" {
		return fmt.Errorf("%s is not active", managedXrayServiceName)
	}
	if !portListening(port) {
		return fmt.Errorf("approved TCP port %d is not listening after Xray start", port)
	}
	return nil
}

func portListening(port int) bool {
	output, _ := readonlyCommandOutput("ss", "-lntup")
	rows, _ := listeningPortRows(output)
	for _, row := range rows {
		if value, ok := row["port"].(int); ok && value == port {
			return true
		}
	}
	return false
}

func buildVLESSRealityShareLink(request landingNodeCreateRequest, reality realityMaterial) string {
	values := url.Values{}
	values.Set("encryption", "none")
	values.Set("flow", request.Flow)
	values.Set("security", "reality")
	values.Set("sni", request.ServerName)
	values.Set("fp", request.Fingerprint)
	values.Set("pbk", reality.PublicKey)
	values.Set("sid", reality.ShortID)
	values.Set("type", "tcp")
	fragment := url.QueryEscape(request.NodeName)
	return fmt.Sprintf(
		"vless://%s@%s:%d?%s#%s",
		reality.UUID,
		request.ServerIP,
		request.ListenPort,
		values.Encode(),
		fragment,
	)
}

func maskShareLink(shareLink string) string {
	if len(shareLink) <= 40 {
		return "[redacted-link]"
	}
	return shareLink[:18] + "..." + shareLink[len(shareLink)-10:]
}

func landingNodeFailureResult(request landingNodeCreateRequest, phases []map[string]any) map[string]any {
	return map[string]any{
		"status":      "failed",
		"node_name":   request.NodeName,
		"listen_port": request.ListenPort,
		"phases":      phases,
		"rollback":    "attempted_current_run_artifacts_only",
	}
}

func rollbackLandingNodeCreate(artifacts *landingNodeCreateArtifacts) {
	if artifacts == nil {
		return
	}
	if artifacts.ServiceStarted {
		_, _ = runCommand(30*time.Second, "systemctl", "stop", managedXrayServiceName)
	}
	if artifacts.ServiceWritten {
		_, _ = runCommand(30*time.Second, "systemctl", "disable", managedXrayServiceName)
		_ = os.Remove(managedXrayServicePath)
	}
	if artifacts.ConfigWritten {
		_ = os.Remove(managedXrayConfigPath)
	}
	if artifacts.BinaryWritten {
		_ = os.Remove(managedXrayBinaryPath)
	}
	if artifacts.StateDirCreated {
		_ = os.Remove(managedXrayStateDir)
	}
	if artifacts.ConfigDirCreated {
		_ = os.Remove(managedXrayConfigDir)
	}
	if artifacts.BinDirCreated {
		_ = os.Remove(managedXrayBinDir)
	}
	if artifacts.BaseDirCreated {
		_ = os.Remove(managedXrayBaseDir)
	}
	if artifacts.DaemonReloaded || artifacts.ServiceWritten {
		_, _ = runCommand(30*time.Second, "systemctl", "daemon-reload")
	}
}

func runCommand(timeout time.Duration, name string, args ...string) (string, error) {
	if _, err := exec.LookPath(name); err != nil && strings.Contains(name, "/") {
		if _, statErr := os.Stat(name); statErr != nil {
			return "", fmt.Errorf("%s not found", name)
		}
	} else if err != nil {
		return "", fmt.Errorf("%s not found", name)
	}
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, name, args...)
	output, err := cmd.CombinedOutput()
	trimmed := truncateReadonlyOutput(strings.TrimSpace(string(output)), commandOutputLimit)
	if ctx.Err() == context.DeadlineExceeded {
		return trimmed, fmt.Errorf("%s timed out", name)
	}
	if err != nil {
		if trimmed != "" {
			return trimmed, fmt.Errorf("%s failed: %s", name, trimmed)
		}
		return "", fmt.Errorf("%s failed: %w", name, err)
	}
	return trimmed, nil
}

func postWorkerCommandResult(cfg config, command workerCommand, result map[string]any) error {
	headers := map[string]string{
		"X-Worker-Id":     cfg.WorkerID,
		"X-Worker-Secret": cfg.WorkerSecret,
	}
	var response apiResponse[map[string]any]
	sanitized := sanitizeCommandResult(command.CommandType, result)
	submitResult, compactInfo := prepareCommandResultForSubmit(command.CommandType, sanitized)
	payload := commandResultPayload{Result: submitResult}
	summary := buildResultSubmitDebugSummary(command.CommandType, result)
	fallbackWouldBeTriggered := payloadSize(payload) > resultPayloadSoftLimit
	if fallbackWouldBeTriggered {
		payload.Result = fallbackCommandResult(command, fmt.Errorf("sanitized result payload exceeded %d bytes", resultPayloadSoftLimit))
	}
	endpointURL := joinURL(cfg.ConsoleURL, "/api/workers/commands/"+command.ID+"/result")
	if compactInfo.CompactApplied {
		traceTransitReadonlyCompactResult(command, endpointURL, compactInfo)
	}
	traceWorkerCommandResultSubmit(command, endpointURL, headers, summary, payloadSize(payload), fallbackWouldBeTriggered)
	if err := postJSONWithCurlFallback(endpointURL, headers, payload, &response); err != nil {
		return err
	}
	if !response.Success {
		return fmt.Errorf("command result rejected: %s", response.Message)
	}
	return nil
}

func postWorkerCommandFailure(cfg config, commandID string, commandErr error, result map[string]any) error {
	headers := map[string]string{
		"X-Worker-Id":     cfg.WorkerID,
		"X-Worker-Secret": cfg.WorkerSecret,
	}
	var response apiResponse[map[string]any]
	commandType := commandTypeFromFailureResult(result)
	submitResult := prepareFailureResultForSubmit(commandType, result, commandErr)
	payload := commandFailurePayload{
		ErrorMessage: compactWorkerFailureMessage(commandErr),
		Result:       submitResult,
	}
	if payloadSize(payload) > workerFailurePayloadTarget {
		payload.ErrorMessage = truncateCompactString(compactWorkerFailureMessage(commandErr), 160)
		payload.Result = minimalFailureCommandResult(commandType, commandErr)
	}
	endpointURL := joinURL(cfg.ConsoleURL, "/api/workers/commands/"+commandID+"/fail")
	traceWorkerCommandFailureSubmit(commandID, endpointURL, headers, payload)
	if err := postJSONWithCurlFallback(endpointURL, headers, payload, &response); err != nil {
		return err
	}
	if !response.Success {
		return fmt.Errorf("command failure rejected: %s", response.Message)
	}
	return nil
}

func sanitizeCommandResult(commandType string, result map[string]any) map[string]any {
	if commandType == "transit_readonly_preflight" {
		return sanitizeTransitReadonlyPreflightResult(result)
	}
	return sanitizeResultMap(result)
}

func sanitizeTransitReadonlyPreflightResult(result map[string]any) map[string]any {
	if result == nil {
		return map[string]any{}
	}
	checks := []any{}
	if rawChecks, ok := result["checks"].([]map[string]any); ok {
		for _, check := range rawChecks {
			checks = append(checks, sanitizeTransitReadonlyPreflightCheck(check))
			if len(checks) >= resultListLimit {
				break
			}
		}
	} else if rawChecks, ok := result["checks"].([]any); ok {
		for _, item := range rawChecks {
			if check, ok := item.(map[string]any); ok {
				checks = append(checks, sanitizeTransitReadonlyPreflightCheck(check))
			}
			if len(checks) >= resultListLimit {
				break
			}
		}
	}
	sanitized := map[string]any{
		"passed":              boolResultValue(result["passed"]),
		"status":              stringResultValue(result["status"]),
		"summary":             stringResultValue(result["summary"]),
		"checks":              checks,
		"worker_version":      workerVersion,
		"hostname":            stringResultValue(result["hostname"]),
		"role":                stringResultValue(result["role"]),
		"interface_name":      stringResultValue(result["interface_name"]),
		"planned_listen_port": intResultValue(result["planned_listen_port"]),
		"landing_target_port": intResultValue(result["landing_target_port"]),
		"forwarding_method":   stringResultValue(result["forwarding_method"]),
		"redacted_summary":    stringResultValue(result["redacted_summary"]),
		"safety_boundary":     sanitizeResultValue(result["safety_boundary"]),
	}
	if sanitized["status"] == "" {
		if passed, _ := sanitized["passed"].(bool); passed {
			sanitized["status"] = "passed"
		} else {
			sanitized["status"] = "blocked"
		}
	}
	if sanitized["summary"] == "" {
		sanitized["summary"] = "Transit readonly preflight returned a sanitized result."
	}
	if sanitized["redacted_summary"] == "" {
		sanitized["redacted_summary"] = fmt.Sprintf(
			"transit_readonly_preflight status=%s planned_listen_port=%v landing_target_port=%v method=%s",
			sanitized["status"],
			sanitized["planned_listen_port"],
			sanitized["landing_target_port"],
			sanitized["forwarding_method"],
		)
	}
	return sanitized
}

func prepareCommandResultForSubmit(commandType string, sanitized map[string]any) (map[string]any, compactResultInfo) {
	originalSize := payloadSize(commandResultPayload{Result: sanitized})
	info := compactResultInfo{
		OriginalSubmitPayloadSize: originalSize,
		CompactSubmitPayloadSize:  originalSize,
		CompactApplied:            false,
		ChecksCount:               checksCount(sanitized["checks"]),
		MaxDetailLength:           maxCheckDetailLength(sanitized["checks"]),
	}
	switch commandType {
	case "transit_readonly_preflight":
		compacted := compactTransitReadonlyPreflightResult(sanitized, true)
		compactSize := payloadSize(commandResultPayload{Result: compacted})
		if compactSize > transitReadonlyCompactPayloadTarget {
			compacted = compactTransitReadonlyPreflightResult(sanitized, false)
			info.DetailsRemoved = true
			compactSize = payloadSize(commandResultPayload{Result: compacted})
		}
		info.CompactSubmitPayloadSize = compactSize
		info.CompactApplied = true
		info.ChecksCount = intResultValue(compacted["checks_count"])
		info.MaxDetailLength = maxCheckDetailLength(compacted["checks"])
		return compacted, info
	case "transit_route_create":
		compacted := compactTransitRouteCreateResult(sanitized, true)
		compactSize := payloadSize(commandResultPayload{Result: compacted})
		if compactSize > transitRouteCreateCompactPayloadTarget {
			compacted = compactTransitRouteCreateResult(sanitized, false)
			info.DetailsRemoved = true
			compactSize = payloadSize(commandResultPayload{Result: compacted})
		}
		if compactSize > transitRouteCreateCompactPayloadTarget {
			compacted = compactTransitRouteCreateResultMinimal(sanitized)
			info.DetailsRemoved = true
			compactSize = payloadSize(commandResultPayload{Result: compacted})
		}
		info.CompactSubmitPayloadSize = compactSize
		info.CompactApplied = true
		info.ChecksCount = intResultValue(compacted["checks_count"])
		info.MaxDetailLength = maxCheckDetailLength(compacted["checks"])
		return compacted, info
	default:
		return sanitized, info
	}
}

func compactTransitReadonlyPreflightResult(result map[string]any, includeDetails bool) map[string]any {
	checksCountValue := checksCount(result["checks"])
	compacted := map[string]any{
		"passed":              boolResultValue(result["passed"]),
		"status":              truncateCompactString(stringResultValue(result["status"]), 48),
		"summary":             truncateCompactString(stringResultValue(result["summary"]), transitReadonlyCompactSummaryLimit),
		"worker_version":      workerVersion,
		"hostname":            truncateCompactString(stringResultValue(result["hostname"]), 80),
		"role":                truncateCompactString(stringResultValue(result["role"]), 32),
		"interface_name":      truncateCompactString(stringResultValue(result["interface_name"]), 32),
		"planned_listen_port": intResultValue(result["planned_listen_port"]),
		"landing_target_port": intResultValue(result["landing_target_port"]),
		"forwarding_method":   truncateCompactString(stringResultValue(result["forwarding_method"]), 16),
		"checks_count":        checksCountValue,
		"redacted_summary":    truncateCompactString(stringResultValue(result["redacted_summary"]), transitReadonlyCompactSummaryLimit),
		"safety_boundary": []any{
			"readonly_only",
			"no_listener_binding",
			"no_firewall_mutation",
			"no_xray_mutation",
			"no_cutover",
		},
	}
	if compacted["status"] == "" {
		if boolResultValue(compacted["passed"]) {
			compacted["status"] = "passed"
		} else {
			compacted["status"] = "blocked"
		}
	}
	if compacted["summary"] == "" {
		compacted["summary"] = "Transit readonly preflight compact result."
	}
	if compacted["redacted_summary"] == "" {
		compacted["redacted_summary"] = fmt.Sprintf(
			"transit_readonly_preflight status=%s planned_listen_port=%v landing_target_port=%v method=%s",
			compacted["status"],
			compacted["planned_listen_port"],
			compacted["landing_target_port"],
			compacted["forwarding_method"],
		)
	}
	if includeDetails {
		compacted["checks"] = compactTransitReadonlyChecks(result["checks"], true)
	} else {
		compacted["failed_check_names"] = failedTransitReadonlyCheckNames(result["checks"])
	}
	return compacted
}

func compactTransitReadonlyChecks(value any, includeDetails bool) []any {
	checks := []any{}
	appendCheck := func(check map[string]any) {
		name := compactCheckName(check)
		compacted := map[string]any{
			"name":   truncateCompactString(name, 80),
			"passed": boolResultValue(check["passed"]),
		}
		if includeDetails {
			detail := truncateCompactString(stringResultValue(check["detail"]), transitReadonlyCompactCheckDetailLimit)
			if detail != "" {
				compacted["detail"] = detail
			}
		}
		checks = append(checks, compacted)
	}
	switch typed := value.(type) {
	case []map[string]any:
		for _, check := range typed {
			appendCheck(check)
		}
	case []any:
		for _, item := range typed {
			if check, ok := item.(map[string]any); ok {
				appendCheck(check)
			}
		}
	}
	return checks
}

func failedTransitReadonlyCheckNames(value any) []any {
	names := []any{}
	appendFailed := func(check map[string]any) {
		if boolResultValue(check["passed"]) {
			return
		}
		name := compactCheckName(check)
		if name != "" {
			names = append(names, truncateCompactString(name, 80))
		}
	}
	switch typed := value.(type) {
	case []map[string]any:
		for _, check := range typed {
			appendFailed(check)
		}
	case []any:
		for _, item := range typed {
			if check, ok := item.(map[string]any); ok {
				appendFailed(check)
			}
		}
	}
	return names
}

func compactTransitRouteCreateResult(result map[string]any, includeDetails bool) map[string]any {
	compacted := compactTransitRouteCreateResultBase(result)
	if includeDetails {
		compacted["checks"] = compactTransitRouteCreateChecks(result["checks"], true)
	} else {
		compacted["failed_check_names"] = failedTransitReadonlyCheckNames(result["checks"])
	}
	return compacted
}

func compactTransitRouteCreateResultMinimal(result map[string]any) map[string]any {
	compacted := compactTransitRouteCreateResultBase(result)
	compacted["failed_check_names"] = failedTransitReadonlyCheckNames(result["checks"])
	return compacted
}

func compactTransitRouteCreateResultBase(result map[string]any) map[string]any {
	summary := truncateCompactString(stringResultValue(result["summary"]), transitRouteCreateCompactSummaryLimit)
	if summary == "" {
		summary = "Transit route create dry-run returned a compact result."
	}
	status := truncateCompactString(stringResultValue(result["status"]), 48)
	if status == "" {
		status = "approval_required"
	}
	executionMode := truncateCompactString(stringResultValue(result["execution_mode"]), 32)
	if executionMode == "" {
		executionMode = "dry_run"
	}
	compacted := map[string]any{
		"execution_mode":        executionMode,
		"real_execution":        boolResultValue(result["real_execution"]),
		"status":                status,
		"summary":               summary,
		"worker_version":        workerVersion,
		"hostname":              truncateCompactString(stringResultValue(result["hostname"]), 80),
		"role":                  truncateCompactString(stringResultValue(result["role"]), 32),
		"interface_name":        truncateCompactString(stringResultValue(result["interface_name"]), 32),
		"planned_listen_port":   intResultValue(result["planned_listen_port"]),
		"landing_target_host":   truncateCompactString(stringResultValue(result["landing_target_host"]), 80),
		"landing_target_port":   intResultValue(result["landing_target_port"]),
		"forwarding_method":     truncateCompactString(stringResultValue(result["forwarding_method"]), 16),
		"route_name":            truncateCompactString(stringResultValue(result["route_name"]), 120),
		"planned_service_name":  truncateCompactString(plannedServiceField(result["planned_service"], "name"), 120),
		"checks_count":          checksCount(result["checks"]),
		"planned_actions_count": listCount(result["planned_actions"]),
		"safety_boundary": []any{
			"dry_run_only",
			"no_listener_binding",
			"no_service_created",
			"no_firewall_mutation",
			"no_cutover",
		},
	}
	return compacted
}

func compactTransitRouteCreateChecks(value any, includeDetails bool) []any {
	checks := []any{}
	appendCheck := func(check map[string]any) {
		compacted := map[string]any{
			"name":   truncateCompactString(compactCheckName(check), 80),
			"passed": boolResultValue(check["passed"]),
		}
		if includeDetails {
			detail := truncateCompactString(stringResultValue(check["detail"]), transitRouteCreateCompactCheckDetailLimit)
			if detail != "" {
				compacted["detail"] = detail
			}
		}
		checks = append(checks, compacted)
	}
	switch typed := value.(type) {
	case []map[string]any:
		for _, check := range typed {
			appendCheck(check)
		}
	case []any:
		for _, item := range typed {
			if check, ok := item.(map[string]any); ok {
				appendCheck(check)
			}
		}
	}
	return checks
}

func compactCheckName(check map[string]any) string {
	for _, key := range []string{"label", "name", "id"} {
		if value := stringResultValue(check[key]); value != "" {
			return value
		}
	}
	return "check"
}

func plannedServiceField(value any, key string) string {
	service, ok := value.(map[string]any)
	if !ok {
		return ""
	}
	return stringResultValue(service[key])
}

func listCount(value any) int {
	switch typed := value.(type) {
	case []any:
		return len(typed)
	case []map[string]any:
		return len(typed)
	case []string:
		return len(typed)
	default:
		return 0
	}
}

func sanitizeTransitReadonlyPreflightCheck(check map[string]any) map[string]any {
	if check == nil {
		return map[string]any{}
	}
	return map[string]any{
		"id":                        stringResultValue(check["id"]),
		"label":                     stringResultValue(check["label"]),
		"status":                    stringResultValue(check["status"]),
		"passed":                    boolResultValue(check["passed"]),
		"detail":                    stringResultValue(check["detail"]),
		"category":                  stringResultValue(check["category"]),
		"evidence_summary":          stringResultValue(check["evidence_summary"]),
		"next_action":               stringResultValue(check["next_action"]),
		"sensitive_output_redacted": true,
	}
}

func fallbackCommandResult(command workerCommand, submitErr error) map[string]any {
	return map[string]any{
		"command_id":     command.ID,
		"command_type":   command.CommandType,
		"status":         "failed",
		"summary":        "Worker could not submit the full command result; a compact failure result was submitted instead.",
		"redacted_error": compactWorkerFailureMessage(submitErr),
		"worker_version": workerVersion,
		"safety_boundary": []any{
			"no arbitrary shell accepted",
			"no listener binding",
			"no firewall mutation",
			"no nodes.share_link read or modification",
			"no cutover",
		},
	}
}

func commandTypeFromFailureResult(result map[string]any) string {
	if result == nil {
		return ""
	}
	return stringResultValue(result["command_type"])
}

func prepareFailureResultForSubmit(commandType string, result map[string]any, commandErr error) map[string]any {
	if result == nil {
		return nil
	}
	sanitized := sanitizeCommandResult(commandType, result)
	if commandType == "" {
		return sanitized
	}
	submitResult, _ := prepareCommandResultForSubmit(commandType, sanitized)
	if payloadSize(commandFailurePayload{ErrorMessage: compactWorkerFailureMessage(commandErr), Result: submitResult}) > workerFailurePayloadTarget {
		return minimalFailureCommandResult(commandType, commandErr)
	}
	return submitResult
}

func minimalFailureCommandResult(commandType string, commandErr error) map[string]any {
	result := map[string]any{
		"status":          "failed",
		"summary":         "Worker command failed; compact failure report recorded.",
		"redacted_error":  compactWorkerFailureMessage(commandErr),
		"worker_version":  workerVersion,
		"safety_boundary": []any{"no_listener_binding", "no_firewall_mutation", "no_nodes_share_link", "no_cutover"},
	}
	if commandType != "" {
		result["command_type"] = commandType
	}
	return result
}

func compactWorkerFailureMessage(commandErr error) string {
	if commandErr == nil {
		return "Worker reported command failure."
	}
	message := sanitizeResultValue(commandErr.Error())
	text, ok := message.(string)
	if !ok || text == "" {
		text = "Worker reported command failure."
	}
	return truncateCompactString(text, workerFailureErrorMessageLimit)
}

func sanitizeResultMap(result map[string]any) map[string]any {
	if result == nil {
		return nil
	}
	sanitized, ok := sanitizeResultValue(result).(map[string]any)
	if !ok {
		return map[string]any{"summary": "result redacted"}
	}
	return sanitized
}

func sanitizeResultValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		result := map[string]any{}
		count := 0
		for key, item := range typed {
			if count >= resultListLimit {
				result["truncated_keys"] = true
				break
			}
			if sensitiveResultKey(key) {
				result[key] = "[redacted]"
			} else {
				result[key] = sanitizeResultValue(item)
			}
			count++
		}
		return result
	case []any:
		result := []any{}
		for index, item := range typed {
			if index >= resultListLimit {
				result = append(result, "...[truncated]")
				break
			}
			result = append(result, sanitizeResultValue(item))
		}
		return result
	case []map[string]any:
		result := []any{}
		for index, item := range typed {
			if index >= resultListLimit {
				result = append(result, "...[truncated]")
				break
			}
			result = append(result, sanitizeResultMap(item))
		}
		return result
	case string:
		return stringResultValue(typed)
	case fmt.Stringer:
		return stringResultValue(typed.String())
	default:
		return typed
	}
}

func sensitiveResultKey(key string) bool {
	lowered := strings.ToLower(key)
	for _, marker := range []string{"secret", "token", "password", "passwd", "passphrase", "private_key", "ssh_key", "session", "cookie", "share_link"} {
		if strings.Contains(lowered, marker) {
			return true
		}
	}
	return false
}

func stringResultValue(value any) string {
	if value == nil {
		return ""
	}
	text := fmt.Sprint(value)
	text = strings.ReplaceAll(text, "\x00", "")
	lowered := strings.ToLower(text)
	for _, marker := range []string{"vless://", "vmess://", "trojan://", "ss://"} {
		if strings.Contains(lowered, marker) {
			return "[redacted-link]"
		}
	}
	return truncateResultString(text, resultStringLimit)
}

func boolResultValue(value any) bool {
	if typed, ok := value.(bool); ok {
		return typed
	}
	return false
}

func intResultValue(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	case string:
		parsed, err := strconv.Atoi(strings.TrimSpace(typed))
		if err == nil {
			return parsed
		}
	}
	return 0
}

func truncateResultString(value string, limit int) string {
	if len(value) <= limit {
		return value
	}
	return value[:limit] + "...[truncated]"
}

func truncateCompactString(value string, limit int) string {
	if len(value) <= limit {
		return value
	}
	if limit <= 0 {
		return ""
	}
	suffix := "..."
	if limit <= len(suffix) {
		return value[:limit]
	}
	return value[:limit-len(suffix)] + suffix
}

func payloadSize(payload any) int {
	body, err := json.Marshal(payload)
	if err != nil {
		return resultPayloadSoftLimit + 1
	}
	return len(body)
}

func postJSONWithCurlFallback(endpointURL string, headers map[string]string, payload any, out any) error {
	err := postJSONFunc(endpointURL, headers, payload, out)
	if err == nil {
		return nil
	}
	triggerReason, shouldFallback := curlFallbackTriggerReason(err)
	if !shouldFallback {
		return err
	}
	if validateCurlFallbackEndpoint(endpointURL) != nil {
		return err
	}
	traceLog(
		"go_http_submit_failed endpoint=%s body_size=%d fallback_trigger_reason=%s error=%s",
		safeEndpointLabel(endpointURL),
		payloadSize(payload),
		triggerReason,
		truncateResultString(redactSensitiveLogText(err.Error(), headers), responseBodyLogLimit),
	)
	traceLog(
		"http_json_curl_fallback_begin endpoint=%s body_size=%d reason=%s header_keys=%s",
		safeEndpointLabel(endpointURL),
		payloadSize(payload),
		triggerReason,
		strings.Join(sortedHeaderKeys(headers), ","),
	)
	curlStartedAt := time.Now()
	if fallbackErr := postJSONViaCurlFunc(endpointURL, headers, payload, out); fallbackErr != nil {
		traceLog(
			"http_json_curl_fallback_end endpoint=%s success=false reason=%s elapsed_ms=%d error=%s",
			safeEndpointLabel(endpointURL),
			triggerReason,
			time.Since(curlStartedAt).Milliseconds(),
			truncateResultString(redactSensitiveLogText(fallbackErr.Error(), headers), responseBodyLogLimit),
		)
		return fmt.Errorf("go net/http submit failed: %w; curl fallback failed: %v", err, fallbackErr)
	}
	traceLog(
		"http_json_curl_fallback_end endpoint=%s success=true reason=%s elapsed_ms=%d",
		safeEndpointLabel(endpointURL),
		triggerReason,
		time.Since(curlStartedAt).Milliseconds(),
	)
	return nil
}

func curlFallbackTriggerReason(err error) (string, bool) {
	if err == nil {
		return "", false
	}
	lowered := strings.ToLower(err.Error())
	if strings.Contains(lowered, "read console response") {
		return "", false
	}
	triggers := []struct {
		marker string
		reason string
	}{
		{"response_headers_timeout", "response_headers_timeout"},
		{"request_error: eof", "pre_response_eof"},
		{"unexpected eof", "unexpected_eof"},
		{"connection reset by peer", "connection_reset_by_peer"},
		{"broken pipe", "broken_pipe"},
		{"server closed idle connection", "server_closed_idle_connection"},
		{"use of closed network connection", "closed_network_connection"},
	}
	for _, trigger := range triggers {
		if strings.Contains(lowered, trigger.marker) {
			return trigger.reason, true
		}
	}
	if strings.Contains(lowered, "failed before response") && strings.Contains(lowered, ": eof") {
		return "pre_response_eof", true
	}
	return "", false
}

func validateCurlFallbackEndpoint(rawURL string) error {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return err
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return fmt.Errorf("curl fallback endpoint scheme is not allowed")
	}
	if parsed.Host == "" {
		return fmt.Errorf("curl fallback endpoint host is required")
	}
	if parsed.RawQuery != "" || parsed.Fragment != "" {
		return fmt.Errorf("curl fallback endpoint query and fragment are not allowed")
	}
	parts := strings.Split(strings.Trim(parsed.EscapedPath(), "/"), "/")
	if len(parts) != 5 {
		return fmt.Errorf("curl fallback endpoint path is not allowed")
	}
	if parts[0] != "api" || parts[1] != "workers" || parts[2] != "commands" {
		return fmt.Errorf("curl fallback endpoint path is not a Worker command endpoint")
	}
	if parts[3] == "" || strings.ContainsAny(parts[3], "; \t\r\n") {
		return fmt.Errorf("curl fallback command id is invalid")
	}
	if parts[4] != "result" && parts[4] != "fail" {
		return fmt.Errorf("curl fallback endpoint must be result or fail")
	}
	return nil
}

func postJSONViaCurl(endpointURL string, headers map[string]string, payload any, out any) error {
	if err := validateCurlFallbackEndpoint(endpointURL); err != nil {
		return err
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	bodyPath, cleanupBody, err := writeCurlFallbackTempFile("liveline-worker-curl-body-*.json", body)
	if err != nil {
		return err
	}
	defer cleanupBody()

	headerText := buildCurlHeaderFile(headers)
	headerPath, cleanupHeader, err := writeCurlFallbackTempFile("liveline-worker-curl-headers-*.txt", []byte(headerText))
	if err != nil {
		return err
	}
	defer cleanupHeader()

	ctx, cancel := context.WithTimeout(context.Background(), postJSONTimeout+2*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "curl", buildCurlFallbackArgs(endpointURL, headerPath, bodyPath)...)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	output, err := cmd.Output()
	if ctx.Err() == context.DeadlineExceeded {
		return fmt.Errorf("curl fallback timed out endpoint=%s", safeEndpointLabel(endpointURL))
	}
	if err != nil {
		return fmt.Errorf("curl fallback command failed endpoint=%s exit_code=%d stdout=%s stderr=%s", safeEndpointLabel(endpointURL), curlExitCode(err), responseBodySummary(output), truncateResultString(redactSensitiveLogText(stderr.String(), headers), responseBodyLogLimit))
	}
	statusCode, responseBody, err := parseCurlIncludeOutput(output)
	if err != nil {
		return fmt.Errorf("curl fallback returned invalid response endpoint=%s stdout=%s stderr=%s", safeEndpointLabel(endpointURL), responseBodySummary(output), truncateResultString(redactSensitiveLogText(stderr.String(), headers), responseBodyLogLimit))
	}
	if err := json.Unmarshal(responseBody, out); err != nil {
		return fmt.Errorf("invalid curl fallback response status=%d body=%s", statusCode, responseBodySummary(responseBody))
	}
	traceLog(
		"http_json_curl_fallback_response endpoint=%s response_status=%d response_body_size=%d",
		safeEndpointLabel(endpointURL),
		statusCode,
		len(responseBody),
	)
	if statusCode < 200 || statusCode >= 300 {
		return fmt.Errorf("curl fallback returned status=%d body=%s", statusCode, responseBodySummary(responseBody))
	}
	return nil
}

func writeCurlFallbackTempFile(pattern string, contents []byte) (string, func(), error) {
	file, err := os.CreateTemp("", pattern)
	if err != nil {
		return "", nil, err
	}
	path := file.Name()
	cleanup := func() {
		_ = os.Remove(path)
	}
	if err := os.Chmod(path, 0o600); err != nil {
		file.Close()
		cleanup()
		return "", nil, err
	}
	if len(contents) > 0 {
		if _, err := file.Write(contents); err != nil {
			file.Close()
			cleanup()
			return "", nil, err
		}
	}
	if err := file.Sync(); err != nil {
		file.Close()
		cleanup()
		return "", nil, err
	}
	if err := file.Close(); err != nil {
		cleanup()
		return "", nil, err
	}
	return path, cleanup, nil
}

func buildCurlHeaderFile(headers map[string]string) string {
	lines := []string{"Content-Type: application/json"}
	for _, key := range sortedHeaderKeys(headers) {
		lines = append(lines, key+": "+headers[key])
	}
	return strings.Join(lines, "\n") + "\n"
}

func buildCurlFallbackArgs(endpointURL string, headerPath string, bodyPath string) []string {
	return []string{
		"-i",
		"--max-time",
		fmt.Sprintf("%d", int(postJSONTimeout.Seconds())),
		"--request",
		"POST",
		"--header",
		"@" + headerPath,
		"--data-binary",
		"@" + bodyPath,
		endpointURL,
	}
}

func parseCurlIncludeOutput(output []byte) (int, []byte, error) {
	if len(output) == 0 {
		return 0, nil, fmt.Errorf("empty curl response")
	}
	position := 0
	for position < len(output) {
		headerStart := findHTTPHeaderStart(output[position:])
		if headerStart < 0 {
			return 0, nil, fmt.Errorf("missing HTTP status line")
		}
		position += headerStart
		statusLineEnd := bytes.IndexByte(output[position:], '\n')
		if statusLineEnd < 0 {
			return 0, nil, fmt.Errorf("missing HTTP status line terminator")
		}
		statusLine := strings.TrimSpace(string(output[position : position+statusLineEnd]))
		statusCode, err := parseHTTPStatusCode(statusLine)
		if err != nil {
			return 0, nil, err
		}
		headerEndOffset, separatorLen := findHTTPHeaderEnd(output[position:])
		if headerEndOffset < 0 {
			return 0, nil, fmt.Errorf("missing HTTP header terminator")
		}
		bodyStart := position + headerEndOffset + separatorLen
		body := output[bodyStart:]
		if statusCode >= 100 && statusCode < 200 && bytes.HasPrefix(body, []byte("HTTP/")) {
			position = bodyStart
			continue
		}
		return statusCode, body, nil
	}
	return 0, nil, fmt.Errorf("missing final HTTP response")
}

func findHTTPHeaderStart(output []byte) int {
	if bytes.HasPrefix(output, []byte("HTTP/")) {
		return 0
	}
	if index := bytes.Index(output, []byte("\r\nHTTP/")); index >= 0 {
		return index + 2
	}
	if index := bytes.Index(output, []byte("\nHTTP/")); index >= 0 {
		return index + 1
	}
	return -1
}

func findHTTPHeaderEnd(output []byte) (int, int) {
	if index := bytes.Index(output, []byte("\r\n\r\n")); index >= 0 {
		return index, 4
	}
	if index := bytes.Index(output, []byte("\n\n")); index >= 0 {
		return index, 2
	}
	return -1, 0
}

func parseHTTPStatusCode(statusLine string) (int, error) {
	parts := strings.Fields(statusLine)
	if len(parts) < 2 || !strings.HasPrefix(parts[0], "HTTP/") {
		return 0, fmt.Errorf("invalid HTTP status line")
	}
	statusCode, err := strconv.Atoi(parts[1])
	if err != nil {
		return 0, fmt.Errorf("invalid HTTP status code")
	}
	return statusCode, nil
}

func curlExitCode(err error) int {
	var exitErr *exec.ExitError
	if errors.As(err, &exitErr) {
		return exitErr.ExitCode()
	}
	return -1
}

func redactSensitiveLogText(text string, headers map[string]string) string {
	redacted := text
	for _, value := range headers {
		if value == "" {
			continue
		}
		redacted = strings.ReplaceAll(redacted, value, "[redacted]")
	}
	return redacted
}

type resultSubmitDebugSummary struct {
	CommandType                      string                    `json:"command_type"`
	RawResultSize                    int                       `json:"raw_result_size"`
	SanitizedResultSize              int                       `json:"sanitized_result_size"`
	SubmitPayloadSize                int                       `json:"submit_payload_size"`
	ResultKeys                       []string                  `json:"result_keys"`
	ChecksCount                      int                       `json:"checks_count"`
	Checks                           []resultCheckDebugSummary `json:"checks"`
	LargestFieldPath                 string                    `json:"largest_field_path"`
	LargestFieldLength               int                       `json:"largest_field_length"`
	TruncationFlags                  map[string]bool           `json:"truncation_flags"`
	SensitiveMarkerDetected          bool                      `json:"sensitive_marker_detected"`
	ContainsNUL                      bool                      `json:"contains_nul"`
	SanitizedPayloadExceedsSoftLimit bool                      `json:"sanitized_payload_exceeds_soft_limit"`
	FallbackWouldBeTriggered         bool                      `json:"fallback_would_be_triggered"`
	NonJSONFriendlyTypes             []string                  `json:"non_json_friendly_types"`
	NoToken                          bool                      `json:"no_token"`
	NoWorkerSecret                   bool                      `json:"no_worker_secret"`
	NoFullBody                       bool                      `json:"no_full_body"`
	SafetyBoundary                   []string                  `json:"safety_boundary"`
}

type resultCheckDebugSummary struct {
	ID           string `json:"id"`
	Status       string `json:"status"`
	Passed       bool   `json:"passed"`
	DetailLength int    `json:"detail_length"`
}

func buildResultSubmitDebugSummary(commandType string, result map[string]any) resultSubmitDebugSummary {
	sanitized := sanitizeCommandResult(commandType, result)
	submitPayload := commandResultPayload{Result: sanitized}
	submitPayloadSize := payloadSize(submitPayload)
	largestPath, largestLength := largestStringField(result)
	containsNUL := valueContainsNUL(result)
	sensitiveMarkerDetected := valueContainsSensitiveMarker(result)
	nonJSONFriendlyTypes := collectNonJSONFriendlyTypes(result)

	return resultSubmitDebugSummary{
		CommandType:                      commandType,
		RawResultSize:                    jsonSize(result),
		SanitizedResultSize:              jsonSize(sanitized),
		SubmitPayloadSize:                submitPayloadSize,
		ResultKeys:                       safeSortedMapKeys(result),
		ChecksCount:                      checksCount(result["checks"]),
		Checks:                           summarizeResultChecks(result["checks"]),
		LargestFieldPath:                 largestPath,
		LargestFieldLength:               largestLength,
		TruncationFlags:                  resultTruncationFlags(result),
		SensitiveMarkerDetected:          sensitiveMarkerDetected,
		ContainsNUL:                      containsNUL,
		SanitizedPayloadExceedsSoftLimit: submitPayloadSize > resultPayloadSoftLimit,
		FallbackWouldBeTriggered:         submitPayloadSize > resultPayloadSoftLimit,
		NonJSONFriendlyTypes:             nonJSONFriendlyTypes,
		NoToken:                          true,
		NoWorkerSecret:                   true,
		NoFullBody:                       true,
		SafetyBoundary: []string{
			"diagnostic summary only",
			"no result submission",
			"no arbitrary shell accepted",
			"no socat/gost install, start, stop, or restart",
			"no listener binding",
			"no firewall mutation",
			"no Xray mutation",
			"no nodes.share_link read or modification",
			"no cutover",
			"no full result body included",
		},
	}
}

func traceWorkerCommandResultSubmit(command workerCommand, endpointURL string, headers map[string]string, summary resultSubmitDebugSummary, contentLength int, fallbackWouldBeTriggered bool) {
	traceLog(
		"worker_command_result_submit_prepare command_id=%s command_type=%s endpoint=result sanitized_result_size=%d submit_payload_size=%d fallback_would_be_triggered=%v result_keys=%s checks_count=%d largest_field_path=%s largest_field_length=%d content_length=%d header_keys=%s endpoint=%s",
		command.ID,
		command.CommandType,
		summary.SanitizedResultSize,
		summary.SubmitPayloadSize,
		fallbackWouldBeTriggered,
		strings.Join(summary.ResultKeys, ","),
		summary.ChecksCount,
		summary.LargestFieldPath,
		summary.LargestFieldLength,
		contentLength,
		strings.Join(sortedHeaderKeys(headers), ","),
		safeEndpointLabel(endpointURL),
	)
}

func traceTransitReadonlyCompactResult(command workerCommand, endpointURL string, info compactResultInfo) {
	traceLog(
		"worker_command_result_compact command_id=%s command_type=%s endpoint=result original_submit_payload_size=%d compact_submit_payload_size=%d compact_applied=%v checks_count=%d max_detail_length=%d details_removed=%v endpoint=%s",
		command.ID,
		command.CommandType,
		info.OriginalSubmitPayloadSize,
		info.CompactSubmitPayloadSize,
		info.CompactApplied,
		info.ChecksCount,
		info.MaxDetailLength,
		info.DetailsRemoved,
		safeEndpointLabel(endpointURL),
	)
}

func traceWorkerCommandFailureSubmit(commandID string, endpointURL string, headers map[string]string, payload commandFailurePayload) {
	resultPresent := payload.Result != nil
	resultKeys := []string{}
	if payload.Result != nil {
		resultKeys = safeSortedMapKeys(payload.Result)
	}
	commandType := "unknown"
	if payload.Result != nil {
		commandType = stringResultValue(payload.Result["command_type"])
		if commandType == "" {
			commandType = "unknown"
		}
	}
	traceLog(
		"worker_command_failure_submit_prepare command_id=%s command_type=%s endpoint=fail failure_payload_size=%d result_present=%v fallback_result_keys=%s header_keys=%s endpoint=%s",
		commandID,
		commandType,
		payloadSize(payload),
		resultPresent,
		strings.Join(resultKeys, ","),
		strings.Join(sortedHeaderKeys(headers), ","),
		safeEndpointLabel(endpointURL),
	)
}

func traceLog(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "liveline-worker trace "+format+"\n", args...)
}

func sortedHeaderKeys(headers map[string]string) []string {
	keys := make([]string, 0, len(headers))
	for key := range headers {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func safeEndpointLabel(rawURL string) string {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return "[invalid-url]"
	}
	host := parsed.Host
	if host == "" {
		host = "[no-host]"
	}
	path := parsed.EscapedPath()
	if path == "" {
		path = "/"
	}
	return host + path
}

func jsonSize(value any) int {
	body, err := json.Marshal(value)
	if err != nil {
		return -1
	}
	return len(body)
}

func sortedMapKeys(value map[string]any) []string {
	keys := make([]string, 0, len(value))
	for key := range value {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func safeSortedMapKeys(value map[string]any) []string {
	keys := make([]string, 0, len(value))
	for key := range value {
		if sensitiveResultKey(key) {
			keys = append(keys, "[redacted_sensitive_key]")
		} else {
			keys = append(keys, key)
		}
	}
	sort.Strings(keys)
	return keys
}

func checksCount(value any) int {
	switch typed := value.(type) {
	case []map[string]any:
		return len(typed)
	case []any:
		return len(typed)
	default:
		return 0
	}
}

func maxCheckDetailLength(value any) int {
	maxLength := 0
	checkLength := func(check map[string]any) {
		if length := len(stringResultValue(check["detail"])); length > maxLength {
			maxLength = length
		}
	}
	switch typed := value.(type) {
	case []map[string]any:
		for _, check := range typed {
			checkLength(check)
		}
	case []any:
		for _, item := range typed {
			if check, ok := item.(map[string]any); ok {
				checkLength(check)
			}
		}
	}
	return maxLength
}

func summarizeResultChecks(value any) []resultCheckDebugSummary {
	summaries := []resultCheckDebugSummary{}
	appendCheck := func(check map[string]any) {
		summaries = append(summaries, resultCheckDebugSummary{
			ID:           stringResultValue(check["id"]),
			Status:       stringResultValue(check["status"]),
			Passed:       boolResultValue(check["passed"]),
			DetailLength: len(fmt.Sprint(check["detail"])),
		})
	}
	switch typed := value.(type) {
	case []map[string]any:
		for _, check := range typed {
			appendCheck(check)
		}
	case []any:
		for _, item := range typed {
			if check, ok := item.(map[string]any); ok {
				appendCheck(check)
			}
		}
	}
	return summaries
}

func largestStringField(value any) (string, int) {
	path, length := largestStringFieldAt("$", value)
	return path, length
}

func largestStringFieldAt(path string, value any) (string, int) {
	switch typed := value.(type) {
	case map[string]any:
		bestPath := path
		bestLength := 0
		keys := sortedMapKeys(typed)
		for _, key := range keys {
			pathKey := key
			if sensitiveResultKey(key) {
				pathKey = "[redacted_sensitive_key]"
			}
			childPath, childLength := largestStringFieldAt(path+"."+pathKey, typed[key])
			if childLength > bestLength {
				bestPath = childPath
				bestLength = childLength
			}
		}
		return bestPath, bestLength
	case []any:
		bestPath := path
		bestLength := 0
		for index, item := range typed {
			childPath, childLength := largestStringFieldAt(fmt.Sprintf("%s[%d]", path, index), item)
			if childLength > bestLength {
				bestPath = childPath
				bestLength = childLength
			}
		}
		return bestPath, bestLength
	case []map[string]any:
		bestPath := path
		bestLength := 0
		for index, item := range typed {
			childPath, childLength := largestStringFieldAt(fmt.Sprintf("%s[%d]", path, index), item)
			if childLength > bestLength {
				bestPath = childPath
				bestLength = childLength
			}
		}
		return bestPath, bestLength
	case string:
		return path, len(typed)
	case fmt.Stringer:
		text := typed.String()
		return path, len(text)
	default:
		return path, 0
	}
}

func valueContainsNUL(value any) bool {
	switch typed := value.(type) {
	case map[string]any:
		for _, item := range typed {
			if valueContainsNUL(item) {
				return true
			}
		}
	case []any:
		for _, item := range typed {
			if valueContainsNUL(item) {
				return true
			}
		}
	case []map[string]any:
		for _, item := range typed {
			if valueContainsNUL(item) {
				return true
			}
		}
	case string:
		return strings.Contains(typed, "\x00")
	case fmt.Stringer:
		return strings.Contains(typed.String(), "\x00")
	}
	return false
}

func valueContainsSensitiveMarker(value any) bool {
	switch typed := value.(type) {
	case map[string]any:
		for _, item := range typed {
			if valueContainsSensitiveMarker(item) {
				return true
			}
		}
	case []any:
		for _, item := range typed {
			if valueContainsSensitiveMarker(item) {
				return true
			}
		}
	case []map[string]any:
		for _, item := range typed {
			if valueContainsSensitiveMarker(item) {
				return true
			}
		}
	case string:
		return stringContainsSensitiveMarker(typed)
	case fmt.Stringer:
		return stringContainsSensitiveMarker(typed.String())
	}
	return false
}

func stringContainsSensitiveMarker(value string) bool {
	lowered := strings.ToLower(value)
	for _, marker := range []string{"vless://", "vmess://", "ss://", "trojan://"} {
		if strings.Contains(lowered, marker) {
			return true
		}
	}
	return false
}

func resultTruncationFlags(value any) map[string]bool {
	flags := map[string]bool{
		"string_over_limit": false,
		"list_over_limit":   false,
		"map_over_limit":    false,
		"checks_over_limit": false,
	}
	markTruncationFlags(value, flags)
	if checksCount(valueFromMap(value, "checks")) > resultListLimit {
		flags["checks_over_limit"] = true
	}
	return flags
}

func markTruncationFlags(value any, flags map[string]bool) {
	switch typed := value.(type) {
	case map[string]any:
		if len(typed) > resultListLimit {
			flags["map_over_limit"] = true
		}
		for _, item := range typed {
			markTruncationFlags(item, flags)
		}
	case []any:
		if len(typed) > resultListLimit {
			flags["list_over_limit"] = true
		}
		for _, item := range typed {
			markTruncationFlags(item, flags)
		}
	case []map[string]any:
		if len(typed) > resultListLimit {
			flags["list_over_limit"] = true
		}
		for _, item := range typed {
			markTruncationFlags(item, flags)
		}
	case string:
		if len(typed) > resultStringLimit {
			flags["string_over_limit"] = true
		}
	case fmt.Stringer:
		if len(typed.String()) > resultStringLimit {
			flags["string_over_limit"] = true
		}
	}
}

func valueFromMap(value any, key string) any {
	if typed, ok := value.(map[string]any); ok {
		return typed[key]
	}
	return nil
}

func collectNonJSONFriendlyTypes(value any) []string {
	seen := map[string]bool{}
	collectNonJSONFriendlyTypesAt("$", value, seen)
	items := make([]string, 0, len(seen))
	for item := range seen {
		items = append(items, item)
	}
	sort.Strings(items)
	return items
}

func collectNonJSONFriendlyTypesAt(path string, value any, seen map[string]bool) {
	switch typed := value.(type) {
	case nil, bool, string, float64, float32, int, int8, int16, int32, int64, uint, uint8, uint16, uint32, uint64, json.Number:
		return
	case map[string]any:
		for key, item := range typed {
			pathKey := key
			if sensitiveResultKey(key) {
				pathKey = "[redacted_sensitive_key]"
			}
			collectNonJSONFriendlyTypesAt(path+"."+pathKey, item, seen)
		}
	case []any:
		for index, item := range typed {
			collectNonJSONFriendlyTypesAt(fmt.Sprintf("%s[%d]", path, index), item, seen)
		}
	case []map[string]any:
		for index, item := range typed {
			collectNonJSONFriendlyTypesAt(fmt.Sprintf("%s[%d]", path, index), item, seen)
		}
	case fmt.Stringer:
		return
	default:
		seen[fmt.Sprintf("%s:%T", path, value)] = true
	}
}

func postJSON(url string, headers map[string]string, payload any, out any) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	startedAt := time.Now().UTC()
	endpoint := safeEndpointLabel(url)
	traceLog(
		"http_json_submit_begin endpoint=%s method=POST body_size=%d timeout=%s start=%s",
		endpoint,
		len(body),
		postJSONTimeout,
		startedAt.Format(time.RFC3339Nano),
	)
	request, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		traceLog(
			"http_json_submit_end endpoint=%s method=POST body_size=%d elapsed_ms=%d success=false error_classification=request_build_failed",
			endpoint,
			len(body),
			time.Since(startedAt).Milliseconds(),
		)
		return err
	}
	request.Header.Set("Content-Type", "application/json")
	request.ContentLength = int64(len(body))
	for key, value := range headers {
		request.Header.Set(key, value)
	}

	response, err := postJSONHTTPClient.Do(request)
	if err != nil {
		classified := describeHTTPPostError(err)
		traceLog(
			"http_json_submit_end endpoint=%s method=POST body_size=%d timeout=%s elapsed_ms=%d success=false error_classification=%s",
			endpoint,
			len(body),
			postJSONTimeout,
			time.Since(startedAt).Milliseconds(),
			classified,
		)
		return fmt.Errorf("post %s failed before response: %s", endpoint, classified)
	}
	defer response.Body.Close()

	responseBody, err := io.ReadAll(io.LimitReader(response.Body, 1<<20))
	if err != nil {
		classified := describeHTTPPostError(err)
		traceLog(
			"http_json_submit_end endpoint=%s method=POST body_size=%d timeout=%s elapsed_ms=%d success=false response_status=%d error_classification=%s",
			endpoint,
			len(body),
			postJSONTimeout,
			time.Since(startedAt).Milliseconds(),
			response.StatusCode,
			classified,
		)
		return fmt.Errorf("read console response status=%d failed: %s", response.StatusCode, describeHTTPPostError(err))
	}
	if err := json.Unmarshal(responseBody, out); err != nil {
		traceLog(
			"http_json_submit_end endpoint=%s method=POST body_size=%d timeout=%s elapsed_ms=%d success=false response_status=%d error_classification=invalid_json_response",
			endpoint,
			len(body),
			postJSONTimeout,
			time.Since(startedAt).Milliseconds(),
			response.StatusCode,
		)
		return fmt.Errorf("invalid console response status=%d body=%s", response.StatusCode, responseBodySummary(responseBody))
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		traceLog(
			"http_json_submit_end endpoint=%s method=POST body_size=%d timeout=%s elapsed_ms=%d success=false response_status=%d error_classification=non_2xx_response",
			endpoint,
			len(body),
			postJSONTimeout,
			time.Since(startedAt).Milliseconds(),
			response.StatusCode,
		)
		return fmt.Errorf("console returned status=%d body=%s", response.StatusCode, responseBodySummary(responseBody))
	}
	traceLog(
		"http_json_submit_end endpoint=%s method=POST body_size=%d timeout=%s elapsed_ms=%d success=true response_status=%d",
		endpoint,
		len(body),
		postJSONTimeout,
		time.Since(startedAt).Milliseconds(),
		response.StatusCode,
	)
	return nil
}

func describeHTTPPostError(err error) string {
	if err == nil {
		return "unknown_error"
	}
	phase := "request_error"
	var urlErr *url.Error
	if errors.As(err, &urlErr) {
		err = urlErr.Err
	}
	text := err.Error()
	lowered := strings.ToLower(text)
	var netErr net.Error
	isTimeout := errors.Is(err, context.DeadlineExceeded) || (errors.As(err, &netErr) && netErr.Timeout())
	switch {
	case strings.Contains(lowered, "awaiting headers"):
		phase = "response_headers_timeout"
	case strings.Contains(lowered, "tls handshake timeout"):
		phase = "tls_handshake_timeout"
	case strings.Contains(lowered, "no such host"):
		phase = "dns_resolution_failed"
	case strings.Contains(lowered, "connection refused"):
		phase = "connect_refused"
	case strings.Contains(lowered, "i/o timeout"):
		phase = "io_timeout"
	case isTimeout:
		phase = "request_timeout"
	}
	return fmt.Sprintf("%s: %s", phase, truncateResultString(text, responseBodyLogLimit))
}

func responseBodySummary(body []byte) string {
	summary := string(body)
	summary = strings.ReplaceAll(summary, "\x00", "")
	return truncateResultString(summary, responseBodyLogLimit)
}

func joinURL(base string, path string) string {
	return strings.TrimRight(strings.TrimSpace(base), "/") + path
}

func validateRole(role string) (string, error) {
	cleaned := strings.ToLower(strings.TrimSpace(role))
	if cleaned != "landing" && cleaned != "transit" {
		return "", errors.New("role must be landing or transit")
	}
	return cleaned, nil
}

func writeConfig(path string, cfg config) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	content := strings.Join([]string{
		"console_url: " + quoteConfig(cfg.ConsoleURL),
		"worker_id: " + quoteConfig(cfg.WorkerID),
		"worker_secret: " + quoteConfig(cfg.WorkerSecret),
		"role: " + quoteConfig(cfg.Role),
		"interface_name: " + quoteConfig(cfg.InterfaceName),
		fmt.Sprintf("heartbeat_interval_seconds: %d", cfg.HeartbeatIntervalSeconds),
		"",
	}, "\n")
	return os.WriteFile(path, []byte(content), 0o600)
}

func readConfig(path string) (config, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return config{}, err
	}
	values := map[string]string{}
	for _, line := range strings.Split(string(content), "\n") {
		cleaned := strings.TrimSpace(line)
		if cleaned == "" || strings.HasPrefix(cleaned, "#") {
			continue
		}
		key, value, ok := strings.Cut(cleaned, ":")
		if !ok {
			continue
		}
		values[strings.TrimSpace(key)] = unquoteConfig(strings.TrimSpace(value))
	}
	interval, _ := strconv.Atoi(values["heartbeat_interval_seconds"])
	if interval <= 0 {
		interval = 60
	}
	return config{
		ConsoleURL:               values["console_url"],
		WorkerID:                 values["worker_id"],
		WorkerSecret:             values["worker_secret"],
		Role:                     values["role"],
		InterfaceName:            values["interface_name"],
		HeartbeatIntervalSeconds: interval,
	}, nil
}

func quoteConfig(value string) string {
	return strconv.Quote(value)
}

func unquoteConfig(value string) string {
	if unquoted, err := strconv.Unquote(value); err == nil {
		return unquoted
	}
	return strings.Trim(value, "\"'")
}

func collectSystemInfo(role string, interfaceName string) map[string]any {
	info := map[string]any{
		"worker_version": workerVersion,
		"interface_name": interfaceName,
		"role":           role,
		"os":             osReleaseSummary(),
		"kernel":         commandOutput("uname", "-r"),
		"uptime_seconds": uptimeSeconds(),
		"cpu":            cpuSummary(),
		"memory":         memorySummary(),
		"disk":           diskSummary("/"),
		"services":       serviceSummary(role),
	}
	return info
}

func osReleaseSummary() string {
	content, err := os.ReadFile("/etc/os-release")
	if err != nil {
		return "unknown"
	}
	values := map[string]string{}
	for _, line := range strings.Split(string(content), "\n") {
		key, value, ok := strings.Cut(line, "=")
		if ok {
			values[key] = strings.Trim(value, "\"")
		}
	}
	if pretty := values["PRETTY_NAME"]; pretty != "" {
		return pretty
	}
	if name := values["NAME"]; name != "" {
		return name
	}
	return "unknown"
}

func uptimeSeconds() int64 {
	content, err := os.ReadFile("/proc/uptime")
	if err != nil {
		return 0
	}
	fields := strings.Fields(string(content))
	if len(fields) == 0 {
		return 0
	}
	value, err := strconv.ParseFloat(fields[0], 64)
	if err != nil {
		return 0
	}
	return int64(value)
}

func cpuSummary() map[string]any {
	content, err := os.ReadFile("/proc/cpuinfo")
	if err != nil {
		return map[string]any{"model": "unknown"}
	}
	model := "unknown"
	cores := 0
	for _, line := range strings.Split(string(content), "\n") {
		if strings.HasPrefix(line, "processor") {
			cores++
		}
		if strings.HasPrefix(line, "model name") && model == "unknown" {
			_, value, _ := strings.Cut(line, ":")
			model = strings.TrimSpace(value)
		}
	}
	return map[string]any{"model": model, "cores": cores}
}

func memorySummary() map[string]any {
	content, err := os.ReadFile("/proc/meminfo")
	if err != nil {
		return map[string]any{}
	}
	result := map[string]any{}
	for _, line := range strings.Split(string(content), "\n") {
		key, value, ok := strings.Cut(line, ":")
		if !ok {
			continue
		}
		switch key {
		case "MemTotal", "MemAvailable", "SwapTotal", "SwapFree":
			result[key] = strings.TrimSpace(value)
		}
	}
	return result
}

func diskSummary(path string) map[string]any {
	var stat syscall.Statfs_t
	if err := syscall.Statfs(path, &stat); err != nil {
		return map[string]any{}
	}
	total := stat.Blocks * uint64(stat.Bsize)
	free := stat.Bavail * uint64(stat.Bsize)
	return map[string]any{
		"path":        path,
		"total_bytes": total,
		"free_bytes":  free,
	}
}

func serviceSummary(role string) map[string]any {
	services := map[string]any{
		"liveline_worker": serviceState("liveline-worker", "liveline-worker"),
	}
	if role == "landing" {
		services["xray"] = serviceState("xray", "xray")
		return services
	}
	if role == "transit" {
		services["socat"] = serviceState("socat", "socat")
		services["gost"] = serviceState("gost", "gost")
	}
	return services
}

func collectLandingPreflight(cfg config, hostname string) map[string]any {
	warnings := []any{}
	errors := []string{}
	ssOutput, ssErr := readonlyCommandOutput("ss", "-lntup")
	if ssErr != "" {
		warnings = append(warnings, map[string]any{
			"code":    "ss_unavailable",
			"message": "ss -lntup unavailable: " + ssErr,
		})
	}
	firewall, firewallWarnings := firewallReadonlySummary()
	for _, warning := range firewallWarnings {
		warnings = append(warnings, map[string]any{
			"code":    "firewall_readonly_warning",
			"message": warning,
		})
	}
	network := landingNetworkSummary(cfg.InterfaceName, ssOutput)
	if mismatch, ok := network["interface_mismatch"].(bool); ok && mismatch {
		defaultIface, _ := network["default_route_interface"].(string)
		warnings = append(warnings, map[string]any{
			"code":                    "interface_mismatch",
			"message":                 fmt.Sprintf("Worker configured interface %s differs from default route interface %s.", cfg.InterfaceName, defaultIface),
			"worker_config_interface": cfg.InterfaceName,
			"default_route_interface": defaultIface,
		})
	}
	return map[string]any{
		"preflight_version": "0.2",
		"worker_version":    workerVersion,
		"system":            landingSystemSummary(cfg, hostname),
		"network":           network,
		"ports":             landingPortSummary(ssOutput),
		"services":          landingServiceChecks(),
		"binaries":          binaryChecks([]string{"xray", "x-ui", "3x-ui", "nginx", "caddy", "socat", "gost", "docker", "iptables", "ufw", "firewall-cmd"}),
		"firewall":          firewall,
		"xray_discovery":    xrayDiscoverySummary(),
		"warnings":          warnings,
		"errors":            errors,
	}
}

func landingSystemSummary(cfg config, hostname string) map[string]any {
	return map[string]any{
		"hostname":                hostname,
		"uname":                   readonlyCommandValue("uname", "-a"),
		"os_release":              osReleaseSummary(),
		"uptime_seconds":          uptimeSeconds(),
		"current_user":            readonlyCommandValue("whoami"),
		"worker_running_user":     readonlyCommandValue("whoami"),
		"uid":                     os.Getuid(),
		"architecture":            readonlyCommandValue("uname", "-m"),
		"role":                    cfg.Role,
		"interface_name":          cfg.InterfaceName,
		"worker_config_interface": cfg.InterfaceName,
	}
}

func landingNetworkSummary(interfaceName string, ssOutput string) map[string]any {
	defaultRoute := readonlyCommandValue("ip", "route", "show", "default")
	defaultInfo := parseDefaultRoute(defaultRoute)
	localIPs := localIPList()
	primaryInterface := defaultInfo.Interface
	if primaryInterface == "" {
		primaryInterface = interfaceName
	}
	primaryIP := localIPv4ForInterface(localIPs, primaryInterface)
	if primaryIP == "" && primaryInterface == interfaceName {
		primaryIP = interfaceAddress(interfaceName)
	}
	interfaceMismatch := strings.TrimSpace(interfaceName) != "" &&
		strings.TrimSpace(defaultInfo.Interface) != "" &&
		strings.TrimSpace(interfaceName) != strings.TrimSpace(defaultInfo.Interface)

	return map[string]any{
		"worker_config_interface": interfaceName,
		"default_route_interface": defaultInfo.Interface,
		"default_route_gateway":   defaultInfo.Gateway,
		"primary_interface":       primaryInterface,
		"primary_interface_ip":    primaryIP,
		"interface_mismatch":      interfaceMismatch,
		"local_ips":               localIPs,
		"public_ip":               "not_checked",
		"ip_route":                defaultRoute,
		"listening_summary":       summarizeListeningPorts(ssOutput, 30),
	}
}

type defaultRouteInfo struct {
	Interface string
	Gateway   string
}

func parseDefaultRoute(output string) defaultRouteInfo {
	for _, line := range strings.Split(output, "\n") {
		fields := strings.Fields(strings.TrimSpace(line))
		if len(fields) == 0 || fields[0] != "default" {
			continue
		}
		info := defaultRouteInfo{}
		for idx := 0; idx < len(fields)-1; idx++ {
			switch fields[idx] {
			case "dev":
				info.Interface = fields[idx+1]
			case "via":
				info.Gateway = fields[idx+1]
			}
		}
		return info
	}
	return defaultRouteInfo{}
}

func localIPv4ForInterface(localIPs []map[string]string, interfaceName string) string {
	if strings.TrimSpace(interfaceName) == "" {
		return ""
	}
	for _, item := range localIPs {
		if item["interface"] != interfaceName {
			continue
		}
		ip := net.ParseIP(item["ip"])
		if ip != nil && ip.To4() != nil {
			return item["ip"]
		}
	}
	return ""
}

func localIPList() []map[string]string {
	result := []map[string]string{}
	interfaces, err := net.Interfaces()
	if err != nil {
		return result
	}
	for _, iface := range interfaces {
		addrs, err := iface.Addrs()
		if err != nil {
			continue
		}
		for _, addr := range addrs {
			ip, _, err := net.ParseCIDR(addr.String())
			if err != nil || ip == nil {
				continue
			}
			result = append(result, map[string]string{
				"interface": iface.Name,
				"ip":        ip.String(),
			})
		}
	}
	return result
}

func summarizeListeningPorts(ssOutput string, limit int) []map[string]any {
	rows, _ := listeningPortRows(ssOutput)
	if limit > 0 && len(rows) > limit {
		return rows[:limit]
	}
	return rows
}

func landingPortSummary(ssOutput string) map[string]any {
	rows, skipped := listeningPortRows(ssOutput)
	checks := portChecksFromRows(rows, []int{22, 80, 443, 8443, 18443, formalLandingPort})
	importantPorts := map[string]any{}
	for _, check := range checks {
		port := fmt.Sprintf("%v", check["port"])
		if listening, ok := check["listening"].(bool); ok && listening {
			check["status"] = "listening"
		} else {
			check["status"] = "not_listening"
		}
		importantPorts[port] = check
	}
	return map[string]any{
		"listening_count":     len(rows),
		"listening_summary":   summarizeListeningPorts(ssOutput, 30),
		"important_ports":     importantPorts,
		"debug_skipped_count": skipped,
	}
}

func portChecksFromRows(rows []map[string]any, ports []int) []map[string]any {
	result := []map[string]any{}
	for _, port := range ports {
		listeners := []map[string]any{}
		for _, row := range rows {
			parsedPort, ok := row["port"].(int)
			if !ok || parsedPort != port {
				continue
			}
			listeners = append(listeners, map[string]any{
				"listen_address": row["listen_address"],
				"process":        row["process"],
			})
		}
		result = append(result, map[string]any{
			"port":      port,
			"protocol":  "tcp",
			"listening": len(listeners) > 0,
			"listeners": listeners,
		})
	}
	return result
}

func listeningPortRows(ssOutput string) ([]map[string]any, int) {
	rows := []map[string]any{}
	skipped := 0
	for _, line := range strings.Split(ssOutput, "\n") {
		cleaned := strings.TrimSpace(line)
		if cleaned == "" || strings.HasPrefix(cleaned, "Netid") || strings.HasPrefix(cleaned, "State") {
			continue
		}
		fields := strings.Fields(cleaned)
		if !isTCPListenLine(fields) {
			continue
		}
		localField := localAddressField(fields)
		address, port, ok := parseListenAddressAndPort(localField)
		if !ok || address == "" || port <= 0 {
			skipped++
			continue
		}
		rows = append(rows, map[string]any{
			"protocol":       "tcp",
			"listen_address": address,
			"port":           port,
			"process":        processSummary(cleaned),
		})
	}
	return rows, skipped
}

func isTCPListenLine(fields []string) bool {
	if len(fields) < 4 {
		return false
	}
	if strings.HasPrefix(fields[0], "tcp") {
		return len(fields) >= 5 && strings.EqualFold(fields[1], "LISTEN")
	}
	return strings.EqualFold(fields[0], "LISTEN")
}

func localAddressField(fields []string) string {
	if len(fields) == 0 {
		return ""
	}
	if strings.HasPrefix(fields[0], "tcp") {
		if len(fields) >= 5 {
			return fields[4]
		}
		return ""
	}
	if len(fields) >= 4 {
		return fields[3]
	}
	return ""
}

func parseListenAddressAndPort(field string) (string, int, bool) {
	cleaned := strings.TrimSpace(field)
	if cleaned == "" {
		return "", 0, false
	}
	var address string
	var portText string
	if strings.HasPrefix(cleaned, "[") {
		end := strings.LastIndex(cleaned, "]:")
		if end < 0 {
			return "", 0, false
		}
		address = strings.Trim(cleaned[:end+1], "[]")
		portText = cleaned[end+2:]
	} else {
		idx := strings.LastIndex(cleaned, ":")
		if idx < 0 {
			return "", 0, false
		}
		address = cleaned[:idx]
		portText = cleaned[idx+1:]
	}
	portText = strings.Trim(portText, "[]")
	port, err := strconv.Atoi(portText)
	if err != nil || port <= 0 || port > 65535 {
		return "", 0, false
	}
	return strings.TrimSpace(address), port, true
}

func processSummary(line string) string {
	marker := "users:("
	idx := strings.Index(line, marker)
	if idx < 0 {
		return ""
	}
	return truncateReadonlyOutput(line[idx:], 500)
}

func landingServiceChecks() []map[string]any {
	services := []string{"xray", "x-ui", "3x-ui", "nginx", "caddy", "socat", "gost", "docker", "liveline-worker"}
	result := []map[string]any{}
	for _, service := range services {
		result = append(result, serviceCheck(service))
	}
	return result
}

func serviceCheck(serviceName string) map[string]any {
	exists := false
	if _, err := exec.LookPath("systemctl"); err == nil {
		_, statusErr := readonlyCommandOutput("systemctl", "status", serviceName, "--no-pager", "--lines=0")
		exists = statusErr == ""
	}
	return map[string]any{
		"name":    serviceName,
		"exists":  exists,
		"active":  readonlyCommandValue("systemctl", "is-active", serviceName),
		"enabled": readonlyCommandValue("systemctl", "is-enabled", serviceName),
		"status_summary": truncateReadonlyOutput(
			readonlyCommandValue("systemctl", "status", serviceName, "--no-pager", "--lines=5"),
			1000,
		),
	}
}

func binaryChecks(names []string) []map[string]any {
	result := []map[string]any{}
	for _, name := range names {
		path, err := exec.LookPath(name)
		result = append(result, map[string]any{
			"name":    name,
			"present": err == nil,
			"path":    path,
		})
	}
	return result
}

func firewallReadonlySummary() (map[string]any, []string) {
	warnings := []string{}
	result := map[string]any{}
	if _, err := exec.LookPath("ufw"); err == nil {
		output, cmdErr := readonlyCommandOutput("ufw", "status")
		result["ufw_status"] = output
		if cmdErr != "" {
			warnings = append(warnings, "ufw status unavailable: "+cmdErr)
		}
	} else {
		result["ufw_status"] = "not_installed"
	}
	if _, err := exec.LookPath("firewall-cmd"); err == nil {
		output, cmdErr := readonlyCommandOutput("firewall-cmd", "--state")
		result["firewalld_state"] = output
		if cmdErr != "" {
			warnings = append(warnings, "firewall-cmd --state unavailable: "+cmdErr)
		}
	} else {
		result["firewalld_state"] = "not_installed"
	}
	if _, err := exec.LookPath("iptables"); err == nil {
		output, cmdErr := readonlyCommandOutput("iptables", "-S")
		result["iptables_rules_summary"] = output
		if cmdErr != "" {
			warnings = append(warnings, "iptables -S unavailable: "+cmdErr)
		}
	} else {
		result["iptables_rules_summary"] = "not_installed"
	}
	return result, warnings
}

func xrayDiscoverySummary() map[string]any {
	paths := []string{
		"/usr/local/etc/xray/config.json",
		"/etc/xray/config.json",
		"/usr/local/x-ui",
		"/etc/x-ui",
		"/etc/systemd/system/xray.service",
		"/etc/systemd/system/x-ui.service",
		"/etc/systemd/system/3x-ui.service",
	}
	items := []map[string]any{}
	for _, path := range paths {
		info := map[string]any{
			"path":   path,
			"exists": false,
		}
		stat, err := os.Stat(path)
		if err == nil {
			info["exists"] = true
			info["is_dir"] = stat.IsDir()
			info["size_bytes"] = stat.Size()
			info["mtime"] = stat.ModTime().UTC().Format(time.RFC3339)
		}
		items = append(items, info)
	}
	return map[string]any{"paths": items}
}

func serviceState(serviceName string, binaryName string) map[string]any {
	exists := false
	if _, err := exec.LookPath(binaryName); err == nil {
		exists = true
	}
	active := "unknown"
	if _, err := exec.LookPath("systemctl"); err == nil {
		output := strings.TrimSpace(commandOutput("systemctl", "is-active", serviceName))
		if output != "" {
			active = output
		}
	}
	return map[string]any{"binary_present": exists, "systemd_active": active}
}

func readonlyCommandValue(name string, args ...string) string {
	output, errText := readonlyCommandOutput(name, args...)
	if errText != "" && output == "" {
		return "unavailable: " + errText
	}
	return output
}

func readonlyCommandOutput(name string, args ...string) (string, string) {
	if _, err := exec.LookPath(name); err != nil {
		return "", "command_not_found"
	}
	ctx, cancel := context.WithTimeout(context.Background(), readonlyCommandTimeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, name, args...)
	output, err := cmd.CombinedOutput()
	trimmed := truncateReadonlyOutput(strings.TrimSpace(string(output)), readonlyOutputLimit)
	if ctx.Err() == context.DeadlineExceeded {
		return trimmed, "timeout"
	}
	if err != nil {
		if trimmed != "" {
			return trimmed, err.Error()
		}
		return "", err.Error()
	}
	return trimmed, ""
}

func truncateReadonlyOutput(value string, limit int) string {
	if len(value) <= limit {
		return value
	}
	return value[:limit] + "...[truncated]"
}

func commandOutput(name string, args ...string) string {
	cmd := exec.Command(name, args...)
	output, err := cmd.CombinedOutput()
	if err != nil {
		trimmed := strings.TrimSpace(string(output))
		if trimmed != "" {
			return trimmed
		}
		return "unknown"
	}
	return strings.TrimSpace(string(output))
}

func interfaceAddress(interfaceName string) string {
	iface, err := net.InterfaceByName(interfaceName)
	if err != nil {
		return ""
	}
	addrs, err := iface.Addrs()
	if err != nil {
		return ""
	}
	for _, addr := range addrs {
		ip, _, err := net.ParseCIDR(addr.String())
		if err != nil || ip == nil {
			continue
		}
		if ipv4 := ip.To4(); ipv4 != nil && !ipv4.IsLoopback() {
			return ipv4.String()
		}
	}
	return ""
}
