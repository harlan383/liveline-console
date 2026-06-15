package main

import (
	"bytes"
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

const workerVersion = "0.1.1-stage-3.3.28"
const commandPollIntervalSeconds = 20

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
