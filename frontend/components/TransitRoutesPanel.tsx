"use client";

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import {
  apiFetch,
  apiFormFetch,
  createTransitReadonlyPreflightCommand,
  createWorkerCommand,
  createTransitWorkerBootstrap,
  exportNodeShareLink,
  listWorkerCommands,
  regenerateTransitWorkerBootstrap,
  type CsrfResult,
  type NodeData,
  type NodeListResult,
  type ReadonlyPreflightCheckItem,
  type ReadonlyPreflightPlanRequest,
  type ReadonlyPreflightPlanResponse,
  type TaskData,
  type TaskLogData,
  type TransitResourceData,
  type TransitResourceListResult,
  type TransitResourcePayload,
  type TransitRouteCreateResult,
  type TransitRouteData,
  type TransitRouteDiagnoseResult,
  type TransitRouteListResult,
  type TransitRouteRestartSocatResult,
  type TransitReadonlyPreflightCommandRequest,
  type WorkerRole,
  type WorkerCommandData,
  type WorkerTokenCreateResult,
  requestReadonlyPreflightPlan,
} from "@/lib/api";
import { RouteSafetyGuardrails } from "@/components/RouteSafetyGuardrails";
import { TransitReadonlyPreflightSimplePanel } from "@/components/TransitReadonlyPreflightSimplePanel";

const terminalStatuses = new Set(["success", "failed", "cancelled", "timeout"]);
const workerCommandTerminalStatuses = new Set(["succeeded", "failed", "expired", "cancelled"]);
const SOCAT_RESOURCE_ID = "6d67c275-8ac9-4775-9519-c89b50718157";
const PROTECTED_LISTEN_PORTS = new Set(["22", "8443", "18443", "20575"]);
const PROTECTED_LISTEN_PORT_MESSAGES: Record<string, string> = {
  "22": "22 是 SSH 端口，不能作为中转监听端口。",
  "8443": "8443 当前保留给 gost 回退链路，不能作为新转发端口。",
  "18443": "18443 当前为 socat 正式链路，不能被新转发覆盖或复用。",
  "20575": "20575 是历史问题端口，不能作为中转监听端口。",
};
const secretKeyPattern = /(private|private_key|passphrase|password|passwd|secret|token|cookie|session|admin_password_hash|ssh_key)/i;
const linkPattern = /(vless|vmess|trojan|ss):\/\//i;
const privateKeyPattern = /BEGIN (OPENSSH|RSA|EC|DSA)? ?PRIVATE KEY/i;

type ForwardingMethod = "gost" | "socat";
type TransitModalMode = "addServer" | "editServer" | "addRoute" | "viewRoute" | null;
type DiagnosticItemSpec = {
  key: string;
  label: string;
  purpose: string;
  failureMeaning: string;
  nextAction: string;
};
type ReadonlyPreflightItemSpec = {
  label: string;
  scope: string;
  detail: string;
};
type TransitServerFormState = {
  name: string;
  entryHost: string;
  sshPort: string;
  sshUsername: string;
  provider: string;
  notes: string;
};
type WorkerBootstrapFormState = {
  name: string;
  ip: string;
  expiresInMinutes: string;
};
type TransitRouteDraftState = {
  routeName: string;
  forwardingMethod: ForwardingMethod;
  listenPort: string;
  landingVpsId: string;
  targetNodeId: string;
  targetPort: string;
  notes: string;
};

const emptyTransitServerForm: TransitServerFormState = {
  name: "",
  entryHost: "",
  sshPort: "22",
  sshUsername: "root",
  provider: "",
  notes: "",
};

const emptyWorkerBootstrapForm: WorkerBootstrapFormState = {
  name: "",
  ip: "",
  expiresInMinutes: "60",
};

const emptyTransitRouteDraft: TransitRouteDraftState = {
  routeName: "",
  forwardingMethod: "socat",
  listenPort: "",
  landingVpsId: "",
  targetNodeId: "",
  targetPort: "443",
  notes: "",
};

function CollapsibleWarning({
  title,
  children,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <details className={`warning-box collapsible-notice${wide ? " wide-field" : ""}`}>
      <summary className="collapsible-summary">
        <strong>{title}</strong>
        <span className="notice-toggle-text">
          <span className="when-closed">查看说明</span>
          <span className="when-open">收起说明</span>
        </span>
      </summary>
      <div className="collapsible-body">{children}</div>
    </details>
  );
}

const readonlyPreflightItemSpecs: ReadonlyPreflightItemSpec[] = [
  {
    label: "中转服务器基础连通性",
    scope: "未来远程只读",
    detail: "确认目标中转服务器可在授权阶段进行只读登录和基础状态读取。",
  },
  {
    label: "新监听端口占用检查",
    scope: "未来远程只读",
    detail: "确认计划监听端口未被现有进程占用；本阶段只生成计划，不执行 ss/lsof。",
  },
  {
    label: "socat 18443 正式链路检查",
    scope: "未来远程只读",
    detail: "确认 18443 仍由当前 socat 正式链路使用，且不会被新线路覆盖。",
  },
  {
    label: "gost 8443 回退链路检查",
    scope: "未来远程只读",
    detail: "确认 8443 仍由 gost 回退链路保留，且不会让 socat 接管 8443。",
  },
  {
    label: "gost 服务 / 进程状态",
    scope: "未来远程只读",
    detail: "只读查看 gost 服务和进程状态；不执行 start / stop / restart。",
  },
  {
    label: "socat 服务 / 进程状态",
    scope: "未来远程只读",
    detail: "只读查看 socat 服务和进程状态；不修改配置，不接管 8443。",
  },
  {
    label: "中转到落地 TCP 连通性",
    scope: "未来远程只读",
    detail: "确认中转服务器到落地 VPS 目标端口可达；本阶段不执行 nc/curl。",
  },
  {
    label: "服务器防火墙状态",
    scope: "未来远程只读",
    detail: "只读查看服务器防火墙状态；不新增、删除或修改规则。",
  },
  {
    label: "任务记录和本地 health",
    scope: "本地检查",
    detail: "确认本地 health 正常，并确认没有 pending / running 任务。",
  },
  {
    label: "云侧和服务器防火墙确认",
    scope: "本地人工确认",
    detail: "确认云安全组、云防火墙、服务器防火墙均放行计划 TCP 端口。",
  },
];

function displayValue(value: string | number | null | undefined) {
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

function formatTime(value: string | null | undefined) {
  if (!value) {
    return "暂无";
  }
  return new Date(value).toLocaleString();
}

function workerCommandTypeLabel(commandType: string) {
  const labels: Record<string, string> = {
    ping: "Ping",
    collect_status: "状态采集",
    service_status: "服务状态",
    transit_readonly_preflight: "中转只读预检",
  };
  return labels[commandType] ?? commandType;
}

function workerCommandStatusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: "等待中",
    claimed: "已领取",
    running: "执行中",
    succeeded: "成功",
    failed: "失败",
    expired: "已过期",
    cancelled: "已取消",
  };
  return labels[status] ?? status;
}

function objectValue(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function stringValue(record: Record<string, unknown> | null, key: string) {
  const value = record?.[key];
  return typeof value === "string" && value ? value : "-";
}

function scalarValue(record: Record<string, unknown> | null, key: string) {
  const value = record?.[key];
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "-";
}

function maskLink(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  if (value.length <= 44) {
    return value;
  }
  return `${value.slice(0, 24)}...${value.slice(-12)}`;
}

async function copyTextWithFallback(text: string, textArea: HTMLTextAreaElement | null) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall back to selecting the command textarea below.
  }

  try {
    if (!textArea) {
      return false;
    }
    textArea.focus();
    textArea.select();
    textArea.setSelectionRange(0, text.length);
    return document.execCommand("copy");
  } catch {
    return false;
  }
}

function parseListenPortInput(value: string) {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 65535 ? parsed : null;
}

function listenPortValidationMessage(value: string) {
  const trimmed = value.trim();
  const parsed = parseListenPortInput(trimmed);
  if (parsed === null) {
    return "监听端口必须是 1-65535 之间的整数。";
  }
  const normalizedPort = String(parsed);
  if (PROTECTED_LISTEN_PORTS.has(normalizedPort)) {
    return PROTECTED_LISTEN_PORT_MESSAGES[normalizedPort] ?? "该端口受保护，不能用于新转发。";
  }
  return null;
}

function redactString(value: string) {
  if (privateKeyPattern.test(value)) {
    return "[redacted private key]";
  }
  if (linkPattern.test(value)) {
    const protocol = value.match(linkPattern)?.[1] ?? "node";
    return `[redacted ${protocol} link]`;
  }
  if (secretKeyPattern.test(value)) {
    return "[redacted sensitive text]";
  }
  if (value.length > 1800) {
    return `${value.slice(0, 1400)}... [truncated]`;
  }
  return value;
}

function resultStrings(result: Record<string, unknown> | null, key: string) {
  const value = result?.[key];
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function diagnosticItemSpecs(task: TaskData | null): DiagnosticItemSpec[] {
  if (task?.result_data?.["classification"] === "restart_socat_route") {
    return [
      {
        key: "restart_result",
        label: "重启结果",
        purpose: "确认受控重启命令是否成功返回。",
        failureMeaning: "重启命令失败或未返回成功状态。",
        nextAction: "不要连续重试；先查看任务记录并确认是否需要人工介入。",
      },
      {
        key: "service_status",
        label: "systemd 状态检查",
        purpose: "确认转发服务在 systemd 中的状态。",
        failureMeaning: "服务可能未处于 active 状态，或服务文件/名称不符合预期。",
        nextAction: "查看任务记录；真正远程复核需要 Workbuddy 或单独授权阶段。",
      },
      {
        key: "listen_check",
        label: "监听端口检查",
        purpose: "确认中转机正在监听该线路的监听端口。",
        failureMeaning: "ss 没有监听，转发服务可能未启动或已经退出。",
        nextAction: "优先检查服务状态；如本地 nc timeout，同步检查云安全组、云防火墙和服务器防火墙。",
      },
      {
        key: "target_connectivity",
        label: "中转到落地连通性",
        purpose: "确认中转机可以连到落地目标 host:port。",
        failureMeaning: "中转服务器到落地 VPS 不通，或目标服务不可达。",
        nextAction: "检查落地节点服务、目标端口和中转机出口连通性。",
      },
    ];
  }

  return [
    {
      key: "listen_check",
      label: "监听端口检查",
      purpose: "确认中转机正在监听该线路的监听端口。",
      failureMeaning: "ss 没有监听，转发服务可能未启动、已退出，或端口被其它进程占用。",
      nextAction: "查看 systemd 状态和进程检查；如外部访问 timeout，同步检查云安全组、云防火墙和服务器防火墙。",
    },
    {
      key: "process_check",
      label: "转发进程检查",
      purpose: "确认 gost 或 socat 进程存在。",
      failureMeaning: "转发进程不存在，服务可能未启动或已异常退出。",
      nextAction: "查看服务状态和任务记录；真正远程复核需要 Workbuddy 或单独授权阶段。",
    },
    {
      key: "target_connectivity",
      label: "中转到落地连通性",
      purpose: "确认中转机可以连到落地目标 host:port。",
      failureMeaning: "中转服务器到落地 VPS 不通，或目标服务不可达。",
      nextAction: "检查落地节点服务、目标端口和中转机出口连通性。",
    },
    {
      key: "service_status",
      label: "systemd 状态检查",
      purpose: "确认转发服务在 systemd 中的状态。",
      failureMeaning: "服务可能未处于 active 状态，或服务文件/名称不符合预期。",
      nextAction: "查看任务记录；不要直接停止、重启或替换服务，除非进入授权阶段。",
    },
  ];
}

function checkStatus(check: Record<string, unknown> | null) {
  if (!check) {
    return { className: "warn", label: "未返回" };
  }
  return check["ok"] === true ? { className: "ok", label: "通过" } : { className: "bad", label: "失败" };
}

function preflightStatusClass(status: string | null | undefined, ready?: boolean) {
  if (ready || status === "ready") {
    return "ok";
  }
  if (status === "no_go") {
    return "warn";
  }
  return "bad";
}

function preflightCheckClass(check: ReadonlyPreflightCheckItem) {
  if (check.passed) {
    return "ok";
  }
  if (check.id.startsWith("future_") || check.status === "skipped") {
    return "warn";
  }
  return "bad";
}

function preflightCheckStatusLabel(check: ReadonlyPreflightCheckItem) {
  if (check.id.startsWith("future_") || check.status === "skipped") {
    return "未来检查 / 本阶段不执行";
  }
  const labels: Record<string, string> = {
    ready: "就绪",
    no_go: "不通过",
    blocked: "已阻止",
    passed: "通过",
    failed: "失败",
    skipped: "已跳过",
  };
  return labels[check.status] ?? check.status;
}

function preflightPlanStatusLabel(status: string | null | undefined, ready?: boolean) {
  if (ready || status === "ready") {
    return "就绪";
  }
  if (status === "no_go") {
    return "不通过";
  }
  if (status === "blocked") {
    return "已阻止";
  }
  return status ?? "未知";
}

function booleanLabel(value: boolean) {
  return value ? "是" : "否";
}

function routeStatusLabel(status: string) {
  const labels: Record<string, string> = {
    active: "已启用",
    disabled: "已停用",
    deleted: "已删除",
    pending: "等待中",
    failed: "失败",
    unknown: "未知",
  };
  return labels[status] ?? status;
}

function routeStatusClass(status: string) {
  if (status === "active") {
    return "ok";
  }
  if (status === "disabled" || status === "unknown") {
    return "muted";
  }
  return "bad";
}

function transitResourceStatusLabel(resource: TransitResourceData) {
  const displayStatus = resource.display_status || resource.status;
  const labels: Record<string, string> = {
    pending_worker: "待接入",
    online: "在线",
    offline: "离线",
    unchecked: "未检测",
    disabled: "已停用",
    active: "未检测",
  };
  if (labels[displayStatus]) {
    return labels[displayStatus];
  }
  if (resource.status === "disabled") {
    return "已停用";
  }
  return "未检测";
}

function transitResourceStatusClass(resource: TransitResourceData) {
  const displayStatus = resource.display_status || resource.status;
  if (displayStatus === "online" || displayStatus === "worker_online") {
    return "ok";
  }
  if (displayStatus === "offline" || displayStatus === "worker_offline") {
    return "bad";
  }
  return resource.status === "disabled" ? "muted" : "warn";
}

function isPlanningSelectableTransitResource(resource: TransitResourceData) {
  if (resource.resource_type !== "server") {
    return false;
  }
  const displayStatus = resource.display_status || resource.status;
  return (
    resource.status === "active" ||
    resource.worker_online === true ||
    displayStatus === "online" ||
    displayStatus === "worker_online"
  );
}

function transitHostLabel(resource: TransitResourceData) {
  return resource.entry_host || resource.ssh_host || "-";
}

function transitSshPortLabel(resource: TransitResourceData) {
  const port = resource.ssh_port ?? resource.entry_port;
  return port ? `SSH ${port}` : "-";
}

function formFromTransitResource(resource: TransitResourceData): TransitServerFormState {
  return {
    name: resource.name ?? "",
    entryHost: resource.entry_host ?? resource.ssh_host ?? "",
    sshPort: resource.ssh_port ? String(resource.ssh_port) : "22",
    sshUsername: resource.ssh_username ?? "root",
    provider: resource.provider ?? "",
    notes: resource.notes ?? "",
  };
}

function buildTransitResourcePayloadFromForm(
  form: TransitServerFormState,
  selectedResource: TransitResourceData | null,
): { payload: TransitResourcePayload | null; error: string | null } {
  const name = form.name.trim();
  const entryHost = form.entryHost.trim();
  const sshUsername = form.sshUsername.trim();
  const sshPort = parseListenPortInput(form.sshPort);

  if (!name) {
    return { payload: null, error: "请填写中转服务器名称。" };
  }
  if (!entryHost) {
    return { payload: null, error: "请填写中转服务器公网 IP。" };
  }
  if (sshPort === null) {
    return { payload: null, error: "SSH 端口必须是 1-65535 之间的整数。" };
  }
  if (!sshUsername) {
    return { payload: null, error: "请填写 SSH 用户名。" };
  }

  return {
    error: null,
    payload: {
      name,
      resource_type: "server",
      provider: form.provider.trim() || null,
      entry_host: entryHost,
      entry_port: null,
      entry_region: null,
      exit_region: null,
      bandwidth_mbps: null,
      traffic_limit_gb: null,
      traffic_used_gb: null,
      protocol_hint: "tcp",
      has_ssh: true,
      ssh_host: entryHost,
      ssh_port: sshPort,
      ssh_username: sshUsername,
      status: selectedResource?.status ?? "active",
      expires_at: null,
      notes: form.notes.trim() || null,
    },
  };
}

function landingNodeKey(node: NodeData) {
  return node.vps_id || node.vps_ip || node.id;
}

function landingNodeLabel(node: NodeData) {
  return node.vps_ip || node.vps_id || "未知落地服务器";
}

function taskStatusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: "等待中",
    running: "执行中",
    success: "成功",
    completed: "成功",
    failed: "失败",
    cancelled: "已取消",
    timeout: "超时",
  };
  return labels[status] ?? status;
}

function diagnosticOutcome(task: TaskData) {
  if (task.status === "failed") {
    return task.error_message ? redactString(task.error_message) : "诊断任务失败，请查看任务记录。";
  }
  if (task.result_data?.["passed"] === true) {
    return "诊断通过：监听、进程、服务状态和中转到落地连通性未发现异常。";
  }
  if (task.result_data?.["passed"] === false) {
    return "诊断发现问题：请按失败项的下一步建议排查。";
  }
  return "诊断任务仍在进行或尚未返回完整结果。";
}

export function TransitServersPanel() {
  const workerInstallCommandRef = useRef<HTMLTextAreaElement | null>(null);
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [loadingResources, setLoadingResources] = useState(true);
  const [message, setMessage] = useState("中转服务器只代表本地资源记录；真实转发关系请到“中转链路”页面配置。");
  const [modalMode, setModalMode] = useState<"add" | "edit" | "regenerate" | null>(null);
  const [selectedTransitResource, setSelectedTransitResource] = useState<TransitResourceData | null>(null);
  const [transitServerForm, setTransitServerForm] = useState<TransitServerFormState>(emptyTransitServerForm);
  const [workerBootstrapForm, setWorkerBootstrapForm] = useState<WorkerBootstrapFormState>(emptyWorkerBootstrapForm);
  const [workerTokenResult, setWorkerTokenResult] = useState<WorkerTokenCreateResult | null>(null);
  const [workerCommandsByWorkerId, setWorkerCommandsByWorkerId] = useState<Record<string, WorkerCommandData[]>>({});
  const [latestWorkerCommandByResourceId, setLatestWorkerCommandByResourceId] = useState<Record<string, WorkerCommandData>>({});
  const [workerCommandLoadingId, setWorkerCommandLoadingId] = useState<string | null>(null);
  const [submittingTransitResource, setSubmittingTransitResource] = useState(false);
  const [regeneratingResourceId, setRegeneratingResourceId] = useState<string | null>(null);

  async function ensureCsrfToken() {
    const csrf = await apiFetch<CsrfResult>("/api/auth/csrf");
    if (!csrf.success) {
      throw new Error(csrf.message);
    }
    return csrf.data.csrf_token;
  }

  async function loadTransitServers() {
    setLoadingResources(true);
    const resourceResult = await apiFetch<TransitResourceListResult>("/api/transit-resources?resource_type=server");
    if (!resourceResult.success) {
      setMessage(resourceResult.message);
      setLoadingResources(false);
      return;
    }
    const serverResources = resourceResult.data.resources.filter((resource) => resource.resource_type === "server");
    setResources(serverResources);
    await Promise.all(
      serverResources
        .filter((resource) => resource.worker_id)
        .map((resource) => loadWorkerCommands(resource.worker_id as string, resource.id)),
    );
    setLoadingResources(false);
  }

  useEffect(() => {
    void loadTransitServers();
  }, []);

  function updateTransitServerForm<K extends keyof TransitServerFormState>(
    key: K,
    value: TransitServerFormState[K],
  ) {
    setTransitServerForm((current) => ({ ...current, [key]: value }));
  }

  function closeTransitServerModal() {
    setModalMode(null);
    setSelectedTransitResource(null);
    setTransitServerForm(emptyTransitServerForm);
    setWorkerBootstrapForm(emptyWorkerBootstrapForm);
    setWorkerTokenResult(null);
  }

  function openAddTransitServer() {
    setSelectedTransitResource(null);
    setTransitServerForm(emptyTransitServerForm);
    setWorkerBootstrapForm(emptyWorkerBootstrapForm);
    setWorkerTokenResult(null);
    setModalMode("add");
  }

  function openEditTransitServer(resource: TransitResourceData) {
    setSelectedTransitResource(resource);
    setTransitServerForm(formFromTransitResource(resource));
    setModalMode("edit");
  }

  function canRegenerateWorkerBootstrap(resource: TransitResourceData) {
    const isPendingWorker = resource.status === "pending_worker" || resource.display_status === "pending_worker";
    return resource.connection_mode === "worker" && isPendingWorker && !resource.worker_online;
  }

  async function submitTransitServer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const { payload, error } = buildTransitResourcePayloadFromForm(transitServerForm, selectedTransitResource);
    if (!payload) {
      setMessage(error ?? "请检查中转服务器表单。");
      return;
    }
    try {
      setSubmittingTransitResource(true);
      const csrfToken = await ensureCsrfToken();
      const isEdit = modalMode === "edit" && selectedTransitResource;
      const result = await apiFetch<TransitResourceData>(
        isEdit ? `/api/transit-resources/${selectedTransitResource.id}` : "/api/transit-resources",
        {
          body: JSON.stringify(payload),
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrfToken,
          },
          method: isEdit ? "PATCH" : "POST",
        },
      );
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setMessage(isEdit ? "中转服务器记录已更新。" : "中转服务器记录已添加。");
      closeTransitServerModal();
      await loadTransitServers();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存中转服务器记录失败。");
    } finally {
      setSubmittingTransitResource(false);
    }
  }

  async function generateWorkerInstallCommand(role: WorkerRole) {
    const name = workerBootstrapForm.name.trim();
    const ip = workerBootstrapForm.ip.trim();
    const expiresInMinutes = Number(workerBootstrapForm.expiresInMinutes);
    if (!name) {
      setMessage("请填写中转服务器名称。");
      return;
    }
    if (!ip) {
      setMessage("请填写中转服务器 IP。");
      return;
    }
    if (!Number.isInteger(expiresInMinutes) || expiresInMinutes < 1 || expiresInMinutes > 10080) {
      setMessage("过期时间必须是 1 到 10080 分钟之间的整数。");
      return;
    }
    try {
      setSubmittingTransitResource(true);
      setWorkerTokenResult(null);
      setMessage("正在保存中转服务器并生成一次性 Worker 安装命令。");
      const csrfToken = await ensureCsrfToken();
      const result = await createTransitWorkerBootstrap(
        {
          name,
          ip,
          expires_in_minutes: expiresInMinutes,
        },
        csrfToken,
      );
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setWorkerTokenResult(result.data.token);
      setMessage("中转服务器已保存为待接入，Worker 安装命令已生成。请在 VPS 上先确认能访问主控地址。");
      await loadTransitServers();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "生成 Worker 安装命令失败。");
    } finally {
      setSubmittingTransitResource(false);
    }
  }

  async function regenerateWorkerInstallCommand(resource: TransitResourceData) {
    if (!canRegenerateWorkerBootstrap(resource)) {
      setMessage("只有 pending_worker 且 Worker 未在线的中转服务器可以重新生成安装命令。");
      return;
    }
    try {
      setRegeneratingResourceId(resource.id);
      setWorkerTokenResult(null);
      setSelectedTransitResource(resource);
      setMessage("正在为已有中转服务器重新生成一次性 Worker 安装命令。");
      const csrfToken = await ensureCsrfToken();
      const result = await regenerateTransitWorkerBootstrap(resource.id, { expires_in_minutes: 60 }, csrfToken);
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setSelectedTransitResource(result.data.resource);
      setWorkerTokenResult(result.data.token);
      setModalMode("regenerate");
      setMessage("新的 Worker 安装命令已生成。命令只显示一次，请立即复制并妥善保存。");
      await loadTransitServers();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "重新生成 Worker 安装命令失败。");
    } finally {
      setRegeneratingResourceId(null);
    }
  }

  async function copyInstallCommand() {
    if (!workerTokenResult?.install_command) {
      setMessage("请先生成安装命令。");
      return;
    }
    const copied = await copyTextWithFallback(workerTokenResult.install_command, workerInstallCommandRef.current);
    if (!copied) {
      setMessage("复制失败，请点击命令框后按 Ctrl+A / Ctrl+C，Mac 使用 Command+A / Command+C。");
      return;
    }
    setMessage("已复制安装命令。请勿把该命令写入文档、日志或 Git。");
  }

  async function loadWorkerCommands(workerId: string, resourceId?: string) {
    const result = await listWorkerCommands(workerId);
    if (!result.success) {
      setMessage(`${result.error_code}: ${result.message}`);
      return;
    }
    setWorkerCommandsByWorkerId((current) => ({ ...current, [workerId]: result.data.commands }));
    if (resourceId && result.data.commands[0]) {
      setLatestWorkerCommandByResourceId((current) => ({ ...current, [resourceId]: result.data.commands[0] }));
    }
  }

  async function runWorkerCheck(resource: TransitResourceData) {
    if (!resource.worker_id || !resource.worker_online) {
      setMessage("Worker 未在线，不能创建 Worker 检查命令。");
      return;
    }
    setWorkerCommandLoadingId(resource.worker_id);
    setMessage("正在创建 Worker 状态检查命令。该命令只会由 Worker 轮询执行，不会 SSH。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await createWorkerCommand(
        resource.worker_id,
        { command_type: "collect_status", payload: null, server_id: resource.id, server_type: "transit" },
        csrfToken,
      );
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setLatestWorkerCommandByResourceId((current) => ({ ...current, [resource.id]: result.data.command }));
      const targetVersion = result.data.target_worker_version || "未知版本";
      const targetNote = result.data.target_worker_changed ? "已自动切换到最新支持命令的 Worker。" : "";
      setMessage(
        `Worker 检查命令已创建：${result.data.command.id}；目标 Worker：${result.data.target_worker_id} / ${targetVersion}。${targetNote}`,
      );
      await loadWorkerCommands(result.data.target_worker_id, resource.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "创建 Worker 检查命令失败。");
    } finally {
      setWorkerCommandLoadingId(null);
    }
  }

  function latestWorkerCommandForResource(resource: TransitResourceData) {
    return latestWorkerCommandByResourceId[resource.id] ?? (resource.worker_id ? workerCommandsByWorkerId[resource.worker_id]?.[0] : undefined);
  }

  function renderRecentWorkerCommand(command: WorkerCommandData | undefined) {
    if (!command) {
      return null;
    }
    return (
      <span className="worker-command-status">
        最近命令：
        {workerCommandTypeLabel(command.command_type)} / {workerCommandStatusLabel(command.status)}
        {command.target_worker_version ? ` / Worker ${command.target_worker_version}` : ""}
        {command.result_summary ? ` / ${command.result_summary}` : ""}
        {command.error_message ? ` / ${command.error_message}` : ""}
      </span>
    );
  }

  function renderTransitServerModal() {
    if (!modalMode) {
      return null;
    }
    const title =
      modalMode === "edit"
        ? "编辑中转服务器"
        : modalMode === "regenerate"
          ? "重新生成 Worker 安装命令"
          : "添加中转服务器";
    return (
      <div className="modal-backdrop" role="presentation" onClick={closeTransitServerModal}>
        <div className="modal-card transit-server-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
          <div className="status-row">
            <div>
              <h3>{title}</h3>
              <p className="message">
                {modalMode === "add"
                  ? "默认使用 Worker 安装命令接入；仅在点击生成按钮时创建一次性 token，不会执行 SSH。"
                  : modalMode === "regenerate"
                    ? "仅为已有 pending_worker 中转服务器生成新的绑定安装命令；不会执行 SSH、不会安装 Worker、不会创建中转链路。"
                    : "只保存本地资源记录；不会安装 Worker、不会生成 token、不会执行 SSH 或远程命令。"}
              </p>
            </div>
            <button className="secondary compact" type="button" onClick={closeTransitServerModal}>
              关闭
            </button>
          </div>
          {modalMode === "add"
            ? renderWorkerBootstrapForm("transit")
            : modalMode === "regenerate"
              ? renderRegeneratedWorkerCommand()
              : renderTransitResourceForm()}
        </div>
      </div>
    );
  }

  function renderWorkerCommandPanel() {
    if (!workerTokenResult) {
      return null;
    }
    return (
      <div className="worker-command-panel wide-field">
        <div className="worker-command-meta">
          <span>role：{workerTokenResult.role}</span>
          <span>masked token：{workerTokenResult.masked_token}</span>
          <span>过期时间：{formatTime(workerTokenResult.expires_at)}</span>
          <span>状态：{workerTokenResult.status}</span>
        </div>
        <label>
          安装命令
          <textarea
            ref={workerInstallCommandRef}
            className="worker-install-command"
            readOnly
            value={workerTokenResult.install_command}
          />
        </label>
        <div className="modal-actions">
          <button className="secondary" type="button" onClick={() => void copyInstallCommand()}>
            复制命令
          </button>
        </div>
        <p className="message">
          命令只显示一次，关闭后无法再次查看。请在 VPS 上先确认能访问主控地址；不要把命令写入聊天、Git、README、PR、日志或截图。
        </p>
      </div>
    );
  }

  function renderRegeneratedWorkerCommand() {
    return (
      <div className="form transit-server-form worker-bootstrap-form">
        <div className="worker-bootstrap-intro wide-field">
          <strong>{selectedTransitResource?.name ?? "中转服务器"} 的新安装命令</strong>
          <span>已为这条 pending_worker 中转服务器生成新的 role = transit 一次性安装命令。</span>
          <span>同一中转服务器下旧的 active token 已在后端失效，旧命令不再可用。</span>
        </div>
        <div className="warning-box wide-field">
          <strong>敏感命令提醒</strong>
          <span>完整安装命令包含一次性 token，只在本次响应中显示。</span>
          <span>不要写入聊天、Git、README、PR、日志或截图。</span>
          <span>本按钮只重新生成命令，不执行 SSH、不执行 Worker 命令、不安装 Worker、不创建中转链路。</span>
        </div>
        {renderWorkerCommandPanel()}
        <div className="modal-actions wide-field">
          <button className="secondary" type="button" onClick={closeTransitServerModal}>
            关闭
          </button>
        </div>
      </div>
    );
  }

  function renderWorkerBootstrapForm(role: WorkerRole) {
    return (
      <div className="form transit-server-form worker-bootstrap-form">
        <div className="worker-bootstrap-intro wide-field">
          <strong>接入方式：Worker 安装命令</strong>
          <span>
            中转服务器使用 role = transit。点击生成后会先保存中转服务器记录，再生成绑定该记录的一次性安装命令。
          </span>
        </div>
        <label>
          中转服务器名称
          <input
            value={workerBootstrapForm.name}
            onChange={(event) => setWorkerBootstrapForm({ ...workerBootstrapForm, name: event.target.value })}
            placeholder="例如：香港中转服务器"
          />
        </label>
        <label>
          中转服务器 IP
          <input
            value={workerBootstrapForm.ip}
            onChange={(event) => setWorkerBootstrapForm({ ...workerBootstrapForm, ip: event.target.value })}
            placeholder="公网 IPv4"
          />
        </label>
        <label>
          过期时间，分钟
          <input
            inputMode="numeric"
            value={workerBootstrapForm.expiresInMinutes}
            onChange={(event) => setWorkerBootstrapForm({ ...workerBootstrapForm, expiresInMinutes: event.target.value })}
            placeholder="60"
          />
        </label>
        <div className="warning-box wide-field">
          <strong>Worker 第一版安装说明</strong>
          <span>当前安装命令会安装真实 liveline-worker，并写入 systemd 服务。</span>
          <span>Worker 第一版只做注册、心跳和基础状态上报，不创建中转链路、不修改 socat/gost、不新增监听端口。</span>
          <span>生成命令必须先配置 PUBLIC_CONSOLE_URL；主控公网地址未配置时，远程 VPS 无法通过 localhost 访问安装脚本。</span>
          <span>安装完成后可使用 journalctl -u liveline-worker -f 查看日志。</span>
          <span>如果服务器网卡不是 eth0，请根据实际网卡名修改，例如 ens3、ens5、enp1s0。</span>
        </div>
        <div className="modal-actions wide-field">
          <button disabled={submittingTransitResource} type="button" onClick={() => void generateWorkerInstallCommand(role)}>
            {submittingTransitResource ? "生成中..." : "保存中转服务器并生成安装命令"}
          </button>
          <button className="secondary" type="button" onClick={closeTransitServerModal}>
            取消
          </button>
        </div>
        {workerTokenResult ? renderWorkerCommandPanel() : (
          <p className="message wide-field">点击“生成安装命令”后，这里会显示一次性 curl | bash 命令和 token 过期时间。</p>
        )}
      </div>
    );
  }

  function renderTransitResourceForm() {
    return (
      <form className="form transit-server-form" onSubmit={(event) => void submitTransitServer(event)}>
            <label>
              名称
              <input
                value={transitServerForm.name}
                onChange={(event) => updateTransitServerForm("name", event.target.value)}
                placeholder="例如：香港中转服务器"
              />
            </label>
            <label>
              IP 地址
              <input
                value={transitServerForm.entryHost}
                onChange={(event) => updateTransitServerForm("entryHost", event.target.value)}
                placeholder="仅填写主机地址，不写密码或密钥"
              />
            </label>
            <label>
              SSH 端口
              <input
                value={transitServerForm.sshPort}
                onChange={(event) => updateTransitServerForm("sshPort", event.target.value)}
                placeholder="22"
              />
            </label>
            <label>
              SSH 用户名
              <input
                value={transitServerForm.sshUsername}
                onChange={(event) => updateTransitServerForm("sshUsername", event.target.value)}
                placeholder="root"
              />
            </label>
            <label>
              服务商 / 区域
              <input
                value={transitServerForm.provider}
                onChange={(event) => updateTransitServerForm("provider", event.target.value)}
                placeholder="可选"
              />
            </label>
            <label className="wide-field">
              备注
              <textarea
                value={transitServerForm.notes}
                onChange={(event) => updateTransitServerForm("notes", event.target.value)}
                placeholder="不要填写真实密码、SSH Key、token 或完整节点链接。"
              />
            </label>
            <div className="warning-box wide-field">
              <strong>Worker 接入后续实现</strong>
              <span>curl | bash Worker 接入、token 生成、远程检测和远程清理将在后续 Worker / API 阶段单独审批。</span>
              <span>本阶段只维护本地中转服务器资源记录。</span>
            </div>
            <div className="modal-actions wide-field">
              <button className="secondary" type="button" onClick={closeTransitServerModal}>
                取消
              </button>
              <button type="submit" disabled={submittingTransitResource}>
                {submittingTransitResource ? "保存中" : "保存记录"}
              </button>
            </div>
          </form>
    );
  }

  return (
    <section className="panel wide server-management-panel transit-server-management-panel">
      <div className="server-panel-header">
        <div>
          <h2>中转服务器</h2>
          <p>管理中转服务器资源。资源记录不等于真实线路，转发关系请到“中转链路”页面配置。</p>
        </div>
        <button type="button" onClick={openAddTransitServer}>
          添加中转服务器
        </button>
      </div>

      <CollapsibleWarning title="查看中转服务器安全说明" wide>
        <span>中转服务器只代表可用于转发的服务器资源记录，不等于已经创建真实可用线路。</span>
        <span>本页面不会自动生成 Worker token；只有点击“生成安装命令”才会创建一次性 token。</span>
        <span>本页面不安装真实 Worker，不执行 SSH / 远程命令，不新增监听端口。</span>
        <span>真实转发关系请在“中转链路”页面规划；真正远程创建必须进入后续 Worker / 授权阶段。</span>
        <span>新增或变更监听端口后，仍必须同步检查云服务器安全组 / 云防火墙 / 服务器防火墙是否放行对应 TCP 端口。</span>
      </CollapsibleWarning>

      <div className="server-table">
        <div className="server-table-row server-table-head">
          <span>名称</span>
          <span>IP 地址</span>
          <span>端口</span>
          <span>状态</span>
          <span>操作</span>
        </div>
        {loadingResources ? (
          <div className="server-table-empty">正在加载中转服务器记录...</div>
        ) : resources.length === 0 ? (
          <div className="server-table-empty">
            暂无中转服务器记录。点击“添加中转服务器”可先创建本地资源记录；这不会安装 Worker，也不会执行 SSH。
          </div>
        ) : (
          resources.map((resource) => (
            <div className="server-table-group" key={resource.id}>
              <div className="server-table-row transit-server-row">
                <div>
                  <strong>{resource.name}</strong>
                  <span className="node-meta-line">资源类型：{resource.resource_type}</span>
                </div>
                <span>{transitHostLabel(resource)}</span>
                <span>{transitSshPortLabel(resource)}</span>
                <div>
                  <span className={`pill ${transitResourceStatusClass(resource)}`}>
                    {transitResourceStatusLabel(resource)}
                  </span>
                  <span className="node-meta-line">
                    {resource.connection_mode === "worker"
                      ? `Worker：${resource.worker_status ? transitResourceStatusLabel(resource) : "未注册"} / 最后心跳 ${formatTime(
                          resource.worker_last_heartbeat_at,
                        )}`
                      : "状态来源：本地资源状态 / 未做 SSH 检测"}
                  </span>
                  {renderRecentWorkerCommand(latestWorkerCommandForResource(resource))}
                </div>
                <div className="server-actions">
                  {canRegenerateWorkerBootstrap(resource) ? (
                    <button
                      className="secondary compact"
                      disabled={regeneratingResourceId === resource.id}
                      type="button"
                      onClick={() => void regenerateWorkerInstallCommand(resource)}
                    >
                      {regeneratingResourceId === resource.id ? "生成中..." : "重新生成安装命令"}
                    </button>
                  ) : null}
                  {resource.worker_id ? (
                    <button
                      className="secondary compact"
                      disabled={!resource.worker_online || workerCommandLoadingId === resource.worker_id}
                      title={!resource.worker_online ? "Worker 未在线，不能创建检查命令" : "创建只读 Worker 检查命令"}
                      type="button"
                      onClick={() => void runWorkerCheck(resource)}
                    >
                      Worker 检查
                    </button>
                  ) : null}
                  <button
                    className="secondary compact"
                    type="button"
                    onClick={() => setMessage("重新检测需要后续 Worker / API 阶段开放；本阶段不执行 SSH 或远程命令。")}
                  >
                    重新检测
                  </button>
                  <button className="secondary compact" type="button" onClick={() => openEditTransitServer(resource)}>
                    编辑
                  </button>
                  <button
                    className="danger compact"
                    type="button"
                    onClick={() =>
                      setMessage(
                        "删除中转服务器需要后续 Worker 先完成远程 socat / gost 清理；本阶段不删除系统记录，也不执行远程清理。",
                      )
                    }
                  >
                    删除
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="server-panel-footer">
        <button className="secondary" type="button" onClick={() => void loadTransitServers()}>
          刷新中转服务器
        </button>
        <span>{message}</span>
      </div>
      {renderTransitServerModal()}
    </section>
  );
}

export function TransitRoutesPanel() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const diagnosticFileInputRef = useRef<HTMLInputElement | null>(null);
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [routes, setRoutes] = useState<TransitRouteData[]>([]);
  const [loadingResources, setLoadingResources] = useState(true);
  const [selectedResourceId, setSelectedResourceId] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [forwardingMethod, setForwardingMethod] = useState<ForwardingMethod>("gost");
  const [routeName, setRouteName] = useState("hk-gost-new-route");
  const [listenPort, setListenPort] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [privateKeyText, setPrivateKeyText] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [task, setTask] = useState<TaskData | null>(null);
  const [logs, setLogs] = useState<TaskLogData[]>([]);
  const [message, setMessage] = useState("Stage 3.3.3 只创建一条 gost TCP 转发规则。");
  const [copied, setCopied] = useState(false);
  const [copiedRouteId, setCopiedRouteId] = useState<string | null>(null);
  const [copiedSocatCandidateRouteId, setCopiedSocatCandidateRouteId] = useState<string | null>(null);
  const [copiedDiagnosticsRouteId, setCopiedDiagnosticsRouteId] = useState<string | null>(null);
  const [diagnosticPrivateKeyText, setDiagnosticPrivateKeyText] = useState("");
  const [diagnosticPassphrase, setDiagnosticPassphrase] = useState("");
  const [diagnosticTask, setDiagnosticTask] = useState<TaskData | null>(null);
  const [diagnosticLogs, setDiagnosticLogs] = useState<TaskLogData[]>([]);
  const [diagnosticRouteId, setDiagnosticRouteId] = useState<string | null>(null);
  const [diagnosticMessage, setDiagnosticMessage] = useState("只读诊断不会停止、删除、重启或创建线路。");
  const [planResourceId, setPlanResourceId] = useState("");
  const [planNodeId, setPlanNodeId] = useState("");
  const [planListenPort, setPlanListenPort] = useState("");
  const [planTargetPort, setPlanTargetPort] = useState("");
  const [planPurpose, setPlanPurpose] = useState("");
  const [planCloudSecurityGroupConfirmed, setPlanCloudSecurityGroupConfirmed] = useState(false);
  const [planCloudFirewallConfirmed, setPlanCloudFirewallConfirmed] = useState(false);
  const [planServerFirewallConfirmed, setPlanServerFirewallConfirmed] = useState(false);
  const [planLocalBackupConfirmed, setPlanLocalBackupConfirmed] = useState(false);
  const [planSummaryCopied, setPlanSummaryCopied] = useState(false);
  const [preflightHealthConfirmed, setPreflightHealthConfirmed] = useState(false);
  const [preflightBoundaryAcknowledged, setPreflightBoundaryAcknowledged] = useState(false);
  const [preflightWorkbuddyBoundaryConfirmed, setPreflightWorkbuddyBoundaryConfirmed] = useState(false);
  const [preflightSummaryCopied, setPreflightSummaryCopied] = useState(false);
  const [readonlyPreflightPlan, setReadonlyPreflightPlan] = useState<ReadonlyPreflightPlanResponse | null>(null);
  const [readonlyPreflightApiMessage, setReadonlyPreflightApiMessage] = useState("");
  const [readonlyPreflightLoading, setReadonlyPreflightLoading] = useState(false);
  const [remotePreflightCommand, setRemotePreflightCommand] = useState<WorkerCommandData | null>(null);
  const [remotePreflightMessage, setRemotePreflightMessage] = useState("");
  const [remotePreflightLoading, setRemotePreflightLoading] = useState(false);
  const [transitModalMode, setTransitModalMode] = useState<TransitModalMode>(null);
  const [selectedTransitResource, setSelectedTransitResource] = useState<TransitResourceData | null>(null);
  const [selectedTransitRoute, setSelectedTransitRoute] = useState<TransitRouteData | null>(null);
  const [transitServerForm, setTransitServerForm] = useState<TransitServerFormState>(emptyTransitServerForm);
  const [transitRouteDraft, setTransitRouteDraft] = useState<TransitRouteDraftState>(emptyTransitRouteDraft);
  const [submittingTransitResource, setSubmittingTransitResource] = useState(false);

  async function ensureCsrfToken() {
    const csrf = await apiFetch<CsrfResult>("/api/auth/csrf");
    if (!csrf.success) {
      throw new Error(csrf.message);
    }
    return csrf.data.csrf_token;
  }

  async function loadData() {
    setLoadingResources(true);
    const [resourceResult, nodeResult, routeResult] = await Promise.all([
      apiFetch<TransitResourceListResult>("/api/transit-resources?resource_type=server"),
      apiFetch<NodeListResult>("/api/nodes"),
      apiFetch<TransitRouteListResult>("/api/transit-routes"),
    ]);

    if (!resourceResult.success) {
      setMessage(resourceResult.message);
      setLoadingResources(false);
      return;
    }
    if (!nodeResult.success) {
      setMessage(nodeResult.message);
      setLoadingResources(false);
      return;
    }
    if (!routeResult.success) {
      setMessage(routeResult.message);
      setLoadingResources(false);
      return;
    }

    const serverResources = resourceResult.data.resources.filter((resource) => resource.resource_type === "server");
    const activeResources = serverResources.filter((resource) => resource.status === "active");
    const planningResources = serverResources.filter(isPlanningSelectableTransitResource);
    const activeNodes = nodeResult.data.nodes.filter((node) => node.status === "active");
    setResources(serverResources);
    setNodes(activeNodes);
    setRoutes(routeResult.data.routes);
    setSelectedResourceId((current) => current || activeResources[0]?.id || "");
    setSelectedNodeId((current) => current || activeNodes[0]?.id || "");
    setPlanResourceId((current) => current || planningResources[0]?.id || "");
    setPlanNodeId((current) => current || activeNodes[0]?.id || "");
    setLoadingResources(false);
  }

  useEffect(() => {
    void loadData();
  }, []);

  useEffect(() => {
    setReadonlyPreflightPlan(null);
    setReadonlyPreflightApiMessage("");
    setRemotePreflightCommand(null);
    setRemotePreflightMessage("");
    setPreflightSummaryCopied(false);
  }, [
    planResourceId,
    planNodeId,
    planListenPort,
    planTargetPort,
    planPurpose,
    planCloudSecurityGroupConfirmed,
    planCloudFirewallConfirmed,
    planServerFirewallConfirmed,
    planLocalBackupConfirmed,
    preflightHealthConfirmed,
    preflightBoundaryAcknowledged,
    preflightWorkbuddyBoundaryConfirmed,
  ]);

  useEffect(() => {
    setConfirm(false);
    setTask(null);
    setLogs([]);
    setCopied(false);
    if (forwardingMethod === "socat") {
      setRouteName("hk-socat-new-test");
      setListenPort("");
      setSelectedResourceId((current) =>
        resources.some((resource) => resource.id === SOCAT_RESOURCE_ID) ? SOCAT_RESOURCE_ID : current,
      );
      setMessage("Stage 3.3.3-fix-b1：只创建 socat 测试转发。");
      return;
    }

    setRouteName("hk-gost-new-route");
    setListenPort("");
    setMessage("Stage 3.3.3 只创建一条 gost TCP 转发规则。");
  }, [forwardingMethod, resources]);

  useEffect(() => {
    if (!task?.id || terminalStatuses.has(task.status)) {
      return;
    }
    const timer = window.setTimeout(() => {
      void loadTask(task.id);
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [task]);

  useEffect(() => {
    if (!diagnosticTask?.id || terminalStatuses.has(diagnosticTask.status)) {
      return;
    }
    const timer = window.setTimeout(() => {
      void loadDiagnosticTask(diagnosticTask.id);
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [diagnosticTask]);

  async function loadTask(taskId: string) {
    const [taskResult, logsResult] = await Promise.all([
      apiFetch<TaskData>(`/api/tasks/${taskId}`),
      apiFetch<{ logs: TaskLogData[] }>(`/api/tasks/${taskId}/logs`),
    ]);

    if (taskResult.success) {
      setTask(taskResult.data);
      const taskMessage = taskResult.data.result_data?.["message"];
      if (typeof taskMessage === "string") {
        setMessage(taskMessage);
      } else if (taskResult.data.error_message) {
        setMessage(taskResult.data.error_message);
      }
      if (terminalStatuses.has(taskResult.data.status)) {
        void loadData();
      }
    } else {
      setMessage(taskResult.message);
    }

    if (logsResult.success) {
      setLogs(logsResult.data.logs);
    }
  }

  async function loadDiagnosticTask(taskId: string) {
    const [taskResult, logsResult] = await Promise.all([
      apiFetch<TaskData>(`/api/tasks/${taskId}`),
      apiFetch<{ logs: TaskLogData[] }>(`/api/tasks/${taskId}/logs`),
    ]);

    if (taskResult.success) {
      setDiagnosticTask(taskResult.data);
      const taskMessage = taskResult.data.result_data?.["message"];
      if (typeof taskMessage === "string") {
        setDiagnosticMessage(taskMessage);
      } else if (taskResult.data.error_message) {
        setDiagnosticMessage(taskResult.data.error_message);
      }
      if (terminalStatuses.has(taskResult.data.status)) {
        void loadData();
      }
    } else {
      setDiagnosticMessage(taskResult.message);
    }

    if (logsResult.success) {
      setDiagnosticLogs(logsResult.data.logs);
    }
  }

  function buildForm() {
    const formData = new FormData();
    formData.append("transit_resource_id", selectedResourceId);
    formData.append("node_id", selectedNodeId);
    formData.append("listen_port", listenPort);
    formData.append("forwarding_method", forwardingMethod);
    formData.append("route_name", routeName);
    formData.append("confirm", confirm ? "true" : "false");
    formData.append("ssh_key_passphrase", passphrase);
    if (privateKeyText.trim()) {
      formData.append("private_key_text", privateKeyText);
    }
    const file = fileInputRef.current?.files?.[0];
    if (file) {
      formData.append("private_key_file", file);
    }
    return formData;
  }

  function buildDiagnosticForm() {
    const formData = new FormData();
    formData.append("ssh_key_passphrase", diagnosticPassphrase);
    if (diagnosticPrivateKeyText.trim()) {
      formData.append("private_key_text", diagnosticPrivateKeyText);
    }
    const file = diagnosticFileInputRef.current?.files?.[0];
    if (file) {
      formData.append("private_key_file", file);
    }
    return formData;
  }

  function clearCredentials() {
    setPrivateKeyText("");
    setPassphrase("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  function clearDiagnosticCredentials() {
    setDiagnosticPrivateKeyText("");
    setDiagnosticPassphrase("");
    if (diagnosticFileInputRef.current) {
      diagnosticFileInputRef.current.value = "";
    }
  }

  function updateListenPort(value: string) {
    setListenPort(value);
    setConfirm(false);
  }

  function updateTransitServerForm<K extends keyof TransitServerFormState>(
    key: K,
    value: TransitServerFormState[K],
  ) {
    setTransitServerForm((current) => ({ ...current, [key]: value }));
  }

  function updateTransitRouteDraft<K extends keyof TransitRouteDraftState>(
    key: K,
    value: TransitRouteDraftState[K],
  ) {
    setTransitRouteDraft((current) => ({ ...current, [key]: value }));
  }

  function closeTransitModal() {
    setTransitModalMode(null);
    setSelectedTransitResource(null);
    setSelectedTransitRoute(null);
    setTransitServerForm(emptyTransitServerForm);
    setTransitRouteDraft(emptyTransitRouteDraft);
  }

  function openAddTransitServer() {
    setTransitServerForm(emptyTransitServerForm);
    setSelectedTransitResource(null);
    setTransitModalMode("addServer");
  }

  function openEditTransitServer(resource: TransitResourceData) {
    setSelectedTransitResource(resource);
    setTransitServerForm(formFromTransitResource(resource));
    setTransitModalMode("editServer");
  }

  function openAddTransitRoute(resource?: TransitResourceData) {
    const planningSelectableServerResources = resources.filter(isPlanningSelectableTransitResource);
    const defaultResource =
      resource && isPlanningSelectableTransitResource(resource)
        ? resource
        : planningSelectableServerResources[0] ?? null;
    const defaultNode = nodes[0] ?? null;
    setSelectedTransitResource(defaultResource);
    setTransitRouteDraft({
      ...emptyTransitRouteDraft,
      routeName: `${defaultResource?.name || "中转服务器"}-new-route`,
      landingVpsId: defaultNode ? landingNodeKey(defaultNode) : "",
      targetNodeId: defaultNode?.id ?? "",
      targetPort: defaultNode?.port ? String(defaultNode.port) : "443",
    });
    setTransitModalMode("addRoute");
  }

  function openTransitRouteDetail(route: TransitRouteData) {
    setSelectedTransitRoute(route);
    setTransitModalMode("viewRoute");
  }

  function buildTransitResourcePayload(): TransitResourcePayload | null {
    const name = transitServerForm.name.trim();
    const entryHost = transitServerForm.entryHost.trim();
    const sshUsername = transitServerForm.sshUsername.trim();
    const sshPort = parseListenPortInput(transitServerForm.sshPort);

    if (!name) {
      setMessage("请填写中转服务器名称。");
      return null;
    }
    if (!entryHost) {
      setMessage("请填写中转服务器公网 IP。");
      return null;
    }
    if (sshPort === null) {
      setMessage("SSH 端口必须是 1-65535 之间的整数。");
      return null;
    }
    if (!sshUsername) {
      setMessage("请填写 SSH 用户名。");
      return null;
    }

    return {
      name,
      resource_type: "server",
      provider: transitServerForm.provider.trim() || null,
      entry_host: entryHost,
      entry_port: null,
      entry_region: null,
      exit_region: null,
      bandwidth_mbps: null,
      traffic_limit_gb: null,
      traffic_used_gb: null,
      protocol_hint: "tcp",
      has_ssh: true,
      ssh_host: entryHost,
      ssh_port: sshPort,
      ssh_username: sshUsername,
      status: selectedTransitResource?.status ?? "active",
      expires_at: null,
      notes: transitServerForm.notes.trim() || null,
    };
  }

  async function submitTransitServer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = buildTransitResourcePayload();
    if (!payload) {
      return;
    }
    try {
      setSubmittingTransitResource(true);
      const csrfToken = await ensureCsrfToken();
      const isEdit = transitModalMode === "editServer" && selectedTransitResource;
      const result = await apiFetch<TransitResourceData>(
        isEdit ? `/api/transit-resources/${selectedTransitResource.id}` : "/api/transit-resources",
        {
          body: JSON.stringify(payload),
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrfToken,
          },
          method: isEdit ? "PATCH" : "POST",
        },
      );
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setMessage(isEdit ? "中转服务器记录已更新。" : "中转服务器记录已添加。");
      closeTransitModal();
      await loadData();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存中转服务器记录失败。");
    } finally {
      setSubmittingTransitResource(false);
    }
  }

  async function createTransitRoute() {
    setCopied(false);
    if (!selectedResourceId || !selectedNodeId) {
      setMessage("请选择中转资源和已启用节点。");
      return;
    }
    const listenPortError = listenPortValidationMessage(listenPort);
    if (listenPortError) {
      setMessage(listenPortError);
      return;
    }
    if (forwardingMethod === "socat" && selectedResourceId !== SOCAT_RESOURCE_ID) {
      setMessage("socat 首轮测试只允许选择正式香港中转服务器。");
      return;
    }
    if (!confirm) {
      setMessage("请先确认风险提示。");
      return;
    }

    try {
      setMessage(`正在创建单条 ${forwardingMethod} TCP 转发任务。`);
      const csrfToken = await ensureCsrfToken();
      const result = await apiFormFetch<TransitRouteCreateResult>(
        "/api/transit-routes",
        buildForm(),
        {
          headers: { "X-CSRF-Token": csrfToken },
        },
      );
      clearCredentials();
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setMessage(`单条 ${forwardingMethod} TCP 转发任务已创建。`);
      await loadTask(result.data.task_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "创建中转规则任务失败。");
    }
  }

  async function diagnoseRoute(route: TransitRouteData) {
    const hasTextKey = diagnosticPrivateKeyText.trim().length > 0;
    const hasFileKey = Boolean(diagnosticFileInputRef.current?.files?.[0]);
    if (!hasTextKey && !hasFileKey) {
      setDiagnosticMessage("请先粘贴或选择中转服务器 SSH 私钥。");
      return;
    }

    try {
      setDiagnosticRouteId(route.id);
      setDiagnosticTask(null);
      setDiagnosticLogs([]);
      setDiagnosticMessage("正在创建中转线路只读诊断任务。");
      const csrfToken = await ensureCsrfToken();
      const result = await apiFormFetch<TransitRouteDiagnoseResult>(
        `/api/transit-routes/${route.id}/diagnose`,
        buildDiagnosticForm(),
        {
          headers: { "X-CSRF-Token": csrfToken },
        },
      );
      clearDiagnosticCredentials();
      if (!result.success) {
        setDiagnosticMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setDiagnosticMessage("中转线路只读诊断任务已创建。");
      await loadDiagnosticTask(result.data.task_id);
    } catch (error) {
      setDiagnosticMessage(error instanceof Error ? error.message : "中转线路只读诊断任务创建失败。");
    }
  }

  async function restartSocatRoute(route: TransitRouteData) {
    if (!isSocatTestRoute(route)) {
      setDiagnosticMessage("只允许重启 socat 18443 测试链路。");
      return;
    }
    const hasTextKey = diagnosticPrivateKeyText.trim().length > 0;
    const hasFileKey = Boolean(diagnosticFileInputRef.current?.files?.[0]);
    if (!hasTextKey && !hasFileKey) {
      setDiagnosticMessage("请先粘贴或选择中转服务器 SSH 私钥。");
      return;
    }
    const confirmed = window.confirm("仅重启 socat 测试链路，不会修改 gost 8443 正式链路。");
    if (!confirmed) {
      return;
    }

    try {
      setDiagnosticRouteId(route.id);
      setDiagnosticTask(null);
      setDiagnosticLogs([]);
      setDiagnosticMessage("正在创建 socat 测试链路重启任务。");
      const csrfToken = await ensureCsrfToken();
      const result = await apiFormFetch<TransitRouteRestartSocatResult>(
        `/api/transit-routes/${route.id}/restart-socat`,
        buildDiagnosticForm(),
        {
          headers: { "X-CSRF-Token": csrfToken },
        },
      );
      clearDiagnosticCredentials();
      if (!result.success) {
        setDiagnosticMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setDiagnosticMessage("socat 测试链路重启任务已创建。");
      await loadDiagnosticTask(result.data.task_id);
    } catch (error) {
      setDiagnosticMessage(error instanceof Error ? error.message : "socat 测试链路重启任务创建失败。");
    }
  }

  async function copyTransitLink() {
    const shareLink = stringValue(objectValue(task?.result_data?.["route"]), "share_link");
    if (shareLink === "-") {
      return;
    }
    const confirmed = window.confirm("中转链接属于敏感信息，仅用于客户端导入。不要粘贴到聊天、PR、日志或文档中。确认复制吗？");
    if (!confirmed) {
      return;
    }
    await navigator.clipboard.writeText(shareLink);
    setCopied(true);
  }

  async function copyRouteLink(route: TransitRouteData) {
    if (!route.share_link) {
      return;
    }
    const confirmed = window.confirm("中转链接属于敏感信息，仅用于客户端导入。不要粘贴到聊天、PR、日志或文档中。确认复制吗？");
    if (!confirmed) {
      return;
    }
    await navigator.clipboard.writeText(route.share_link);
    setCopiedRouteId(route.id);
  }

  async function copySocatCandidateLink(route: TransitRouteData) {
    const node = activeNodeForRoute(route);
    const transitHost = transitHostForRoute(route);
    if (!node || !transitHost || !(node.has_share_link ?? node.share_link_present ?? Boolean(node.masked_share_link))) {
      setDiagnosticMessage("当前 active 节点没有可导出的 share_link，暂不能生成候选正式链接。");
      return;
    }
    const confirmed = window.confirm(
      "这是敏感候选链接，仅用于客户端导入测试。不要粘贴到聊天、PR、日志或文档中。本操作不会修改 node.share_link，也不会停用 gost 8443。确认继续导出并复制吗？",
    );
    if (!confirmed) {
      return;
    }
    const csrfToken = await ensureCsrfToken();
    const exportResult = await exportNodeShareLink(node.id, csrfToken, "socat_candidate_link");
    if (!exportResult.success) {
      setDiagnosticMessage(`${exportResult.error_code}: ${exportResult.message}`);
      return;
    }
    const derivedLink = deriveSocatCandidateLink(route, exportResult.data.share_link, transitHost);
    await navigator.clipboard.writeText(derivedLink);
    setCopiedSocatCandidateRouteId(route.id);
    setDiagnosticMessage("候选链接已复制，请妥善保存，不要公开分享。");
  }

  async function copyDiagnostics(route: TransitRouteData) {
    await navigator.clipboard.writeText(diagnosticTextForRoute(route));
    setCopiedDiagnosticsRouteId(route.id);
  }

  async function copyLocalPlanSummary() {
    await navigator.clipboard.writeText(localPlanSummaryText);
    setPlanSummaryCopied(true);
  }

  async function copyReadonlyPreflightSummary() {
    await navigator.clipboard.writeText(readonlyPreflightPlan?.redacted_summary ?? readonlyPreflightSummaryText);
    setPreflightSummaryCopied(true);
  }

  function buildReadonlyPreflightPayload(): ReadonlyPreflightPlanRequest {
    return {
      transit_resource_id: planResourceId || null,
      transit_resource_name: planResource?.name ?? null,
      transit_host_hint: planResource?.entry_host ?? planResource?.ssh_host ?? null,
      landing_node_id: planNodeId || null,
      landing_node_name: planNode?.node_name ?? null,
      landing_host_hint: planNode?.vps_ip ?? null,
      landing_target_port: planTargetPort,
      planned_listen_port: planListenPort,
      route_purpose: planPurpose.trim() || null,
      firewall_security_group_confirmed: planCloudSecurityGroupConfirmed,
      cloud_firewall_confirmed: planCloudFirewallConfirmed,
      server_firewall_confirmed: planServerFirewallConfirmed,
      local_backup_confirmed: planLocalBackupConfirmed,
      user_approved_readonly_preflight: preflightHealthConfirmed && preflightBoundaryAcknowledged,
      workbuddy_authorized: preflightWorkbuddyBoundaryConfirmed,
      no_cutover_confirmed: preflightBoundaryAcknowledged,
      no_node_share_link_change_confirmed: preflightBoundaryAcknowledged,
    };
  }

  async function generateReadonlyPreflightPlan() {
    setReadonlyPreflightLoading(true);
    setReadonlyPreflightApiMessage("正在校验后端 no-op 只读预检计划。");
    try {
      const result = await requestReadonlyPreflightPlan(buildReadonlyPreflightPayload());
      if (!result.success) {
        setReadonlyPreflightPlan(null);
        setReadonlyPreflightApiMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setReadonlyPreflightPlan(result.data);
      setReadonlyPreflightApiMessage(result.message);
    } catch (error) {
      setReadonlyPreflightPlan(null);
      setReadonlyPreflightApiMessage(error instanceof Error ? error.message : "后端 no-op 只读预检计划校验失败。");
    } finally {
      setReadonlyPreflightLoading(false);
    }
  }

  function buildTransitReadonlyPreflightCommandPayload(): TransitReadonlyPreflightCommandRequest | null {
    if (!planResourceId || !planNodeId) {
      setRemotePreflightMessage("请选择中转服务器和落地节点。");
      return null;
    }
    if (!readonlyPreflightReady) {
      setRemotePreflightMessage("本地只读预检计划尚未 Ready，不能创建远程只读预检命令。");
      return null;
    }
    const plannedListenPortNumber = parseListenPortInput(planListenPort);
    if (plannedListenPortNumber === null || planTargetPortNumber === null) {
      setRemotePreflightMessage("计划监听端口和落地目标端口必须是合法 TCP 端口。");
      return null;
    }
    return {
      transit_resource_id: planResourceId,
      landing_node_id: planNodeId,
      planned_listen_port: plannedListenPortNumber,
      landing_target_port: planTargetPortNumber,
      forwarding_method: "socat",
      purpose: planPurpose.trim() || "中转链路只读预检",
      readonly: true,
    };
  }

  async function runTransitReadonlyPreflightCommand() {
    const payload = buildTransitReadonlyPreflightCommandPayload();
    if (!payload) {
      return;
    }
    setRemotePreflightLoading(true);
    setRemotePreflightMessage("正在创建 transit_readonly_preflight Worker command。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await createTransitReadonlyPreflightCommand(payload, csrfToken);
      if (!result.success) {
        setRemotePreflightCommand(null);
        setRemotePreflightMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setRemotePreflightCommand(result.data.command);
      setRemotePreflightMessage(result.message);
    } catch (error) {
      setRemotePreflightCommand(null);
      setRemotePreflightMessage(error instanceof Error ? error.message : "创建远程只读预检命令失败。");
    } finally {
      setRemotePreflightLoading(false);
    }
  }

  async function refreshTransitReadonlyPreflightCommand() {
    if (!remotePreflightCommand?.target_worker_id) {
      return;
    }
    setRemotePreflightLoading(true);
    setRemotePreflightMessage("正在刷新 Worker command 状态。");
    try {
      const result = await listWorkerCommands(remotePreflightCommand.target_worker_id);
      if (!result.success) {
        setRemotePreflightMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      const updated = result.data.commands.find((command) => command.id === remotePreflightCommand.id);
      if (!updated) {
        setRemotePreflightMessage("未找到当前远程只读预检命令，请稍后刷新。");
        return;
      }
      setRemotePreflightCommand(updated);
      setRemotePreflightMessage(workerCommandTerminalStatuses.has(updated.status) ? "远程只读预检命令已返回结果。" : "远程只读预检命令仍在执行或等待。");
    } catch (error) {
      setRemotePreflightMessage(error instanceof Error ? error.message : "刷新远程只读预检命令失败。");
    } finally {
      setRemotePreflightLoading(false);
    }
  }

  function transitHostForRoute(route: TransitRouteData) {
    const resource = resources.find((item) => item.id === route.transit_resource_id);
    return resource?.entry_host || resource?.ssh_host || null;
  }

  function processCheckCommand(route: TransitRouteData) {
    if (route.forwarding_method === "socat") {
      return "ps -ef | grep '[s]ocat'";
    }
    if (route.forwarding_method === "gost") {
      return "ps -ef | grep '[g]ost'";
    }
    return `ps -ef | grep '[${route.forwarding_method.slice(0, 1)}]${route.forwarding_method.slice(1)}'`;
  }

  function diagnosticCommandsForRoute(route: TransitRouteData) {
    const transitHost = displayValue(transitHostForRoute(route));
    const commands = [
      {
        label: "本地连通性",
        command: `nc -vz ${transitHost} ${route.listen_port}`,
      },
      {
        label: "中转机监听检查",
        command: `ss -lntp | grep ${route.listen_port}`,
      },
      {
        label: "中转机转发进程检查",
        command: processCheckCommand(route),
      },
      {
        label: "systemd 服务状态",
        command: route.service_name ? `systemctl status ${route.service_name}` : "-",
      },
      {
        label: "目标连通性",
        command: `nc -vz ${route.target_host} ${route.target_port}`,
      },
    ];
    return commands;
  }

  function diagnosticTextForRoute(route: TransitRouteData) {
    return diagnosticCommandsForRoute(route)
      .map((item) => `${item.label}: ${item.command}`)
      .join("\n");
  }

  function diagnosticCheckFor(key: string) {
    const result = diagnosticTask?.result_data;
    const directCheck = objectValue(result?.[key]);
    if (directCheck) {
      return directCheck;
    }
    const checks = objectValue(result?.["checks"]);
    return objectValue(checks?.[key]);
  }

  function checkOutput(check: Record<string, unknown> | null) {
    const output = check?.["raw_output"];
    return typeof output === "string" && output ? redactString(output) : "-";
  }

  function renderRemoteReadonlyPreflightResult() {
    if (!remotePreflightCommand) {
      return null;
    }
    const result = objectValue(remotePreflightCommand.result_json);
    const checks = Array.isArray(result?.["checks"]) ? result["checks"] : [];
    const status = stringValue(result, "status");
    const summary = stringValue(result, "summary");
    const redactedSummary = stringValue(result, "redacted_summary");

    return (
      <div className="readonly-preflight-api-result">
        <div className="status-row">
          <div>
            <h4>远程只读预检 Worker 结果</h4>
            <p className="message">
              command id: {remotePreflightCommand.id} / {workerCommandTypeLabel(remotePreflightCommand.command_type)}
            </p>
          </div>
          <span className={`pill ${remotePreflightCommand.status === "succeeded" ? "ok" : remotePreflightCommand.status === "failed" ? "bad" : "warn"}`}>
            {workerCommandStatusLabel(remotePreflightCommand.status)}
          </span>
        </div>
        <div className="detail-grid">
          <span>Worker</span>
          <strong>{remotePreflightCommand.target_worker_id}</strong>
          <span>Worker 版本</span>
          <strong>{remotePreflightCommand.target_worker_version ?? "-"}</strong>
          <span>命令状态</span>
          <strong>{workerCommandStatusLabel(remotePreflightCommand.status)}</strong>
          <span>预检状态</span>
          <strong>{status}</strong>
          <span>摘要</span>
          <strong>{summary}</strong>
        </div>
        <div className="warning-box">
          <strong>只读边界</strong>
          <span>该命令只执行固定 allowlist 只读检查，不创建真实转发，不安装或重启 socat / gost，不新增监听端口。</span>
          <span>结果已脱敏；不展示完整客户端链接、Worker token、Worker secret、SSH 私钥或数据库密码。</span>
        </div>
        {checks.length > 0 ? (
          <div className="readonly-preflight-checklist api-check-list">
            {checks.map((item, index) => {
              const check = objectValue(item);
              const checkId = stringValue(check, "id");
              const checkStatus = stringValue(check, "status");
              const checkPassed = check?.["passed"] === true;
              return (
                <div className="readonly-preflight-item api-check-card" key={`${checkId}-${index}`}>
                  <div className="status-row">
                    <div>
                      <strong>{stringValue(check, "label")}</strong>
                      <p className="message">{checkId}</p>
                    </div>
                    <span className={`pill ${checkPassed ? "ok" : "bad"}`}>{checkStatus}</span>
                  </div>
                  <div className="detail-grid compact-detail-grid">
                    <span>是否通过</span>
                    <strong>{booleanLabel(checkPassed)}</strong>
                    <span>脱敏详情</span>
                    <strong>{stringValue(check, "detail")}</strong>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="warning-box">
            <strong>尚未返回检查项</strong>
            <span>如果命令仍在 pending / running，请稍后刷新状态。</span>
          </div>
        )}
        {redactedSummary !== "-" ? (
          <div>
            <h4>脱敏结果摘要</h4>
            <pre className="local-plan-output">{redactedSummary}</pre>
          </div>
        ) : null}
      </div>
    );
  }

  function routeBadge(route: TransitRouteData) {
    if (route.forwarding_method === "socat" && route.listen_port === 18443) {
      return "当前正式链路 / socat 18443";
    }
    if (route.forwarding_method === "gost" && route.listen_port === 8443) {
      return "回退链路 / 保留";
    }
    return "只读线路";
  }

  function isSocatTestRoute(route: TransitRouteData) {
    return route.forwarding_method === "socat" && route.listen_port === 18443;
  }

  function activeNodeForRoute(route: TransitRouteData) {
    return nodes.find((node) => node.id === route.node_id && node.status === "active") ?? null;
  }

  function deriveSocatCandidateLink(route: TransitRouteData, shareLink: string, transitHost: string) {
    try {
      const url = new URL(shareLink);
      url.hostname = transitHost;
      url.port = String(route.listen_port);
      return url.toString();
    } catch {
      return shareLink.replace(/@([^:/?#]+)(?::\d+)?/, `@${transitHost}:${route.listen_port}`);
    }
  }

  const activeServerResources = resources.filter((resource) => resource.status === "active");
  const planningSelectableServerResources = resources.filter(isPlanningSelectableTransitResource);
  const routesByResourceId = routes.reduce<Record<string, TransitRouteData[]>>((accumulator, route) => {
    const bucket = accumulator[route.transit_resource_id] ?? [];
    bucket.push(route);
    accumulator[route.transit_resource_id] = bucket;
    return accumulator;
  }, {});
  const selectedResource = resources.find((resource) => resource.id === selectedResourceId) ?? null;
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? null;
  const selectableResources =
    forwardingMethod === "socat"
      ? activeServerResources.filter((resource) => resource.id === SOCAT_RESOURCE_ID)
      : activeServerResources;
  const listenPortError = listenPortValidationMessage(listenPort);
  const result = task?.result_data ?? null;
  const resultRoute = objectValue(result?.["route"]);
  const resultGost = objectValue(result?.["gost"]);
  const resultSocat = objectValue(result?.["socat"]);
  const resultVerify = objectValue(result?.["verify"]);
  const resultShareLink = stringValue(resultRoute, "share_link");
  const resultMethod = stringValue(resultRoute, "forwarding_method");
  const resultListenPort = scalarValue(resultRoute, "listen_port");
  const resultTargetHost = stringValue(resultRoute, "target_host");
  const resultTargetPort = scalarValue(resultRoute, "target_port");
  const resultTransitHost = selectedResource?.entry_host ?? selectedResource?.ssh_host ?? null;
  const shouldShowSocatTestHint =
    resultMethod === "socat" && resultTransitHost !== null && resultListenPort !== "-";
  const failures = Array.isArray(result?.["failures"])
    ? result["failures"].filter((item) => typeof item === "string")
    : [];
  const warnings = Array.isArray(result?.["warnings"])
    ? result["warnings"].filter((item) => typeof item === "string")
    : [];
  const planResource = resources.find((resource) => resource.id === planResourceId) ?? null;
  const planNode = nodes.find((node) => node.id === planNodeId) ?? null;
  const planListenPortError = listenPortValidationMessage(planListenPort);
  const planTargetPortNumber = parseListenPortInput(planTargetPort);
  const planTargetPortError = planTargetPortNumber === null ? "落地目标端口必须是 1-65535 之间的整数。" : null;
  const localPlanIssues = [
    !planResource ? "请选择目标中转资源。" : null,
    !planNode ? "请选择落地 VPS / 已启用节点。" : null,
    planListenPortError,
    planTargetPortError,
    planPurpose.trim() ? null : "请填写目标平台 / 用途。",
    planCloudSecurityGroupConfirmed ? null : "云服务器安全组尚未确认放行计划 TCP 端口。",
    planCloudFirewallConfirmed ? null : "云防火墙尚未确认放行计划 TCP 端口。",
    planServerFirewallConfirmed ? null : "服务器防火墙尚未确认放行计划 TCP 端口。",
    planLocalBackupConfirmed ? null : "本地数据库备份尚未确认完成。",
  ].filter((item): item is string => Boolean(item));
  const localPlanReady = localPlanIssues.length === 0;
  const localPlanStatusLabel = localPlanReady ? "可进入只读预检审批" : "不通过";
  const localPlanSummaryText = [
    "LiveLine 单条转发本地 dry-run 规划",
    `状态：${localPlanStatusLabel}`,
    `中转资源：${planResource?.name ?? "待确认"}`,
    `落地节点：${planNode?.node_name ?? "待确认"}`,
    `计划监听端口：${planListenPort || "待确认"}`,
    `落地目标端口：${planTargetPortNumber ?? "待确认"}`,
    `用途：${planPurpose.trim() || "待确认"}`,
    `云服务器安全组已确认：${planCloudSecurityGroupConfirmed ? "是" : "否"}`,
    `云防火墙已确认：${planCloudFirewallConfirmed ? "是" : "否"}`,
    `服务器防火墙已确认：${planServerFirewallConfirmed ? "是" : "否"}`,
    `本地数据库备份已确认：${planLocalBackupConfirmed ? "是" : "否"}`,
    "远程执行：未授权",
    "真实转发创建：未授权",
    "node.share_link 修改：未授权",
    "正式 cutover：未授权",
    "敏感信息：完整节点链接、SSH Key、密码、token、SESSION_SECRET 均不写入摘要。",
  ].join("\n");
  const readonlyPreflightIssues = [
    ...localPlanIssues,
    preflightHealthConfirmed ? null : "当前系统 health 尚未确认正常，请先执行本地 health check。",
    preflightBoundaryAcknowledged
      ? null
      : "请确认这只是只读预检计划，不会执行 SSH、创建真实转发或修改 node.share_link。",
    preflightWorkbuddyBoundaryConfirmed
      ? null
      : "请确认远程只读预检只通过 Worker allowlist 执行固定检查，不接受任意 shell。",
  ].filter((item): item is string => Boolean(item));
  const readonlyPreflightReady = readonlyPreflightIssues.length === 0;
  const readonlyPreflightStatusLabel = readonlyPreflightReady
    ? "可进入只读预检审批"
    : "不通过";
  const readonlyPreflightSummaryText = [
    "LiveLine 单条转发只读预检框架",
    `状态：${readonlyPreflightStatusLabel}`,
    `中转资源：${planResource?.name ?? "待确认"}`,
    `落地节点：${planNode?.node_name ?? "待确认"}`,
    `计划监听端口：${planListenPort || "待确认"}`,
    `落地目标端口：${planTargetPortNumber ?? "待确认"}`,
    `用途：${planPurpose.trim() || "待确认"}`,
    `云服务器安全组已确认：${planCloudSecurityGroupConfirmed ? "是" : "否"}`,
    `云防火墙已确认：${planCloudFirewallConfirmed ? "是" : "否"}`,
    `服务器防火墙已确认：${planServerFirewallConfirmed ? "是" : "否"}`,
    `本地数据库备份已确认：${planLocalBackupConfirmed ? "是" : "否"}`,
    `本地 health 已确认：${preflightHealthConfirmed ? "是" : "否"}`,
    `只读边界已确认：${preflightBoundaryAcknowledged ? "是" : "否"}`,
    `Worker allowlist 只读边界已确认：${preflightWorkbuddyBoundaryConfirmed ? "是" : "否"}`,
    "未来只读检查项：",
    ...readonlyPreflightItemSpecs.map((item) => `- ${item.label}: ${item.scope}`),
    "SSH：本阶段不执行",
    "远程命令：本阶段不执行",
    "真实转发创建：未授权",
    "真实监听端口新增：未授权",
    "node.share_link 修改：未授权",
    "正式 cutover：未授权",
    "敏感信息：完整节点链接、SSH Key、密码、token、SESSION_SECRET 均不写入摘要。",
  ].join("\n");

  function renderTransitLinkTable() {
    if (loadingResources) {
      return <div className="server-table-empty">正在加载中转链路记录...</div>;
    }

    if (routes.length === 0) {
      return (
        <div className="server-table-empty">
          暂无中转链路记录。点击“添加中转链路”只能打开本地规划弹窗；不会创建真实线路或新增监听端口。
        </div>
      );
    }

    return routes.map((route) => {
      const resource = resources.find((item) => item.id === route.transit_resource_id) ?? null;
      const node = nodes.find((item) => item.id === route.node_id) ?? null;
      const landingServer = route.landing_vps_ip ?? node?.vps_ip ?? route.target_host;
      const transitServerName = resource?.name ?? route.transit_resource_name ?? "-";
      const transitServerHost = resource ? transitHostLabel(resource) : "-";
      const landingServerId = route.landing_vps_id ?? "落地服务器";
      const targetNodeName = route.node_name ?? node?.node_name ?? "-";
      const roleLabel = routeBadge(route);
      return (
        <div className="server-table-group" key={route.id}>
          <div className="server-table-row transit-link-row">
            <div>
              <strong className="table-ellipsis" title={route.name}>
                {route.name}
              </strong>
              <span className="node-meta-line table-ellipsis" title={route.id}>
                {route.id.slice(0, 8)}
              </span>
            </div>
            <div>
              <strong className="table-ellipsis" title={transitServerName}>
                {transitServerName}
              </strong>
              <span className="node-meta-line table-ellipsis" title={transitServerHost}>
                {transitServerHost}
              </span>
            </div>
            <span>监听 {route.listen_port}</span>
            <div>
              <strong className="table-ellipsis" title={landingServer}>
                {landingServer}
              </strong>
              <span className="node-meta-line table-ellipsis" title={landingServerId}>
                {landingServerId}
              </span>
            </div>
            <div>
              <strong className="table-ellipsis" title={targetNodeName}>
                {targetNodeName}
              </strong>
              <span className="node-meta-line">目标端口 {route.target_port}</span>
            </div>
            <span>{route.target_port}</span>
            <span>{route.forwarding_method}</span>
            <div>
              <span className={`pill ${routeStatusClass(route.status)}`}>{routeStatusLabel(route.status)}</span>
              <span className="node-meta-line">本地记录 / 远程状态需单独诊断</span>
            </div>
            <span className="table-ellipsis" title={roleLabel}>
              {roleLabel}
            </span>
            <div className="server-actions transit-link-actions-cell">
              <button className="secondary compact" type="button" onClick={() => openTransitRouteDetail(route)}>
                查看
              </button>
              <button
                className="secondary compact"
                type="button"
                onClick={() => setMessage("诊断需要后续远程只读预检 / Worker 授权阶段；本阶段不执行远程命令。")}
              >
                诊断
              </button>
              <button
                className="danger compact"
                type="button"
                onClick={() => setMessage("删除转发链路需要远程清理成功后再删除系统记录；本阶段不执行删除。")}
              >
                删除
              </button>
            </div>
          </div>
        </div>
      );
    });
  }

  function renderTransitServerModal() {
    const isEdit = transitModalMode === "editServer";
    return (
      <div className="modal-backdrop" role="presentation">
        <div aria-modal="true" className="modal-card transit-server-modal" role="dialog">
          <div className="modal-header">
            <div>
              <h3>{isEdit ? "编辑中转服务器" : "添加中转服务器"}</h3>
              <p className="message">仅保存本地资源记录；不会安装 Worker，不会执行 SSH。</p>
            </div>
            <button className="secondary compact" type="button" onClick={closeTransitModal}>
              关闭
            </button>
          </div>
          <form className="form server-modal-form" onSubmit={(event) => void submitTransitServer(event)}>
            <label>
              中转服务器名称
              <input
                value={transitServerForm.name}
                onChange={(event) => updateTransitServerForm("name", event.target.value)}
                placeholder="例如：香港中转机"
              />
            </label>
            <label>
              公网 IP
              <input
                value={transitServerForm.entryHost}
                onChange={(event) => updateTransitServerForm("entryHost", event.target.value)}
                placeholder="仅填写 IP 或主机名，不写密钥"
              />
            </label>
            <label>
              SSH 端口
              <input
                inputMode="numeric"
                value={transitServerForm.sshPort}
                onChange={(event) => updateTransitServerForm("sshPort", event.target.value)}
              />
            </label>
            <label>
              SSH 用户名
              <input
                value={transitServerForm.sshUsername}
                onChange={(event) => updateTransitServerForm("sshUsername", event.target.value)}
              />
            </label>
            <label>
              服务商 / 备注来源
              <input
                value={transitServerForm.provider}
                onChange={(event) => updateTransitServerForm("provider", event.target.value)}
                placeholder="可选"
              />
            </label>
            <label className="wide-field">
              备注
              <textarea
                value={transitServerForm.notes}
                onChange={(event) => updateTransitServerForm("notes", event.target.value)}
                placeholder="不要填写 SSH Key、密码、token、完整节点链接。"
              />
            </label>
            <div className="warning-box wide-field">
              <strong>Worker 接入方式</strong>
              <span>即将支持：curl | bash Worker 接入。</span>
              <span>本阶段不生成 Worker token，不安装 Worker，不执行 SSH / 远程命令。</span>
              <span>SSH 方式源码能力保留在历史流程中，但此弹窗只记录本地资源元数据。</span>
            </div>
            <div className="modal-actions wide-field">
              <button disabled={submittingTransitResource} type="submit">
                {submittingTransitResource ? "保存中..." : isEdit ? "保存修改" : "添加中转服务器"}
              </button>
              <button className="secondary" type="button" onClick={closeTransitModal}>
                取消
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  function renderTransitRouteDraftModal() {
    const draftListenError = listenPortValidationMessage(transitRouteDraft.listenPort);
    const draftTargetPortError =
      parseListenPortInput(transitRouteDraft.targetPort) === null ? "目标端口必须是 1-65535 之间的整数。" : null;
    const draftNode = nodes.find((node) => node.id === transitRouteDraft.targetNodeId) ?? null;
    const landingServers = Array.from(
      new Map(
        nodes.map((node) => [
          landingNodeKey(node),
          {
            id: landingNodeKey(node),
            label: landingNodeLabel(node),
          },
        ]),
      ).values(),
    );
    const filteredNodes = transitRouteDraft.landingVpsId
      ? nodes.filter((node) => landingNodeKey(node) === transitRouteDraft.landingVpsId)
      : nodes;
    return (
      <div className="modal-backdrop" role="presentation">
        <div aria-modal="true" className="modal-card transit-server-modal" role="dialog">
          <div className="modal-header">
            <div>
              <h3>添加转发链路 / 本地规划</h3>
              <p className="message">只整理本地规划，不调用真实创建接口，不新增监听端口。</p>
            </div>
            <button className="secondary compact" type="button" onClick={closeTransitModal}>
              关闭
            </button>
          </div>
          <div className="form server-modal-form">
            <label>
              中转服务器
              <select
                value={selectedTransitResource?.id ?? ""}
                onChange={(event) => {
                  const nextResource = resources.find((resource) => resource.id === event.target.value) ?? null;
                  setSelectedTransitResource(nextResource);
                  setTransitRouteDraft((current) => ({
                    ...current,
                    routeName: current.routeName || `${nextResource?.name || "中转服务器"}-new-route`,
                  }));
                }}
              >
                {planningSelectableServerResources.length === 0 ? <option value="">暂无可用于本地规划的中转服务器</option> : null}
                {planningSelectableServerResources.map((resource) => (
                  <option key={resource.id} value={resource.id}>
                    {resource.name} / {transitHostLabel(resource)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              链路名称
              <input
                value={transitRouteDraft.routeName}
                onChange={(event) => updateTransitRouteDraft("routeName", event.target.value)}
              />
            </label>
            <label>
              转发方式
              <select
                value={transitRouteDraft.forwardingMethod}
                onChange={(event) => updateTransitRouteDraft("forwardingMethod", event.target.value as ForwardingMethod)}
              >
                <option value="socat">socat</option>
                <option value="gost">gost</option>
              </select>
            </label>
            <label>
              中转监听端口
              <input
                inputMode="numeric"
                value={transitRouteDraft.listenPort}
                onChange={(event) => updateTransitRouteDraft("listenPort", event.target.value)}
                placeholder="避开 22 / 8443 / 18443 / 20575"
              />
              <span className={`field-hint ${draftListenError ? "danger-text" : ""}`}>
                {draftListenError ?? "新增端口前必须检查云安全组、云防火墙和服务器防火墙。"}
              </span>
            </label>
            <label>
              目标落地服务器
              <select
                value={transitRouteDraft.landingVpsId}
                onChange={(event) => {
                  const nextLandingVpsId = event.target.value;
                  const firstNode = nodes.find((node) => landingNodeKey(node) === nextLandingVpsId) ?? null;
                  setTransitRouteDraft((current) => ({
                    ...current,
                    landingVpsId: nextLandingVpsId,
                    targetNodeId: firstNode?.id ?? "",
                    targetPort: firstNode?.port ? String(firstNode.port) : current.targetPort,
                  }));
                }}
              >
                {landingServers.length === 0 ? <option value="">暂无落地服务器节点</option> : null}
                {landingServers.map((server) => (
                  <option key={server.id} value={server.id}>
                    {server.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              目标节点
              <select
                value={transitRouteDraft.targetNodeId}
                onChange={(event) => {
                  const nextNode = nodes.find((node) => node.id === event.target.value) ?? null;
                  setTransitRouteDraft((current) => ({
                    ...current,
                    targetNodeId: event.target.value,
                    targetPort: nextNode?.port ? String(nextNode.port) : current.targetPort,
                  }));
                }}
              >
                {filteredNodes.length === 0 ? <option value="">暂无已启用节点</option> : null}
                {filteredNodes.map((node) => (
                  <option key={node.id} value={node.id}>
                    {node.node_name} / {displayValue(node.vps_ip)}:{displayValue(node.port)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              目标端口
              <input
                inputMode="numeric"
                value={transitRouteDraft.targetPort}
                onChange={(event) => updateTransitRouteDraft("targetPort", event.target.value)}
              />
              <span className={`field-hint ${draftTargetPortError ? "danger-text" : ""}`}>
                {draftTargetPortError ?? "默认可参考落地节点端口，实际创建需后续审批。"}
              </span>
            </label>
            <label className="wide-field">
              备注，可选
              <textarea
                value={transitRouteDraft.notes}
                onChange={(event) => updateTransitRouteDraft("notes", event.target.value)}
                placeholder="不要写入完整节点链接、SSH Key、密码或 token。"
              />
            </label>
            <div className="warning-box wide-field">
              <strong>本阶段不创建真实转发</strong>
              <span>中转服务器：{selectedTransitResource?.name ?? "-"}</span>
              <span>目标节点：{draftNode?.node_name ?? "待选择"}</span>
              <span>真实创建、远程监听检查和诊断必须进入后续 Worker / API 阶段。</span>
            </div>
            <div className="modal-actions wide-field">
              <button disabled type="button">
                真实创建需后续 Worker 阶段
              </button>
              <button className="secondary" type="button" onClick={closeTransitModal}>
                关闭
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  function renderTransitRouteDetailModal() {
    if (!selectedTransitRoute) {
      return null;
    }
    return (
      <div className="modal-backdrop" role="presentation">
        <div aria-modal="true" className="modal-card transit-route-detail-modal" role="dialog">
          <div className="modal-header">
            <div>
              <h3>{selectedTransitRoute.name}</h3>
              <p className="message">转发链路详情只读展示；不会执行诊断、删除或正式切换。</p>
            </div>
            <button className="secondary compact" type="button" onClick={closeTransitModal}>
              关闭
            </button>
          </div>
          <div className="detail-grid">
            <span>链路名称</span>
            <strong>{selectedTransitRoute.name}</strong>
            <span>转发方式</span>
            <strong>{selectedTransitRoute.forwarding_method}</strong>
            <span>监听端口</span>
            <strong>{selectedTransitRoute.listen_port}</strong>
            <span>目标地址</span>
            <strong>{selectedTransitRoute.target_host}</strong>
            <span>目标端口</span>
            <strong>{selectedTransitRoute.target_port}</strong>
            <span>状态</span>
            <strong>{routeStatusLabel(selectedTransitRoute.status)}</strong>
            <span>角色标识</span>
            <strong>{routeBadge(selectedTransitRoute)}</strong>
            <span>systemd 服务</span>
            <strong>{selectedTransitRoute.service_name || "-"}</strong>
            <span>share_link</span>
            <strong>{selectedTransitRoute.share_link ? "已生成 / 默认不展示完整链接" : "未生成"}</strong>
          </div>
          <div className="warning-box">
            <strong>安全边界</strong>
            <span>本详情弹窗不修改 node.share_link，不新增监听端口，不执行 SSH / 远程命令。</span>
            <span>如后续需要删除链路，必须先完成远程 socat / gost 清理并单独审批。</span>
          </div>
        </div>
      </div>
    );
  }

  function renderTransitModal() {
    if (transitModalMode === "addServer" || transitModalMode === "editServer") {
      return renderTransitServerModal();
    }
    if (transitModalMode === "addRoute") {
      return renderTransitRouteDraftModal();
    }
    if (transitModalMode === "viewRoute") {
      return renderTransitRouteDetailModal();
    }
    return null;
  }

  return (
    <section className="panel wide server-management-panel transit-link-management-panel">
      <div className="server-management-header">
        <div>
          <h2>中转链路</h2>
          <p className="message">管理中转服务器到落地节点的转发关系；本地规划不等于远程执行或正式 cutover。</p>
        </div>
        <button type="button" onClick={() => openAddTransitRoute()}>
          添加中转链路
        </button>
      </div>

      <div className="server-management-note">
        当前页面只展示和规划转发关系。中转服务器资源本身请到“中转服务器”页面管理；真实创建、远程诊断和删除清理将在后续 Worker / API 阶段开放。
      </div>

      <details className="route-safety-guardrail">
        <summary className="route-safety-summary">
          <div className="route-safety-heading">
            <span>TRANSIT ROUTE SAFETY</span>
            <strong>查看中转链路安全说明</strong>
          </div>
          <span className="notice-toggle-text">
            <span className="when-closed">查看说明</span>
            <span className="when-open">收起说明</span>
          </span>
        </summary>
        <div className="route-safety-body">
          <ul className="route-safety-list">
            <li>中转链路用于描述“中转服务器监听端口 → 落地节点目标端口”的转发关系。</li>
            <li>添加中转链路弹窗只做本地规划，不创建真实线路，不新增监听端口。</li>
            <li>socat / gost 是当前保留的转发方式；本阶段不新增 HAProxy，不安装 Worker，不生成 Worker token。</li>
            <li>本阶段不执行 SSH / 远程命令，不修改 node.share_link，不做正式 cutover。</li>
            <li>新增或变更监听端口后，必须同步检查云服务器安全组 / 云防火墙 / 服务器防火墙是否放行对应 TCP 端口。</li>
          </ul>
        </div>
      </details>

      <div className="transit-link-table-scroll">
        <div className="server-table transit-link-table">
          <div className="server-table-row server-table-head">
            <span>链路名称</span>
            <span>中转服务器</span>
            <span>监听端口</span>
            <span>落地服务器</span>
            <span>目标节点</span>
            <span>目标端口</span>
            <span>转发方式</span>
            <span>状态</span>
            <span>角色标识</span>
            <span className="transit-link-actions-head">操作</span>
          </div>
          {renderTransitLinkTable()}
        </div>
      </div>

      <div className="server-management-footer">
        <p className="message">{message}</p>
        <button className="secondary" type="button" onClick={() => void loadData()}>
          刷新数据
        </button>
      </div>

      {renderTransitModal()}

      <details className="transit-legacy-workbench collapsible-notice">
        <summary className="collapsible-summary">
          <strong>查看高级链路规划 / 只读预检 / 历史诊断工具</strong>
          <span className="notice-toggle-text">
            <span className="when-closed">查看工具</span>
            <span className="when-open">收起工具</span>
          </span>
        </summary>
        <div className="transit-legacy-body">
      <CollapsibleWarning title="查看单条转发安全门槛">
        <span>创建单条转发不等于正式切换，也不会修改 node.share_link。</span>
        <span>8443 当前保留给 gost 回退链路；18443 当前为 socat 正式链路。</span>
        <span>不要把 8443 / 18443 用作新转发端口，也不要让 socat 接管 8443。</span>
        <span>修改 node.share_link 必须单独进入正式切换审批阶段。</span>
        <span>真正创建远程转发或检查远程端口时，需要 Workbuddy 或单独授权阶段。</span>
      </CollapsibleWarning>
      <RouteSafetyGuardrails context="routes" />

      <details className="cutover-boundary-banner collapsible-notice">
        <summary className="collapsible-summary">
          <strong>查看 cutover 风险提示</strong>
          <span className="notice-toggle-text">
            <span className="when-closed">查看说明</span>
            <span className="when-open">收起说明</span>
          </span>
        </summary>
        <div className="cutover-boundary-grid">
          <div>
            <span className="route-role candidate">候选链路</span>
            <strong>socat 18443</strong>
            <p>已验收候选链路；复制和预检不等于新增真实转发。</p>
          </div>
          <div>
            <span className="route-role formal">正式链路</span>
            <strong>node.share_link → socat 18443</strong>
            <p>本阶段只展示现状，不读取、不写入、不替换正式节点链接。</p>
          </div>
          <div>
            <span className="route-role rollback">回滚链路</span>
            <strong>gost 8443</strong>
            <p>继续保留为回退链路；不得关闭、降级、替换或让 socat 接管 8443。</p>
          </div>
          <button className="danger compact" disabled type="button">
            正式切换需单独审批
          </button>
        </div>
      </details>

      <div className="local-plan-builder">
        <div className="status-row">
          <div>
            <h3>单条转发本地规划 / 仅 dry-run</h3>
            <p className="message">
              只做本地规则检查和审批摘要，不连接远端、不写入远程配置、不创建真实转发、不修改 node.share_link、不做 cutover。
            </p>
          </div>
          <span className={`pill ${localPlanReady ? "ok" : "bad"}`}>{localPlanStatusLabel}</span>
        </div>
        <CollapsibleWarning title="查看本地规划边界">
          <span>即使显示“可进入只读预检审批”，也只代表可以进入只读预检审批；真实转发创建仍未授权。</span>
          <span>8443 保留给 gost 回退链路；18443 是当前 socat 正式链路；22 / 20575 不得用于业务转发。</span>
          <span>新增或变更端口前，必须确认云服务器安全组、云防火墙和服务器防火墙均放行对应 TCP 端口。</span>
        </CollapsibleWarning>
        <div className="local-plan-layout">
          <div className="form route-form local-plan-form">
            <label>
              中转资源
              <select
                value={planResourceId}
                onChange={(event) => {
                  setPlanResourceId(event.target.value);
                  setPlanSummaryCopied(false);
                  setPreflightSummaryCopied(false);
                }}
              >
                {planningSelectableServerResources.length === 0 ? <option value="">暂无可用于本地规划的中转服务器</option> : null}
                {planningSelectableServerResources.map((resource) => (
                  <option key={resource.id} value={resource.id}>
                    {resource.name} / {displayValue(resource.entry_host)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              落地 VPS / 已启用节点
              <select
                value={planNodeId}
                onChange={(event) => {
                  setPlanNodeId(event.target.value);
                  setPlanSummaryCopied(false);
                  setPreflightSummaryCopied(false);
                }}
              >
                {nodes.length === 0 ? <option value="">暂无已启用节点</option> : null}
                {nodes.map((node) => (
                  <option key={node.id} value={node.id}>
                    {node.node_name} / {displayValue(node.vps_ip)}:{displayValue(node.port)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              计划监听端口
              <input
                inputMode="numeric"
                value={planListenPort}
                onChange={(event) => {
                  setPlanListenPort(event.target.value);
                  setPlanSummaryCopied(false);
                  setPreflightSummaryCopied(false);
                }}
                placeholder="例如：一个未占用的高位 TCP 端口"
              />
              <span className={`field-hint ${planListenPortError ? "danger-text" : ""}`}>
                {planListenPortError ?? "端口需为 1-65535 的整数，并避开 22 / 8443 / 18443 / 20575。"}
              </span>
            </label>
            <label>
              落地目标端口
              <input
                inputMode="numeric"
                value={planTargetPort}
                onChange={(event) => {
                  setPlanTargetPort(event.target.value);
                  setPlanSummaryCopied(false);
                  setPreflightSummaryCopied(false);
                }}
                placeholder="例如：443"
              />
              <span className={`field-hint ${planTargetPortError ? "danger-text" : ""}`}>
                {planTargetPortError ?? "只用于本地规划摘要，不会触发远程检查。"}
              </span>
            </label>
            <label className="wide-field">
              目标平台 / 用途
              <input
                value={planPurpose}
                onChange={(event) => {
                  setPlanPurpose(event.target.value);
                  setPlanSummaryCopied(false);
                  setPreflightSummaryCopied(false);
                }}
                placeholder="例如：候选直播线路测试 / 客户端手动验收"
              />
            </label>
            <div className="local-plan-checks wide-field">
              <label className="check-row">
                <input
                  checked={planCloudSecurityGroupConfirmed}
                  type="checkbox"
                  onChange={(event) => {
                    setPlanCloudSecurityGroupConfirmed(event.target.checked);
                    setPlanSummaryCopied(false);
                    setPreflightSummaryCopied(false);
                  }}
                />
                <span>已确认云服务器安全组放行计划 TCP 端口</span>
              </label>
              <label className="check-row">
                <input
                  checked={planCloudFirewallConfirmed}
                  type="checkbox"
                  onChange={(event) => {
                    setPlanCloudFirewallConfirmed(event.target.checked);
                    setPlanSummaryCopied(false);
                    setPreflightSummaryCopied(false);
                  }}
                />
                <span>已确认云防火墙放行计划 TCP 端口</span>
              </label>
              <label className="check-row">
                <input
                  checked={planServerFirewallConfirmed}
                  type="checkbox"
                  onChange={(event) => {
                    setPlanServerFirewallConfirmed(event.target.checked);
                    setPlanSummaryCopied(false);
                    setPreflightSummaryCopied(false);
                  }}
                />
                <span>已确认服务器防火墙放行计划 TCP 端口</span>
              </label>
              <label className="check-row">
                <input
                  checked={planLocalBackupConfirmed}
                  type="checkbox"
                  onChange={(event) => {
                    setPlanLocalBackupConfirmed(event.target.checked);
                    setPlanSummaryCopied(false);
                    setPreflightSummaryCopied(false);
                  }}
                />
                <span>已完成本地数据库备份，且备份文件不会进入 Git</span>
              </label>
            </div>
          </div>
          <div className="local-plan-summary">
            <div className="status-row">
              <h4>本地审批摘要</h4>
              <button className="secondary compact" type="button" onClick={() => void copyLocalPlanSummary()}>
                {planSummaryCopied ? "已复制" : "复制摘要"}
              </button>
            </div>
            <div className="detail-grid">
              <span>规划结论</span>
              <strong>{localPlanStatusLabel}</strong>
              <span>中转资源</span>
              <strong>{planResource?.name ?? "-"}</strong>
              <span>落地节点</span>
              <strong>{planNode?.node_name ?? "-"}</strong>
              <span>计划端口</span>
              <strong>{planListenPort || "-"}</strong>
              <span>落地端口</span>
              <strong>{planTargetPortNumber ?? "-"}</strong>
            </div>
            {localPlanIssues.length > 0 ? (
              <div className="failure-box">
                <strong>不通过原因</strong>
                {localPlanIssues.map((issue) => (
                  <span key={issue}>{issue}</span>
                ))}
              </div>
            ) : (
              <div className="warning-box">
                <strong>就绪仅限下一阶段审批</strong>
                <span>当前只可进入只读预检审批；不得创建真实转发，不得修改 node.share_link。</span>
              </div>
            )}
            <pre className="local-plan-output">{localPlanSummaryText}</pre>
          </div>
        </div>
      </div>

      <TransitReadonlyPreflightSimplePanel
        boundaryConfirmed={preflightBoundaryAcknowledged}
        healthConfirmed={preflightHealthConfirmed}
        issues={readonlyPreflightIssues}
        nodeName={planNode?.node_name ?? ""}
        plannedListenPort={planListenPort}
        preflightSummaryCopied={preflightSummaryCopied}
        readonlyPreflightApiMessage={readonlyPreflightApiMessage}
        readonlyPreflightLoading={readonlyPreflightLoading}
        readonlyPreflightPlan={readonlyPreflightPlan}
        ready={readonlyPreflightReady}
        remotePreflightCommand={remotePreflightCommand}
        remotePreflightLoading={remotePreflightLoading}
        remotePreflightMessage={remotePreflightMessage}
        resourceName={planResource?.name ?? ""}
        statusLabel={readonlyPreflightStatusLabel}
        targetPort={planTargetPortNumber ? String(planTargetPortNumber) : ""}
        workerBoundaryConfirmed={preflightWorkbuddyBoundaryConfirmed}
        onBoundaryConfirmedChange={(value) => {
          setPreflightBoundaryAcknowledged(value);
          setPreflightSummaryCopied(false);
        }}
        onCopySummary={() => void copyReadonlyPreflightSummary()}
        onGeneratePlan={() => void generateReadonlyPreflightPlan()}
        onHealthConfirmedChange={(value) => {
          setPreflightHealthConfirmed(value);
          setPreflightSummaryCopied(false);
        }}
        onRefreshCommand={() => void refreshTransitReadonlyPreflightCommand()}
        onRunCommand={() => void runTransitReadonlyPreflightCommand()}
        onWorkerBoundaryConfirmedChange={(value) => {
          setPreflightWorkbuddyBoundaryConfirmed(value);
          setPreflightSummaryCopied(false);
        }}
      />

      <details className="legacy-readonly-preflight-panel">
        <summary className="collapsible-summary">
          <strong>查看旧版高级只读预检面板</strong>
          <span className="notice-toggle-text">
            <span className="when-closed">查看说明</span>
            <span className="when-open">收起说明</span>
          </span>
        </summary>
        <div className="local-plan-builder readonly-preflight-plan">
        <div className="status-row">
          <div>
            <h3>远程只读预检 / Worker allowlist</h3>
            <p className="message">
              基于上方本地规划创建 transit_readonly_preflight Worker command。该命令只执行固定只读检查，不执行 SSH、不创建真实转发、不新增监听端口、不修改 node.share_link、不做 cutover。
            </p>
          </div>
          <span className={`pill ${readonlyPreflightReady ? "ok" : "bad"}`}>
            {readonlyPreflightStatusLabel}
          </span>
        </div>
        <CollapsibleWarning title="查看只读预检安全边界">
          <span>远程只读预检只通过 Worker allowlist 执行固定检查，不接受任意 shell，不安装、不启动、不停止、不重启 socat / gost。</span>
          <span>真正创建远程转发和切换 node.share_link 必须单独审批；本按钮不会进入创建阶段。</span>
          <span>当前正式链路仍是 socat 18443，回退链路仍是 gost 8443，本计划不会关闭 gost，也不会让 socat 接管 8443。</span>
        </CollapsibleWarning>
        <div className="local-plan-layout">
          <div className="readonly-preflight-checklist">
            {readonlyPreflightItemSpecs.map((item) => (
              <div className="readonly-preflight-item" key={item.label}>
                <div className="status-row">
                  <strong>{item.label}</strong>
                  <span className={item.scope === "未来远程只读" ? "pill warn" : "pill ok"}>{item.scope}</span>
                </div>
                <span>{item.detail}</span>
              </div>
            ))}
          </div>
          <div className="local-plan-summary">
            <div className="status-row">
              <h4>只读预检审批摘要</h4>
              <div className="route-card-actions">
                <button
                  className="secondary compact"
                  disabled={readonlyPreflightLoading}
                  type="button"
                  onClick={() => void generateReadonlyPreflightPlan()}
                >
                  {readonlyPreflightLoading ? "校验中" : "校验只读预检计划"}
                </button>
                <button
                  className="primary compact"
                  disabled={!readonlyPreflightReady || remotePreflightLoading}
                  type="button"
                  onClick={() => void runTransitReadonlyPreflightCommand()}
                >
                  {remotePreflightLoading ? "处理中" : "执行远程只读预检"}
                </button>
                {remotePreflightCommand ? (
                  <button
                    className="secondary compact"
                    disabled={remotePreflightLoading}
                    type="button"
                    onClick={() => void refreshTransitReadonlyPreflightCommand()}
                  >
                    刷新命令状态
                  </button>
                ) : null}
                <button className="secondary compact" type="button" onClick={() => void copyReadonlyPreflightSummary()}>
                  {preflightSummaryCopied ? "已复制" : "复制摘要"}
                </button>
              </div>
            </div>
            <div className="local-plan-checks">
              <label className="check-row">
                <input
                  checked={preflightHealthConfirmed}
                  type="checkbox"
                  onChange={(event) => {
                    setPreflightHealthConfirmed(event.target.checked);
                    setPreflightSummaryCopied(false);
                  }}
                />
                <span>已确认本地 health 正常，且 pending / running tasks 为 0</span>
              </label>
              <label className="check-row">
                <input
                  checked={preflightBoundaryAcknowledged}
                  type="checkbox"
                  onChange={(event) => {
                    setPreflightBoundaryAcknowledged(event.target.checked);
                    setPreflightSummaryCopied(false);
                  }}
                />
                <span>我确认这只是只读预检计划，不会创建真实转发、不会修改 node.share_link、不会做 cutover</span>
              </label>
              <label className="check-row">
                <input
                  checked={preflightWorkbuddyBoundaryConfirmed}
                  type="checkbox"
                  onChange={(event) => {
                    setPreflightWorkbuddyBoundaryConfirmed(event.target.checked);
                    setPreflightSummaryCopied(false);
                  }}
                />
                <span>我确认远程只读预检只通过 Worker allowlist 执行固定检查，不接受任意 shell</span>
              </label>
            </div>
            <div className="detail-grid">
              <span>预检结论</span>
              <strong>{readonlyPreflightStatusLabel}</strong>
              <span>中转资源</span>
              <strong>{planResource?.name ?? "-"}</strong>
              <span>落地节点</span>
              <strong>{planNode?.node_name ?? "-"}</strong>
              <span>计划端口</span>
              <strong>{planListenPort || "-"}</strong>
              <span>落地端口</span>
              <strong>{planTargetPortNumber ?? "-"}</strong>
            </div>
            {readonlyPreflightIssues.length > 0 ? (
              <div className="failure-box">
                <strong>不通过原因</strong>
                {readonlyPreflightIssues.map((issue) => (
                  <span key={issue}>{issue}</span>
                ))}
              </div>
            ) : (
              <div className="warning-box">
                <strong>就绪只代表可进入审批</strong>
                <span>当前仅可进入远程只读预检审批；仍不得执行 SSH、不得创建真实转发、不得新增监听端口。</span>
              </div>
            )}
            <pre className="local-plan-output">{readonlyPreflightSummaryText}</pre>
            {readonlyPreflightApiMessage ? <p className="message">{readonlyPreflightApiMessage}</p> : null}
            {remotePreflightMessage ? <p className="message">{remotePreflightMessage}</p> : null}
            {readonlyPreflightPlan ? (
              <div className="readonly-preflight-api-result">
                <div className="status-row">
                  <div>
                    <h4>后端 no-op 预检计划结果</h4>
                    <p className="message">来自 POST /api/transit-routes/readonly-preflight-plan。该接口不执行远程操作。</p>
                  </div>
                  <span
                    className={`pill ${preflightStatusClass(
                      readonlyPreflightPlan.status,
                      readonlyPreflightPlan.ready,
                    )}`}
                  >
                      {preflightPlanStatusLabel(readonlyPreflightPlan.status, readonlyPreflightPlan.ready)}
                  </span>
                </div>
                <div className="detail-grid">
                  <span>是否就绪</span>
                  <strong>{booleanLabel(readonlyPreflightPlan.ready)}</strong>
                  <span>是否阻塞</span>
                  <strong>{booleanLabel(readonlyPreflightPlan.blocked)}</strong>
                  <span>摘要</span>
                  <strong>{readonlyPreflightPlan.summary}</strong>
                  <span>下一步</span>
                  <strong>{readonlyPreflightPlan.next_action}</strong>
                </div>
                {readonlyPreflightPlan.ready ? (
                  <div className="warning-box">
                    <strong>就绪只代表可进入只读预检审批</strong>
                    <span>远程命令、真实转发创建和 node.share_link 修改仍未授权。</span>
                    <span>远程只读预检只执行固定 allowlist 检查；真实转发创建和 cutover 仍未授权。</span>
                  </div>
                ) : (
                  <div className="failure-box">
                    <strong>不通过 / 阻塞原因</strong>
                    <span>{readonlyPreflightPlan.summary}</span>
                    <span>{readonlyPreflightPlan.next_action}</span>
                  </div>
                )}
                <div className="readonly-preflight-checklist api-check-list">
                  {readonlyPreflightPlan.checks.map((check) => {
                    const isFuture = check.id.startsWith("future_") || check.status === "skipped";
                    return (
                      <div className="readonly-preflight-item api-check-card" key={check.id}>
                        <div className="status-row">
                          <div>
                            <strong>{check.label}</strong>
                            <p className="message">{check.id}</p>
                          </div>
                          <span className={`pill ${preflightCheckClass(check)}`}>
                            {preflightCheckStatusLabel(check)}
                          </span>
                        </div>
                        {isFuture ? (
                          <div className="warning-box">
                            <span>未来检查 / 本阶段不执行远程命令。</span>
                          </div>
                        ) : null}
                        <div className="detail-grid compact-detail-grid">
                          <span>检查分类</span>
                          <strong>{check.category}</strong>
                          <span>是否通过</span>
                          <strong>{booleanLabel(check.passed)}</strong>
                          <span>信息</span>
                          <strong>{check.message}</strong>
                          <span>证据摘要</span>
                          <strong>{check.evidence_summary}</strong>
                          <span>下一步</span>
                          <strong>{check.next_action}</strong>
                          <span>输出已脱敏</span>
                          <strong>{booleanLabel(check.sensitive_output_redacted)}</strong>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="warning-box">
                  <strong>安全边界</strong>
                  {readonlyPreflightPlan.safety_boundary.map((boundary) => (
                    <span key={boundary}>{boundary}</span>
                  ))}
                </div>
                <div>
                  <h4>脱敏摘要</h4>
                  <pre className="local-plan-output">{readonlyPreflightPlan.redacted_summary}</pre>
                </div>
              </div>
            ) : (
              <div className="warning-box">
                <strong>尚未调用后端 no-op API</strong>
                <span>点击“校验只读预检计划”后，只会生成本地无副作用计划，不会 SSH、不会远程命令、不会连接远程服务器。</span>
              </div>
            )}
            {renderRemoteReadonlyPreflightResult()}
          </div>
        </div>
        </div>
      </details>

      {forwardingMethod === "socat" ? (
        <CollapsibleWarning title="查看 socat 创建阶段边界">
          <strong>Stage 3.3.3-fix-b1：只创建 socat 测试转发。</strong>
          <span>创建前请先在云服务器安全组/云防火墙放行 TCP {listenPort}。</span>
          <span>同时确认服务器防火墙允许 TCP {listenPort}。</span>
          <span>禁止使用 22 / 8443 / 18443 / 20575。</span>
          <span>不替换 gost，不修改现有节点链接。</span>
          <span>本模式不生成 share_link；真实客户端链接仍需单独验收。</span>
        </CollapsibleWarning>
      ) : (
        <CollapsibleWarning title="查看 gost 创建阶段边界">
          <strong>Stage 3.3.3 只创建一条 gost TCP 转发规则。</strong>
          <span>会在香港服务器创建 systemd 转发服务，并监听一个新端口。</span>
          <span>不会自动开放云安全组，不会修改防火墙，不会写 iptables。</span>
          <span>不会连接或修改落地 VPS，不会影响现有直连链接。</span>
          <span>8443 保留给 gost 回退链路，18443 保留给当前 socat 正式链路，不能作为新转发端口。</span>
          <span>22 / 20575 也不能作为中转监听端口。删除功能不在本阶段。</span>
        </CollapsibleWarning>
      )}

      <div className="route-layout">
        <div className="form route-form">
          <label>
            中转资源
            <select value={selectedResourceId} onChange={(event) => setSelectedResourceId(event.target.value)}>
              {selectableResources.length === 0 ? <option value="">暂无可用 active server 资源</option> : null}
              {selectableResources.map((resource) => (
                <option key={resource.id} value={resource.id}>
                  {resource.name} / {displayValue(resource.entry_host)}
                </option>
              ))}
            </select>
          </label>
          <label>
            已启用节点
            <select value={selectedNodeId} onChange={(event) => setSelectedNodeId(event.target.value)}>
              {nodes.length === 0 ? <option value="">暂无已启用节点</option> : null}
              {nodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.node_name} / {displayValue(node.vps_ip)}:{displayValue(node.port)}
                </option>
              ))}
            </select>
          </label>
          <label>
            转发方式
            <select
              value={forwardingMethod}
              onChange={(event) => setForwardingMethod(event.target.value as ForwardingMethod)}
            >
              <option value="gost">gost</option>
              <option value="socat">socat</option>
            </select>
          </label>
          <label>
            规则名称
            <input value={routeName} onChange={(event) => setRouteName(event.target.value)} />
          </label>
          <label>
            监听端口
            <input
              min={1}
              max={65535}
              type="number"
              value={listenPort}
              onChange={(event) => updateListenPort(event.target.value)}
            />
            <span className={`field-hint ${listenPortError ? "danger-text" : ""}`}>
              {listenPortError ??
                "端口需为 1-65535 的整数。新增或变更端口前必须检查云安全组、云防火墙和服务器防火墙。"}
            </span>
          </label>
          <div className="warning-box wide-field">
            <strong>端口保护</strong>
            <span>8443：保留给 gost 回退链路，禁止作为新转发端口。</span>
            <span>18443：当前 socat 正式链路，禁止覆盖或复用。</span>
            <span>22 / 20575：SSH / 历史问题端口，禁止作为中转监听端口。</span>
          </div>
          <label className="check-row">
            <input
              checked={confirm}
              disabled={Boolean(listenPortError)}
              type="checkbox"
              onChange={(event) => setConfirm(event.target.checked)}
            />
            <span>
              我确认：创建单条转发不会修改 node.share_link，不是正式切换；已检查云服务器安全组、云防火墙和服务器防火墙允许 TCP{" "}
              {listenPort || "<待填写端口>"}。
            </span>
          </label>
          <label className="wide-field">
            SSH Key
            <textarea
              value={privateKeyText}
              onChange={(event) => setPrivateKeyText(event.target.value)}
              placeholder="粘贴香港服务器 SSH 私钥，仅临时加密写入 Redis。"
            />
          </label>
          <label>
            SSH Key 文件
            <input ref={fileInputRef} type="file" />
          </label>
          <label>
            Passphrase
            <input
              type="password"
              value={passphrase}
              onChange={(event) => setPassphrase(event.target.value)}
              placeholder="可选"
            />
          </label>
          <div className="wide-field">
            <button
              disabled={!confirm || Boolean(listenPortError)}
              type="button"
              onClick={() => void createTransitRoute()}
            >
              {forwardingMethod === "socat" ? "创建单条 socat 测试转发" : "创建单条 gost 转发"}
            </button>
            {listenPortError ? <p className="message danger-text">{listenPortError}</p> : null}
          </div>
        </div>

        <div className="route-summary">
          <h3>本次目标</h3>
          <div className="detail-grid">
            <span>中转入口</span>
            <strong>
              {displayValue(selectedResource?.entry_host)}:{displayValue(listenPort)}
            </strong>
            <span>目标节点</span>
            <strong>{selectedNode?.node_name ?? "-"}</strong>
            <span>落地目标</span>
            <strong>
              {displayValue(selectedNode?.vps_ip)}:{displayValue(selectedNode?.port)}
            </strong>
            <span>限制</span>
            <strong>单条 / {forwardingMethod} / 不改防火墙</strong>
          </div>
        </div>
      </div>

      {routes.length > 0 ? (
        <div className="route-management">
          <div className="status-row">
            <div>
              <h3>中转线路管理</h3>
              <p className="message">
                只读查看现有 gost / socat 转发线路；本区域不停止、不删除、不替换线路。socat 18443
                候选链接需要复制后手动在客户端测试。
              </p>
            </div>
          </div>
          <div className="diagnostic-credentials">
            <h4>诊断 / 重启 SSH 凭据</h4>
            <p className="message">只用于本次诊断或重启任务，临时加密写入 Redis；不会落库、不会回显、不会写入日志。</p>
            <div className="form route-form">
              <label className="wide-field">
                SSH Key
                <textarea
                  value={diagnosticPrivateKeyText}
                  onChange={(event) => setDiagnosticPrivateKeyText(event.target.value)}
                  placeholder="粘贴中转服务器 SSH 私钥，仅用于运行只读诊断。"
                />
              </label>
              <label>
                SSH Key 文件
                <input ref={diagnosticFileInputRef} type="file" />
              </label>
              <label>
                Passphrase
                <input
                  type="password"
                  value={diagnosticPassphrase}
                  onChange={(event) => setDiagnosticPassphrase(event.target.value)}
                  placeholder="可选"
                />
              </label>
            </div>
            <CollapsibleWarning title="查看诊断安全边界">
              <span>本区域展示诊断结果，不等于正式切换，也不会修改 node.share_link。</span>
              <span>运行只读诊断只会执行白名单诊断命令；重启按钮只对 socat 18443 测试链路开放。</span>
              <span>不提供停止、删除、创建入口，不允许操作 gost 8443 正式链路。</span>
              <span>诊断不会关闭 gost 8443，也不会让 socat 接管 8443。</span>
              <span>当前正式链路 socat 18443 不应被误删、覆盖或替换；正式链路变更必须进入单独审批阶段。</span>
              <span>新增或变更端口后诊断失败，优先检查云安全组、云防火墙和服务器防火墙。</span>
            </CollapsibleWarning>
            <p className="message">{diagnosticMessage}</p>
          </div>
          {routes.map((route) => {
            const routeDiagnosticActive = diagnosticRouteId === route.id;
            const listenCheck = routeDiagnosticActive ? diagnosticCheckFor("listen_check") : null;
            const serviceStatus = routeDiagnosticActive ? diagnosticCheckFor("service_status") : null;
            const targetConnectivity = routeDiagnosticActive ? diagnosticCheckFor("target_connectivity") : null;
            const processCheck = routeDiagnosticActive ? diagnosticCheckFor("process_check") : null;
            const diagnosticResultRecord = routeDiagnosticActive ? objectValue(diagnosticTask?.result_data) : null;
            const diagnosticWarnings = resultStrings(diagnosticResultRecord, "warnings");
            const diagnosticHints = resultStrings(diagnosticResultRecord, "hints");
            const diagnosticFailures = resultStrings(diagnosticResultRecord, "failures");
            const canExportSocatCandidateLink =
              isSocatTestRoute(route) &&
              Boolean(transitHostForRoute(route)) &&
              Boolean(activeNodeForRoute(route)?.has_share_link ?? activeNodeForRoute(route)?.share_link_present);
            return (
            <div className="route-card" key={route.id}>
              <div className="status-row">
                <div>
                  <h4>{route.name}</h4>
                  <p className="message">{routeBadge(route)}</p>
                </div>
                <div className="route-card-actions">
                  <span className={`pill ${route.status === "active" ? "ok" : "bad"}`}>
                    {routeStatusLabel(route.status)}
                  </span>
                  <button className="secondary compact" type="button" onClick={() => void diagnoseRoute(route)}>
                    运行只读诊断
                  </button>
                  {isSocatTestRoute(route) ? (
                    <button className="secondary compact" type="button" onClick={() => void restartSocatRoute(route)}>
                      重启测试链路
                    </button>
                  ) : null}
                </div>
              </div>
              <div className="detail-grid">
                <span>线路名称</span>
                <strong>{route.name}</strong>
                <span>转发方式</span>
                <strong>{route.forwarding_method}</strong>
                <span>监听地址 / 中转地址</span>
                <strong>{displayValue(transitHostForRoute(route))}</strong>
                <span>监听端口</span>
                <strong>{route.listen_port}</strong>
                <span>落地地址</span>
                <strong>{route.target_host}</strong>
                <span>落地端口</span>
                <strong>{route.target_port}</strong>
                <span>systemd 服务</span>
                <strong>{route.service_name}</strong>
                <span>本地测试命令</span>
                <strong>
                  nc -vz {displayValue(transitHostForRoute(route))} {route.listen_port}
                </strong>
              </div>
              <div className="route-flow">
                <div>
                  <span>本地客户端</span>
                  <strong>本地客户端</strong>
                </div>
                <span className="route-flow-arrow">→</span>
                <div>
                  <span>香港中转机</span>
                  <strong>
                    {displayValue(transitHostForRoute(route))}:{route.listen_port}
                  </strong>
                </div>
                <span className="route-flow-arrow">→</span>
                <div>
                  <span>落地机</span>
                  <strong>
                    {route.target_host}:{route.target_port}
                  </strong>
                </div>
                <span className="route-flow-arrow">→</span>
                <div>
                  <span>Xray Reality 节点</span>
                  <strong>{route.node_name ?? "已启用节点"}</strong>
                </div>
              </div>
              <CollapsibleWarning title="查看该线路端口提醒">
                <span>请确认云服务器安全组/云防火墙已放行 TCP {route.listen_port}。</span>
                <span>如果本地 nc timeout，优先检查云安全组/云防火墙和本机代理测试路径。</span>
                {route.forwarding_method === "socat" ? (
                  <span>socat 新增仍禁止使用 22 / 8443 / 18443 / 20575。</span>
                ) : null}
                {route.forwarding_method === "gost" && route.listen_port === 8443 ? (
                  <span>此链路保留为回退链路。此前与 Xray Reality 兼容性存在问题，不建议作为当前优先测试入口。</span>
                ) : null}
              </CollapsibleWarning>
              {isSocatTestRoute(route) ? (
                <div className="diagnostic-box">
                  <h5>socat 18443 候选正式链接</h5>
                  <p className="message">
                    此链接由当前 active Reality 节点的 share_link 派生，仅将 server 改为{" "}
                    {displayValue(transitHostForRoute(route))}，端口改为 {route.listen_port}。
                    UUID、flow、Reality、SNI、publicKey、shortId、fingerprint、spiderX 等参数保持不变。
                    本阶段不会写入数据库，不会替换 node.share_link。
                  </p>
                  <CollapsibleWarning title="查看候选链接安全提示">
                    <span>尚未正式 cutover：复制后请手动在客户端测试。</span>
                    <span>gost 8443 仍保留为回退链路，不会被停用或替换。</span>
                    <span>如果候选链接不可用，请继续使用原直连链接或 gost 8443 回退链路。</span>
                  </CollapsibleWarning>
                  {canExportSocatCandidateLink ? (
                    <div className="route-copy-row">
                      <span className="route-share-link">完整候选链接按需导出，默认不展示</span>
                      <button
                        className="secondary compact"
                        type="button"
                        onClick={() => void copySocatCandidateLink(route)}
                      >
                        {copiedSocatCandidateRouteId === route.id ? "已复制" : "复制 socat 18443 候选正式链接"}
                      </button>
                    </div>
                  ) : (
                    <div className="warning-box">
                      <span>当前 active 节点没有可导出的 share_link，暂不能生成候选正式链接。</span>
                    </div>
                  )}
                </div>
              ) : null}
              <div className="diagnostic-box">
                <div className="status-row">
                  <h5>诊断命令</h5>
                  <button className="secondary compact" type="button" onClick={() => void copyDiagnostics(route)}>
                    {copiedDiagnosticsRouteId === route.id ? "已复制" : "复制诊断命令"}
                  </button>
                </div>
                <div className="diagnostic-list">
                  {diagnosticCommandsForRoute(route).map((item) => (
                    <div className="diagnostic-row" key={`${route.id}-${item.label}`}>
                      <span>{item.label}</span>
                      <code>{item.command}</code>
                    </div>
                  ))}
                </div>
                <CollapsibleWarning title="查看诊断排查提示">
                  <span>nc timeout：优先检查云安全组/云防火墙 TCP {route.listen_port} 是否放行。</span>
                  <span>ss 没有监听：说明转发服务未启动或已退出。</span>
                  <span>目标 nc 不通：说明中转机到落地机不通。</span>
                  <span>本机开代理客户端时，nc/curl 测试路径可能被代理规则污染。</span>
                </CollapsibleWarning>
              </div>
              {routeDiagnosticActive && diagnosticTask ? (
                <div className="diagnostic-result">
                  <div className="status-row">
                    <div>
                      <h5>只读诊断结果</h5>
                      <p className="message">{diagnosticOutcome(diagnosticTask)}</p>
                    </div>
                    <span
                      className={`pill ${
                        diagnosticTask.result_data?.["passed"] === true
                          ? "ok"
                          : diagnosticTask.status === "failed" || diagnosticTask.result_data?.["passed"] === false
                            ? "bad"
                            : "warn"
                      }`}
                    >
                      {diagnosticTask.result_data?.["passed"] === true
                        ? "通过"
                        : diagnosticTask.result_data?.["passed"] === false
                          ? "失败"
                          : taskStatusLabel(diagnosticTask.status)}
                    </span>
                  </div>
                  <div className="detail-grid">
                    <span>任务状态</span>
                    <strong>{taskStatusLabel(diagnosticTask.status)}</strong>
                    <span>当前步骤</span>
                    <strong>{diagnosticTask.current_step ?? "-"}</strong>
                    <span>进度</span>
                    <strong>{diagnosticTask.progress}%</strong>
                    <span>错误码</span>
                    <strong>{diagnosticTask.error_code ?? "-"}</strong>
                    <span>错误摘要</span>
                    <strong>{diagnosticOutcome(diagnosticTask)}</strong>
                    <span>建议下一步</span>
                    <strong>
                      {diagnosticFailures[0] ??
                        diagnosticHints[0] ??
                        "如果结果不符合预期，请查看任务记录；真正远程复核需要 Workbuddy 或单独授权阶段。"}
                    </strong>
                  </div>

                  {diagnosticWarnings.length > 0 || diagnosticHints.length > 0 || diagnosticFailures.length > 0 ? (
                    <div className="diagnostic-guidance">
                      {diagnosticFailures.length > 0 ? (
                        <div className="failure-box">
                          <strong>失败原因摘要</strong>
                          {diagnosticFailures.map((failure) => (
                            <span key={failure}>{failure}</span>
                          ))}
                        </div>
                      ) : null}
                      {diagnosticHints.length > 0 ? (
                        <div className="warning-box">
                          <strong>建议下一步</strong>
                          {diagnosticHints.map((hint) => (
                            <span key={hint}>{hint}</span>
                          ))}
                        </div>
                      ) : null}
                      {diagnosticWarnings.length > 0 ? (
                        <div className="warning-box">
                          <strong>安全边界</strong>
                          {diagnosticWarnings.map((warning) => (
                            <span key={warning}>{warning}</span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  <div className="diagnostic-result-grid">
                    {diagnosticItemSpecs(diagnosticTask).map((item) => {
                      const check =
                        item.key === "listen_check"
                          ? listenCheck
                          : item.key === "service_status"
                            ? serviceStatus
                            : item.key === "target_connectivity"
                              ? targetConnectivity
                              : item.key === "process_check"
                                ? processCheck
                                : diagnosticCheckFor(item.key);
                      const checkRecord = objectValue(check);
                      const state = checkStatus(checkRecord);
                      return (
                        <div className="diagnostic-output" key={item.key}>
                          <div className="status-row">
                            <strong>{item.label}</strong>
                            <span className={`pill ${state.className}`}>{state.label}</span>
                          </div>
                          <div className="diagnostic-explainer">
                            <span>检查目的</span>
                            <strong>{item.purpose}</strong>
                            <span>失败含义</span>
                            <strong>{item.failureMeaning}</strong>
                            <span>下一步</span>
                            <strong>
                              {checkRecord?.["ok"] === true ? "无需处理，继续观察其它检查项。" : item.nextAction}
                            </strong>
                            <span>退出码</span>
                            <strong>{scalarValue(checkRecord, "exit_code")}</strong>
                          </div>
                          <code>
                            {typeof checkRecord?.["command"] === "string" ? redactString(checkRecord["command"]) : "-"}
                          </code>
                          <details className="diagnostic-output-details">
                            <summary>查看脱敏原始输出</summary>
                            <pre>{checkOutput(checkRecord)}</pre>
                          </details>
                        </div>
                      );
                    })}
                  </div>
                  {diagnosticLogs.length > 0 ? (
                    <div className="log-list">
                      {diagnosticLogs.map((log) => (
                        <div className="log-row" key={log.id}>
                          <span>{log.level}</span>
                          <span>{log.step ?? "-"}</span>
                          <span>{redactString(log.message)}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {route.share_link ? (
                <div className="route-copy-row">
                  <span className="route-share-link">{maskLink(route.share_link)}</span>
                  <button
                    className="secondary compact"
                    disabled={!route.share_link}
                    type="button"
                    onClick={() => void copyRouteLink(route)}
                  >
                    {copiedRouteId === route.id ? "已复制" : "复制中转链接"}
                  </button>
                </div>
              ) : null}
            </div>
            );
          })}
        </div>
      ) : null}

      {task ? (
        <div className="task-card">
          <div className="detail-grid">
            <span>任务类型</span>
            <strong>{task.task_type}</strong>
            <span>任务状态</span>
            <strong>{taskStatusLabel(task.status)}</strong>
            <span>当前步骤</span>
            <strong>{task.current_step ?? "-"}</strong>
            <span>进度</span>
            <strong>{task.progress}%</strong>
            <span>错误码</span>
            <strong>{task.error_code ?? "-"}</strong>
            <span>错误信息</span>
            <strong>{task.error_message ?? "-"}</strong>
          </div>

          {failures.length > 0 ? (
            <div className="failure-box">
              {failures.map((failure) => (
                <div key={failure}>{failure}</div>
              ))}
            </div>
          ) : null}
          {warnings.length > 0 ? (
            <div className="warning-box">
              {warnings.map((warning) => (
                <div key={warning}>{warning}</div>
              ))}
            </div>
          ) : null}

          {resultRoute ? (
            <div className="transit-read-result">
              <h4>中转规则结果</h4>
              <div className="detail-grid">
                <span>线路名称</span>
                <strong>{stringValue(resultRoute, "name")}</strong>
                <span>转发方式</span>
                <strong>{resultMethod}</strong>
                <span>监听端口</span>
                <strong>{resultListenPort}</strong>
                <span>落地目标</span>
                <strong>
                  {resultTargetHost}:{resultTargetPort}
                </strong>
                <span>systemd 服务</span>
                <strong>{stringValue(resultRoute, "service_name")}</strong>
                <span>状态</span>
                <strong>{routeStatusLabel(stringValue(resultRoute, "status"))}</strong>
                <span>gost</span>
                <strong>{stringValue(resultGost, "version")}</strong>
                <span>socat</span>
                <strong>{stringValue(resultSocat, "version")}</strong>
                <span>服务 active</span>
                <strong>{String(resultVerify?.["service_active"] ?? "-")}</strong>
                <span>监听状态</span>
                <strong>{String(resultVerify?.["listening"] ?? "-")}</strong>
              </div>
              {resultShareLink !== "-" ? (
                <>
                  <label className="share-export">
                    中转版分享链接
                    <textarea className="share-link-value" readOnly value={maskLink(resultShareLink)} />
                  </label>
                  <div className="transit-actions">
                    <button type="button" onClick={() => void copyTransitLink()}>
                      复制中转链接
                    </button>
                  </div>
                </>
              ) : null}
              {shouldShowSocatTestHint ? (
                <div className="warning-box">
                  <strong>创建后本地连通性校验</strong>
                  <span>在本机终端执行：</span>
                  <code>
                    nc -vz {resultTransitHost} {resultListenPort}
                  </code>
                  <span>如果 nc timeout，优先检查云安全组/云防火墙 TCP {resultListenPort} 是否放行。</span>
                  <span>如果本机开启代理客户端，请先确认测试路径没有被代理规则污染。</span>
                </div>
              ) : null}
              <p className="message">本阶段不提供删除转发入口，删除功能将在后续阶段实现。</p>
              {copied ? <p className="message">已复制中转版 vless:// 链接。</p> : null}
            </div>
          ) : null}

          {logs.length > 0 ? (
            <div className="log-list">
              {logs.map((log) => (
                <div className="log-row" key={log.id}>
                  <span>{log.level}</span>
                  <span>{log.step ?? "-"}</span>
                  <span>{log.message}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

        </div>
      </details>
      <p className="message">{message}</p>
    </section>
  );
}
