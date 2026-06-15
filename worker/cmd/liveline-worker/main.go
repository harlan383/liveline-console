package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"
)

const workerVersion = "0.1.3-stage-3.3.33"
const commandPollIntervalSeconds = 20
const readonlyCommandTimeout = 5 * time.Second
const readonlyOutputLimit = 12000

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
		if reportErr := postWorkerCommandFailure(cfg, command.ID, err); reportErr != nil {
			return fmt.Errorf("command %s failed: %v; failure report failed: %w", command.ID, err, reportErr)
		}
		return fmt.Errorf("command %s failed: %w", command.ID, err)
	}
	if err := postWorkerCommandResult(cfg, command.ID, result); err != nil {
		return err
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
	default:
		return nil, fmt.Errorf("unsupported command_type %q", command.CommandType)
	}
}

func postWorkerCommandResult(cfg config, commandID string, result map[string]any) error {
	headers := map[string]string{
		"X-Worker-Id":     cfg.WorkerID,
		"X-Worker-Secret": cfg.WorkerSecret,
	}
	var response apiResponse[map[string]any]
	payload := commandResultPayload{Result: result}
	if err := postJSON(joinURL(cfg.ConsoleURL, "/api/workers/commands/"+commandID+"/result"), headers, payload, &response); err != nil {
		return err
	}
	if !response.Success {
		return fmt.Errorf("command result rejected: %s", response.Message)
	}
	return nil
}

func postWorkerCommandFailure(cfg config, commandID string, commandErr error) error {
	headers := map[string]string{
		"X-Worker-Id":     cfg.WorkerID,
		"X-Worker-Secret": cfg.WorkerSecret,
	}
	var response apiResponse[map[string]any]
	payload := commandFailurePayload{ErrorMessage: commandErr.Error()}
	if err := postJSON(joinURL(cfg.ConsoleURL, "/api/workers/commands/"+commandID+"/fail"), headers, payload, &response); err != nil {
		return err
	}
	if !response.Success {
		return fmt.Errorf("command failure rejected: %s", response.Message)
	}
	return nil
}

func postJSON(url string, headers map[string]string, payload any, out any) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	request, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	request.Header.Set("Content-Type", "application/json")
	for key, value := range headers {
		request.Header.Set(key, value)
	}

	client := &http.Client{Timeout: 15 * time.Second}
	response, err := client.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()

	responseBody, err := io.ReadAll(io.LimitReader(response.Body, 1<<20))
	if err != nil {
		return err
	}
	if err := json.Unmarshal(responseBody, out); err != nil {
		return fmt.Errorf("invalid console response status=%d", response.StatusCode)
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		if envelope, ok := out.(*apiResponse[registerResult]); ok && envelope.Message != "" {
			return fmt.Errorf("console returned status=%d: %s", response.StatusCode, envelope.Message)
		}
		return fmt.Errorf("console returned status=%d", response.StatusCode)
	}
	return nil
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
	checks := portChecksFromRows(rows, []int{22, 80, 443, 8443, 18443})
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
