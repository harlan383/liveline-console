"use client";

import { useMemo, useState, type ReactNode } from "react";

import { ProductIcon } from "@/components/ProductIcons";
import {
  apiFetch,
  createTransitHaproxyRouteRealExecution,
  getHaproxyRuntimeDebugContext,
  requestTransitHaproxyRouteRealExecutionReadiness,
  type CsrfResult,
  type HaproxyRuntimeDebugContextResult,
  type HaproxyRuntimeDebugDryRunCandidate,
  type ReadonlyPreflightCheckItem,
  type TransitHaproxyRouteCreateRealExecutionRequest,
  type TransitHaproxyRouteCreateRealExecutionResult,
  type TransitHaproxyRouteRealExecutionReadinessResult,
} from "@/lib/api";

const FINAL_APPROVAL_TEXT = "CONFIRM_HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_ONLY";
const REAL_EXECUTION_STAGE = "Stage 3.3.139-new-transit-haproxy-route-create-real-execution";
const MANUAL_REAL_EXECUTION_CONFIRM = "CONFIRM_CREATE_HAPROXY_REAL_EXECUTION_COMMAND";

type DebugForm = {
  dry_run_command_id: string;
  transit_resource_id: string;
  landing_node_id: string;
  planned_listen_port: string;
  landing_target_host: string;
  landing_target_port: string;
  forwarding_method: "haproxy_tcp";
  route_name: string;
  route_display_name: string;
  approval_stage: string;
  final_approval_text: string;
  real_execution_text: string;
};

type Confirmations = {
  firewall_security_group_confirmed: boolean;
  cloud_firewall_confirmed: boolean;
  server_firewall_confirmed: boolean;
  no_cutover_confirmed: boolean;
  no_node_share_link_change_confirmed: boolean;
  no_transit_share_link_write_confirmed: boolean;
  no_full_client_link_confirmed: boolean;
};

type DebugJsonValue =
  | string
  | number
  | boolean
  | null
  | DebugJsonValue[]
  | {
      [key: string]: DebugJsonValue;
    };

const defaultForm: DebugForm = {
  dry_run_command_id: "",
  transit_resource_id: "",
  landing_node_id: "",
  planned_listen_port: "",
  landing_target_host: "",
  landing_target_port: "",
  forwarding_method: "haproxy_tcp",
  route_name: "",
  route_display_name: "",
  approval_stage: REAL_EXECUTION_STAGE,
  final_approval_text: FINAL_APPROVAL_TEXT,
  real_execution_text: "",
};

const defaultConfirmations: Confirmations = {
  firewall_security_group_confirmed: false,
  cloud_firewall_confirmed: false,
  server_firewall_confirmed: false,
  no_cutover_confirmed: false,
  no_node_share_link_change_confirmed: false,
  no_transit_share_link_write_confirmed: false,
  no_full_client_link_confirmed: false,
};

const safetyBoundaryItems = [
  "只读 readiness",
  "不 SSH",
  "不远程执行",
  "不创建 WorkerCommand",
  "不创建 TransitRoute",
  "不创建 HAProxy route",
  "不创建监听端口",
  "不修改防火墙 / 云防火墙 / 云安全组",
  "不读取或修改 nodes.share_link",
  "不写 transit_routes.share_link",
  "不 cutover",
];

const taskRows = [
  { time: "2026-06-30 11:24:18", name: "HAProxy runtime readiness", object: "中转线路 / 真实创建", status: "只读", result: "等待运行" },
  { time: "2026-06-30 10:51:03", name: "dry-run payload 校验", object: "WorkerCommand / payload", status: "成功", result: "动态端口审批通过" },
  { time: "2026-06-30 09:45:22", name: "real execution 安全边界", object: "HAProxy TCP / WorkerCommand", status: "部分成功", result: "等待人工确认" },
  { time: "2026-06-30 09:12:07", name: "share_link 暴露扫描", object: "响应 JSON / 日志", status: "成功", result: "敏感内容已脱敏" },
];

async function ensureCsrfToken() {
  const csrf = await apiFetch<CsrfResult>("/api/auth/csrf");
  if (!csrf.success) {
    throw new Error(csrf.message);
  }
  return csrf.data.csrf_token;
}

function expectedTextForPort(port: string) {
  const parsed = Number.parseInt(port, 10);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535) {
    return "CONFIRM_REAL_HAPROXY_ROUTE_CREATE_<planned_listen_port>";
  }
  return `CONFIRM_REAL_HAPROXY_ROUTE_CREATE_${parsed}`;
}

function isSafeRouteName(value: string) {
  return /^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/.test(value.trim());
}

function parsePort(value: string) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed) || String(parsed) !== value.trim() || parsed < 1 || parsed > 65535) {
    return null;
  }
  return parsed;
}

function redactDebugJson(value: unknown): DebugJsonValue {
  if (Array.isArray(value)) {
    return value.map((item) => redactDebugJson(item));
  }
  if (value && typeof value === "object") {
    const next: Record<string, DebugJsonValue> = {};
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      const lower = key.toLowerCase();
      if (key === "share_link") {
        next[key] = "[REDACTED_SHARE_LINK]";
        continue;
      }
      if (
        lower.includes("token") ||
        lower.includes("password") ||
        lower.includes("private_key") ||
        lower.includes("privatekey") ||
        lower.includes("secret") ||
        lower.includes("install_command")
      ) {
        next[key] = "[REDACTED]";
        continue;
      }
      next[key] = redactDebugJson(child);
    }
    return next;
  }
  if (typeof value === "string") {
    if (value.includes("vless://")) {
      return "[REDACTED_LINK]";
    }
    if (value.length > 160 && /token|secret|password|private/i.test(value)) {
      return "[REDACTED]";
    }
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean" || value === null) {
    return value;
  }
  return String(value);
}

function formatJson(value: unknown) {
  return JSON.stringify(redactDebugJson(value), null, 2);
}

function resultStatus(result: TransitHaproxyRouteRealExecutionReadinessResult | null) {
  if (!result) {
    return { label: "未运行", tone: "neutral" };
  }
  if (result.ready_for_real_execution) {
    return { label: "ready", tone: "success" };
  }
  return { label: "blocked", tone: "danger" };
}

function checkTone(check: ReadonlyPreflightCheckItem) {
  if (check.passed) {
    return "success";
  }
  if (check.category === "safety_boundary") {
    return "warning";
  }
  return "danger";
}

function Field({
  label,
  children,
  required = false,
}: {
  label: string;
  children: ReactNode;
  required?: boolean;
}) {
  return (
    <label className="advanced-debug-v2-field">
      <span>
        {required ? <b>*</b> : null}
        {label}
      </span>
      {children}
    </label>
  );
}

function CheckboxRow({
  checked,
  label,
  detail,
  onChange,
}: {
  checked: boolean;
  label: string;
  detail?: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="advanced-debug-v2-checkbox">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>
        <strong>{label}</strong>
        {detail ? <small>{detail}</small> : null}
      </span>
    </label>
  );
}

function SummaryMetric({
  icon,
  title,
  value,
  detail,
  tone,
}: {
  icon: string;
  title: string;
  value: string;
  detail: string;
  tone: "blue" | "green" | "orange" | "red";
}) {
  return (
    <article className="advanced-debug-v2-metric">
      <ProductIcon name={icon} tone={tone === "red" ? "red" : tone === "orange" ? "orange" : tone === "green" ? "green" : "blue"} />
      <div>
        <span>{title}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </article>
  );
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  const [collapsed, setCollapsed] = useState(title !== "Readiness Response JSON");

  return (
    <section className="advanced-debug-v2-json-block">
      <header>
        <strong>{title}</strong>
        <button type="button" className="ghost small" onClick={() => setCollapsed((next) => !next)}>
          {collapsed ? "展开" : "折叠"}
        </button>
      </header>
      {!collapsed ? <pre>{formatJson(value ?? {})}</pre> : null}
    </section>
  );
}

export function AdvancedHaproxyDebugPanel() {
  const [activeTab, setActiveTab] = useState<"interface" | "tasks" | "data" | "logs" | "safety">("tasks");
  const [form, setForm] = useState<DebugForm>(defaultForm);
  const [confirmations, setConfirmations] = useState<Confirmations>(defaultConfirmations);
  const [readinessResult, setReadinessResult] = useState<TransitHaproxyRouteRealExecutionReadinessResult | null>(null);
  const [realExecutionResult, setRealExecutionResult] = useState<TransitHaproxyRouteCreateRealExecutionResult | null>(null);
  const [loadingReadiness, setLoadingReadiness] = useState(false);
  const [submittingRealExecution, setSubmittingRealExecution] = useState(false);
  const [message, setMessage] = useState("");
  const [manualRealExecutionConfirm, setManualRealExecutionConfirm] = useState("");
  const [showTaskDetail, setShowTaskDetail] = useState(true);
  const [debugContext, setDebugContext] = useState<HaproxyRuntimeDebugContextResult | null>(null);
  const [loadingContext, setLoadingContext] = useState(false);
  const [selectedTransitResourceId, setSelectedTransitResourceId] = useState("");
  const [selectedLandingNodeId, setSelectedLandingNodeId] = useState("");
  const [selectedDryRunCommandId, setSelectedDryRunCommandId] = useState("");
  const [contextMessage, setContextMessage] = useState("");

  const expectedRealExecutionText = useMemo(
    () => readinessResult?.expected_real_execution_text ?? expectedTextForPort(form.planned_listen_port),
    [form.planned_listen_port, readinessResult?.expected_real_execution_text],
  );

  const currentStatus = resultStatus(readinessResult);
  const checks = readinessResult?.checks ?? [];
  const passedCount = checks.filter((check) => check.passed).length;
  const blockedCount = checks.length ? checks.length - passedCount : 0;

  const requestPayload = useMemo(() => buildPayloadOrNull(form, confirmations), [form, confirmations]);
  const formErrors = useMemo(() => validateForm(form, confirmations), [form, confirmations]);
  const allConfirmationsReady = Object.values(confirmations).every(Boolean);
  const canRunReadiness = formErrors.length === 0 && Boolean(requestPayload);
  const selectedDryRunCandidate = useMemo(
    () => debugContext?.haproxy_dry_run_commands.find((candidate) => candidate.id === selectedDryRunCommandId) ?? null,
    [debugContext?.haproxy_dry_run_commands, selectedDryRunCommandId],
  );
  const selectedTransitResource = useMemo(
    () => debugContext?.transit_resources.find((resource) => resource.id === selectedTransitResourceId) ?? null,
    [debugContext?.transit_resources, selectedTransitResourceId],
  );
  const selectedLandingNode = useMemo(
    () => debugContext?.landing_nodes.find((node) => node.id === selectedLandingNodeId) ?? null,
    [debugContext?.landing_nodes, selectedLandingNodeId],
  );
  const canCreateRealExecution =
    Boolean(requestPayload) &&
    Boolean(readinessResult?.ready_for_real_execution) &&
    form.real_execution_text.trim() === readinessResult?.expected_real_execution_text &&
    allConfirmationsReady &&
    manualRealExecutionConfirm.trim() === MANUAL_REAL_EXECUTION_CONFIRM &&
    !submittingRealExecution;

  function updateForm<K extends keyof DebugForm>(key: K, value: DebugForm[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setReadinessResult(null);
    setRealExecutionResult(null);
  }

  function updateConfirmation<K extends keyof Confirmations>(key: K, value: boolean) {
    setConfirmations((current) => ({ ...current, [key]: value }));
    setReadinessResult(null);
    setRealExecutionResult(null);
  }

  function clearForm() {
    setForm(defaultForm);
    setConfirmations(defaultConfirmations);
    setReadinessResult(null);
    setRealExecutionResult(null);
    setManualRealExecutionConfirm("");
    setMessage("");
    setContextMessage("");
  }

  async function copyText(text: string, successMessage: string) {
    try {
      await navigator.clipboard.writeText(text);
      setMessage(successMessage);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "复制失败，请手动复制。");
    }
  }

  async function runReadiness() {
    if (!requestPayload) {
      setMessage(formErrors[0] ?? "请先补齐参数。");
      return;
    }
    setLoadingReadiness(true);
    setMessage("正在运行 runtime readiness，只读检查不会创建 WorkerCommand。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await requestTransitHaproxyRouteRealExecutionReadiness(requestPayload, csrfToken);
      if (!result.success) {
        setMessage(result.message);
        return;
      }
      setReadinessResult(result.data);
      setMessage(result.data.ready_for_real_execution ? "Runtime readiness 已通过。" : "Runtime readiness 已返回阻塞项。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "运行 readiness 失败。");
    } finally {
      setLoadingReadiness(false);
    }
  }

  async function loadDebugContext() {
    setLoadingContext(true);
    setContextMessage("正在读取主控本地上下文；不会创建 WorkerCommand 或执行远程命令。");
    try {
      const result = await getHaproxyRuntimeDebugContext();
      if (!result.success) {
        setContextMessage(result.message);
        return;
      }
      setDebugContext(result.data);
      const firstCandidate = result.data.haproxy_dry_run_commands[0];
      if (firstCandidate) {
        setSelectedDryRunCommandId(firstCandidate.id);
        setSelectedTransitResourceId(firstCandidate.transit_resource_id ?? "");
        setSelectedLandingNodeId(firstCandidate.landing_node_id ?? "");
      } else {
        setSelectedDryRunCommandId("");
        setSelectedTransitResourceId(result.data.transit_resources[0]?.id ?? "");
        setSelectedLandingNodeId(result.data.landing_nodes[0]?.id ?? "");
      }
      setContextMessage(
        `已读取上下文：${result.data.transit_resources.length} 个中转资源，${result.data.landing_nodes.length} 个落地节点，${result.data.haproxy_dry_run_commands.length} 个 HAProxy dry-run 候选。`,
      );
    } catch (error) {
      setContextMessage(error instanceof Error ? error.message : "读取上下文失败。");
    } finally {
      setLoadingContext(false);
    }
  }

  function selectDryRunCandidate(candidateId: string) {
    setSelectedDryRunCommandId(candidateId);
    const candidate = debugContext?.haproxy_dry_run_commands.find((item) => item.id === candidateId);
    if (!candidate) {
      return;
    }
    setSelectedTransitResourceId(candidate.transit_resource_id ?? "");
    setSelectedLandingNodeId(candidate.landing_node_id ?? "");
  }

  function applyDebugContextCandidate(candidate: HaproxyRuntimeDebugDryRunCandidate | null) {
    if (!candidate) {
      setContextMessage("请先选择一个 HAProxy dry-run 候选。");
      return;
    }
    if (
      !candidate.transit_resource_id ||
      !candidate.landing_node_id ||
      !candidate.planned_listen_port ||
      !candidate.landing_target_host ||
      !candidate.landing_target_port ||
      !candidate.route_name
    ) {
      setContextMessage("选中的 dry-run 候选缺少必要字段，不能自动填充。");
      return;
    }
    const plannedListenPort = String(candidate.planned_listen_port);
    setForm({
      dry_run_command_id: candidate.id,
      transit_resource_id: candidate.transit_resource_id,
      landing_node_id: candidate.landing_node_id,
      planned_listen_port: plannedListenPort,
      landing_target_host: candidate.landing_target_host,
      landing_target_port: String(candidate.landing_target_port),
      forwarding_method: "haproxy_tcp",
      route_name: candidate.route_name,
      route_display_name: candidate.route_display_name ?? "",
      approval_stage: REAL_EXECUTION_STAGE,
      final_approval_text: FINAL_APPROVAL_TEXT,
      real_execution_text: expectedTextForPort(plannedListenPort),
    });
    setConfirmations(defaultConfirmations);
    setReadinessResult(null);
    setRealExecutionResult(null);
    setManualRealExecutionConfirm("");
    setContextMessage("已填充上下文字段；端口放行与安全确认仍需人工逐项确认。");
    setMessage("已从 HAProxy dry-run 候选填充 payload。请人工确认端口放行后再运行 readiness。");
  }

  async function submitRealExecution() {
    if (!requestPayload || !canCreateRealExecution) {
      setMessage("真实执行按钮仍受保护，请先完成 readiness、确认文本和二次确认。");
      return;
    }
    setSubmittingRealExecution(true);
    setMessage("正在创建受控 real execution WorkerCommand。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await createTransitHaproxyRouteRealExecution(requestPayload, csrfToken);
      if (!result.success) {
        setMessage(result.message);
        return;
      }
      setRealExecutionResult(result.data);
      setMessage(result.data.real_execution_command_created ? "Real execution WorkerCommand 已创建。" : result.data.summary);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "创建 real execution WorkerCommand 失败。");
    } finally {
      setSubmittingRealExecution(false);
    }
  }

  return (
    <section className="advanced-debug-v2">
      <div className="advanced-debug-v2-breadcrumb">
        <ProductIcon name="dashboard" tone="slate" />
        <span>/</span>
        <strong>高级调试</strong>
        <span>/</span>
        <strong>HAProxy Runtime Readiness</strong>
        <div className="advanced-debug-v2-env">开发环境</div>
      </div>

      <header className="advanced-debug-v2-header">
        <div>
          <h1>高级调试</h1>
          <p>仅技术支持使用。用于真实创建 HAProxy 中转线路前的只读检查，不会直接创建 Worker command、监听端口或修改防火墙。</p>
        </div>
      </header>

      <nav className="advanced-debug-v2-tabs" aria-label="高级调试模块">
        {[
          ["interface", "接口调试"],
          ["tasks", "任务调试"],
          ["data", "数据校验"],
          ["logs", "日志查看"],
          ["safety", "执行安全"],
        ].map(([key, label]) => (
          <button
            type="button"
            key={key}
            className={activeTab === key ? "active" : ""}
            onClick={() => setActiveTab(key as typeof activeTab)}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="advanced-debug-v2-metrics">
        <SummaryMetric icon="debug" title="当前模式" value="只读" detail="不会修改线上数据" tone="blue" />
        <SummaryMetric icon="tasks" title="远程执行" value="关闭" detail="禁止远程命令执行" tone="green" />
        <SummaryMetric icon="tasks" title="阻塞项" value={String(blockedCount)} detail={checks.length ? "来自 readiness checks" : "等待检查"} tone="orange" />
        <SummaryMetric icon="settings" title="执行状态" value={currentStatus.label} detail="后端 readiness 为准" tone={currentStatus.tone === "danger" ? "red" : currentStatus.tone === "success" ? "green" : "blue"} />
      </div>

      <div className="advanced-debug-v2-layout">
        <main className="advanced-debug-v2-main">
          <section className="advanced-debug-v2-card advanced-debug-v2-safety-bar">
            <header>
              <ProductIcon name="settings" tone="green" />
              <div>
                <h2>安全边界</h2>
                <p>运行 readiness 只读取主控本地数据并校验 payload，不会触发远程或线路变更。</p>
              </div>
            </header>
            <div className="advanced-debug-v2-boundary-grid">
              {safetyBoundaryItems.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
          </section>

          <section className="advanced-debug-v2-card advanced-debug-v2-context">
            <header className="advanced-debug-v2-card-title">
              <div>
                <h2>读取上下文</h2>
                <p>从主控本地记录读取中转资源、落地节点和近期 HAProxy dry-run 候选；只填充 payload 字段，不自动勾选确认项。</p>
              </div>
              <button type="button" className="ghost small" onClick={loadDebugContext} disabled={loadingContext}>
                {loadingContext ? "读取中..." : "刷新上下文"}
              </button>
            </header>

            <div className="advanced-debug-v2-context-grid">
              <label>
                <span>中转资源</span>
                <select value={selectedTransitResourceId} onChange={(event) => setSelectedTransitResourceId(event.target.value)}>
                  <option value="">未选择</option>
                  {debugContext?.transit_resources.map((resource) => (
                    <option key={resource.id} value={resource.id}>
                      {resource.name} / {resource.entry_host ?? "no-entry"} / {resource.worker_online ? "worker online" : resource.worker_runtime_status ?? "worker unknown"}
                    </option>
                  ))}
                </select>
                {selectedTransitResource ? (
                  <small>
                    Worker：{selectedTransitResource.worker_id ?? "-"} / {selectedTransitResource.worker_version ?? "-"}
                  </small>
                ) : null}
              </label>

              <label>
                <span>落地节点</span>
                <select value={selectedLandingNodeId} onChange={(event) => setSelectedLandingNodeId(event.target.value)}>
                  <option value="">未选择</option>
                  {debugContext?.landing_nodes.map((node) => (
                    <option key={node.id} value={node.id}>
                      {node.node_name} / {node.target_host ?? "no-host"}:{node.target_port ?? "-"} / {node.status}
                    </option>
                  ))}
                </select>
                {selectedLandingNode ? (
                  <small>
                    服务：{selectedLandingNode.service_status ?? "-"} / 客户端配置：{selectedLandingNode.share_link_present ? "已生成" : "未生成"}
                  </small>
                ) : null}
              </label>

              <label>
                <span>HAProxy dry-run 候选</span>
                <select value={selectedDryRunCommandId} onChange={(event) => selectDryRunCandidate(event.target.value)}>
                  <option value="">未选择</option>
                  {debugContext?.haproxy_dry_run_commands.map((candidate) => (
                    <option key={candidate.id} value={candidate.id}>
                      {candidate.status} / {candidate.route_name ?? "haproxy route"} / {candidate.planned_listen_port ?? "-"} → {candidate.landing_target_port ?? "-"}
                    </option>
                  ))}
                </select>
                {selectedDryRunCandidate ? (
                  <small>
                    dry_run_command_id：{selectedDryRunCandidate.id} / status：{selectedDryRunCandidate.status}
                  </small>
                ) : null}
              </label>
            </div>

            {selectedDryRunCandidate ? (
              <div className="advanced-debug-v2-context-summary">
                <div>
                  <span>监听端口</span>
                  <strong>{selectedDryRunCandidate.planned_listen_port ?? "-"}</strong>
                </div>
                <div>
                  <span>落地目标</span>
                  <strong>
                    {selectedDryRunCandidate.landing_target_host ?? "-"}:{selectedDryRunCandidate.landing_target_port ?? "-"}
                  </strong>
                </div>
                <div>
                  <span>route_name</span>
                  <strong>{selectedDryRunCandidate.route_name ?? "-"}</strong>
                </div>
                <div>
                  <span>显示名称</span>
                  <strong>{selectedDryRunCandidate.route_display_name ?? "-"}</strong>
                </div>
              </div>
            ) : null}

            {selectedDryRunCandidate && selectedDryRunCandidate.status !== "succeeded" ? (
              <div className="advanced-debug-v2-context-warning">
                选中的 dry-run 当前不是 succeeded；填充后 readiness 会继续按后端规则校验并可能 blocked。
              </div>
            ) : null}

            <div className="advanced-debug-v2-context-actions">
              <button type="button" onClick={() => applyDebugContextCandidate(selectedDryRunCandidate)} disabled={!selectedDryRunCandidate}>
                填充到 Readiness Payload
              </button>
              <span>不会自动勾选云安全组、云防火墙、服务器防火墙或 real execution 确认。</span>
            </div>

            {contextMessage ? <div className="advanced-debug-v2-context-message">{contextMessage}</div> : null}
          </section>

          <section className="advanced-debug-v2-card">
            <header className="advanced-debug-v2-card-title">
              <div>
                <h2>请求参数</h2>
                <p>使用与 HAProxy real execution 相同的 payload；先运行只读 readiness，再决定是否创建 WorkerCommand。</p>
              </div>
              <button
                type="button"
                className="ghost small"
                onClick={() => copyText(formatJson(requestPayload ?? buildDraftPayload(form, confirmations)), "Payload 已复制。")}
              >
                复制 Payload
              </button>
            </header>

            <div className="advanced-debug-v2-form-grid">
              <Field label="dry_run_command_id" required>
                <input value={form.dry_run_command_id} onChange={(event) => updateForm("dry_run_command_id", event.target.value)} />
              </Field>
              <Field label="transit_resource_id" required>
                <input value={form.transit_resource_id} onChange={(event) => updateForm("transit_resource_id", event.target.value)} />
              </Field>
              <Field label="landing_node_id" required>
                <input value={form.landing_node_id} onChange={(event) => updateForm("landing_node_id", event.target.value)} />
              </Field>
              <Field label="forwarding_method" required>
                <select value={form.forwarding_method} onChange={(event) => updateForm("forwarding_method", event.target.value as "haproxy_tcp")}>
                  <option value="haproxy_tcp">haproxy_tcp</option>
                </select>
              </Field>
              <Field label="planned_listen_port" required>
                <input
                  inputMode="numeric"
                  placeholder="例如：25867"
                  value={form.planned_listen_port}
                  onChange={(event) => updateForm("planned_listen_port", event.target.value)}
                />
              </Field>
              <Field label="landing_target_port" required>
                <input
                  inputMode="numeric"
                  placeholder="例如：28917"
                  value={form.landing_target_port}
                  onChange={(event) => updateForm("landing_target_port", event.target.value)}
                />
              </Field>
              <Field label="landing_target_host" required>
                <input placeholder="落地 VPS IP" value={form.landing_target_host} onChange={(event) => updateForm("landing_target_host", event.target.value)} />
              </Field>
              <Field label="route_name" required>
                <input placeholder="haproxy-tcp-25867" value={form.route_name} onChange={(event) => updateForm("route_name", event.target.value)} />
              </Field>
              <Field label="route_display_name">
                <input placeholder="可选显示名称" value={form.route_display_name} onChange={(event) => updateForm("route_display_name", event.target.value)} />
              </Field>
              <Field label="approval_stage" required>
                <input value={form.approval_stage} onChange={(event) => updateForm("approval_stage", event.target.value)} />
              </Field>
              <Field label="final_approval_text" required>
                <input value={form.final_approval_text} onChange={(event) => updateForm("final_approval_text", event.target.value)} />
              </Field>
              <Field label="real_execution_text" required>
                <div className="advanced-debug-v2-inline-control">
                  <input value={form.real_execution_text} onChange={(event) => updateForm("real_execution_text", event.target.value)} />
                  <button type="button" className="ghost small" onClick={() => updateForm("real_execution_text", expectedRealExecutionText)}>
                    填入预期文本
                  </button>
                </div>
                <small>预期格式：{expectedRealExecutionText}</small>
              </Field>
            </div>
          </section>

          <section className="advanced-debug-v2-card advanced-debug-v2-confirm-grid">
            <div>
              <h2>端口放行确认</h2>
              <CheckboxRow
                checked={confirmations.firewall_security_group_confirmed}
                label={`我已确认云服务器安全组已放行 ${form.planned_listen_port || "planned_listen_port"}/TCP`}
                detail="这里只记录人工确认，不修改云安全组。"
                onChange={(checked) => updateConfirmation("firewall_security_group_confirmed", checked)}
              />
              <CheckboxRow
                checked={confirmations.cloud_firewall_confirmed}
                label={`我已确认云防火墙已放行 ${form.planned_listen_port || "planned_listen_port"}/TCP`}
                onChange={(checked) => updateConfirmation("cloud_firewall_confirmed", checked)}
              />
              <CheckboxRow
                checked={confirmations.server_firewall_confirmed}
                label={`我已确认服务器系统防火墙已放行 ${form.planned_listen_port || "planned_listen_port"}/TCP`}
                onChange={(checked) => updateConfirmation("server_firewall_confirmed", checked)}
              />
            </div>
            <div>
              <h2>执行安全确认</h2>
              <CheckboxRow
                checked={confirmations.no_cutover_confirmed}
                label="我确认本阶段不 cutover"
                onChange={(checked) => updateConfirmation("no_cutover_confirmed", checked)}
              />
              <CheckboxRow
                checked={confirmations.no_node_share_link_change_confirmed}
                label="我确认不读取或修改 nodes.share_link"
                onChange={(checked) => updateConfirmation("no_node_share_link_change_confirmed", checked)}
              />
              <CheckboxRow
                checked={confirmations.no_transit_share_link_write_confirmed}
                label="我确认不写入 transit_routes.share_link"
                onChange={(checked) => updateConfirmation("no_transit_share_link_write_confirmed", checked)}
              />
              <CheckboxRow
                checked={confirmations.no_full_client_link_confirmed}
                label="我确认不导出完整客户端链接"
                onChange={(checked) => updateConfirmation("no_full_client_link_confirmed", checked)}
              />
            </div>
          </section>

          {formErrors.length ? (
            <section className="advanced-debug-v2-card advanced-debug-v2-error-list">
              <strong>表单预检</strong>
              {formErrors.map((error) => (
                <span key={error}>{error}</span>
              ))}
            </section>
          ) : null}

          <section className="advanced-debug-v2-actions">
            <button type="button" onClick={runReadiness} disabled={!canRunReadiness || loadingReadiness}>
              {loadingReadiness ? "运行中..." : "运行 Runtime Readiness"}
            </button>
            <button type="button" className="secondary" onClick={() => copyText(formatJson(requestPayload ?? buildDraftPayload(form, confirmations)), "Payload 已复制。")}>
              复制 Payload
            </button>
            <button type="button" className="ghost" onClick={clearForm}>
              清空
            </button>
          </section>

          {message ? <div className="advanced-debug-v2-message">{message}</div> : null}

          <section className="advanced-debug-v2-card">
            <header className="advanced-debug-v2-card-title">
              <div>
                <h2>Readiness 结果</h2>
                <p>结果完全以后端 `/api/transit-routes/haproxy-route-real-execution-readiness` 返回为准。</p>
              </div>
              <span className={`advanced-debug-v2-status ${currentStatus.tone}`}>{currentStatus.label}</span>
            </header>

            <div className="advanced-debug-v2-result-grid">
              {[
                ["ready_for_real_execution", String(Boolean(readinessResult?.ready_for_real_execution))],
                ["blocked", String(Boolean(readinessResult?.blocked))],
                ["expected_real_execution_text", readinessResult?.expected_real_execution_text ?? expectedRealExecutionText],
                ["target_worker_id", readinessResult?.target_worker_id ?? "-"],
                ["target_worker_version", readinessResult?.target_worker_version ?? "-"],
                ["minimum_supported_worker_version", readinessResult?.minimum_supported_worker_version ?? "-"],
                ["planned_service_name", readinessResult?.planned_service_name ?? "-"],
                ["planned_listen_port", readinessResult?.planned_listen_port ? String(readinessResult.planned_listen_port) : "-"],
                ["landing_target_host", readinessResult?.landing_target_host ?? "-"],
                ["landing_target_port", readinessResult?.landing_target_port ? String(readinessResult.landing_target_port) : "-"],
                ["route_name", readinessResult?.route_name ?? "-"],
              ].map(([label, value]) => (
                <div key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>

            {readinessResult ? (
              <div className="advanced-debug-v2-summary">
                <strong>{readinessResult.summary}</strong>
                <p>{readinessResult.next_action}</p>
              </div>
            ) : null}
          </section>

          <section className="advanced-debug-v2-card">
            <header className="advanced-debug-v2-card-title">
              <div>
                <h2>Checks</h2>
                <p>passed 使用绿色，blocked 使用红色，安全边界使用灰色 / 黄色辅助识别。</p>
              </div>
              <span>{passedCount}/{checks.length || 0} passed</span>
            </header>

            <div className="advanced-debug-v2-check-list">
              {checks.length ? (
                checks.map((check) => (
                  <article key={check.id} className={`advanced-debug-v2-check ${checkTone(check)}`}>
                    <span>{check.passed ? "通过" : "阻塞"}</span>
                    <div>
                      <strong>{check.label}</strong>
                      <code>{check.id}</code>
                      <p>{check.message}</p>
                      <small>{check.next_action}</small>
                      {check.evidence_summary ? <em>evidence: {check.evidence_summary}</em> : null}
                      <em>category: {check.category}</em>
                    </div>
                  </article>
                ))
              ) : (
                <div className="advanced-debug-v2-empty">尚未运行 readiness。</div>
              )}
            </div>
          </section>

          <section className="advanced-debug-v2-card advanced-debug-v2-danger-zone">
            <header className="advanced-debug-v2-card-title">
              <div>
                <h2>创建 Real Execution Worker Command</h2>
                <p>这个操作只创建 WorkerCommand，不直接创建 HAProxy route，不直接绑定监听端口，不修改防火墙，不 cutover。</p>
              </div>
              <span className="advanced-debug-v2-status warning">强保护</span>
            </header>
            <Field label="二次确认文本">
              <input
                value={manualRealExecutionConfirm}
                placeholder={MANUAL_REAL_EXECUTION_CONFIRM}
                onChange={(event) => setManualRealExecutionConfirm(event.target.value)}
              />
            </Field>
            <button type="button" className="danger" disabled={!canCreateRealExecution} onClick={submitRealExecution}>
              {submittingRealExecution ? "提交中..." : "创建 Real Execution Worker Command"}
            </button>
            {realExecutionResult ? (
              <div className="advanced-debug-v2-summary">
                <strong>{realExecutionResult.summary}</strong>
                <p>{realExecutionResult.next_action}</p>
                <p>command.id：{realExecutionResult.command?.id ?? "-"}</p>
                <p>command.status：{realExecutionResult.command?.status ?? "-"}</p>
              </div>
            ) : null}
          </section>
        </main>

        <aside className="advanced-debug-v2-side">
          <section className="advanced-debug-v2-card">
            <h2>调试建议</h2>
            <ul className="advanced-debug-v2-advice">
              <li>先运行只读 readiness，确认 payload 与 dry-run 一致。</li>
              <li>失败后查看 checks 与 JSON，不要直接重复真实执行。</li>
              <li>动态端口必须使用后端返回的 expected_real_execution_text。</li>
              <li>任何真实执行都必须再次确认安全边界。</li>
            </ul>
          </section>

          <section className="advanced-debug-v2-card">
            <h2>调试任务列表</h2>
            <table className="advanced-debug-v2-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>任务名称</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {taskRows.map((task) => (
                  <tr key={`${task.time}-${task.name}`}>
                    <td>{task.time}</td>
                    <td>
                      <strong>{task.name}</strong>
                      <span>{task.object}</span>
                    </td>
                    <td>
                      <span className={`advanced-debug-v2-pill ${task.status === "成功" ? "success" : task.status === "部分成功" ? "warning" : "info"}`}>
                        {task.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <button type="button" className="ghost small" onClick={() => setShowTaskDetail((next) => !next)}>
              {showTaskDetail ? "隐藏详情" : "查看详情"}
            </button>
          </section>

          {showTaskDetail ? (
            <section className="advanced-debug-v2-card">
              <h2>任务调试详情</h2>
              <div className="advanced-debug-v2-log">
                <p><span>INFO</span>[TaskRunner] 任务开始，模式：只读 readiness</p>
                <p><span>INFO</span>[Params] 校验请求参数与审批文本</p>
                <p><span>INFO</span>[Safety] 不创建 WorkerCommand / 不绑定监听端口</p>
                <p><span>WARN</span>[Gate] 如果 blocked，请先处理 checks</p>
              </div>
            </section>
          ) : null}

          <JsonBlock title="Context Autofill JSON" value={debugContext} />
          <JsonBlock title="Request Payload JSON" value={requestPayload ?? buildDraftPayload(form, confirmations)} />
          <JsonBlock title="Readiness Response JSON" value={readinessResult} />
          <JsonBlock title="Real Execution Response JSON" value={realExecutionResult} />
        </aside>
      </div>
    </section>
  );
}

function buildPayloadOrNull(
  form: DebugForm,
  confirmations: Confirmations,
): TransitHaproxyRouteCreateRealExecutionRequest | null {
  const plannedListenPort = parsePort(form.planned_listen_port);
  const landingTargetPort = parsePort(form.landing_target_port);
  if (!plannedListenPort || !landingTargetPort) {
    return null;
  }
  if (
    !form.dry_run_command_id.trim() ||
    !form.transit_resource_id.trim() ||
    !form.landing_node_id.trim() ||
    !form.landing_target_host.trim() ||
    !form.route_name.trim() ||
    !form.approval_stage.trim() ||
    !form.final_approval_text.trim() ||
    !form.real_execution_text.trim()
  ) {
    return null;
  }
  if (!isSafeRouteName(form.route_name)) {
    return null;
  }
  if (!Object.values(confirmations).every(Boolean)) {
    return null;
  }
  return {
    dry_run_command_id: form.dry_run_command_id.trim(),
    transit_resource_id: form.transit_resource_id.trim(),
    landing_node_id: form.landing_node_id.trim(),
    planned_listen_port: plannedListenPort,
    landing_target_host: form.landing_target_host.trim(),
    landing_target_port: landingTargetPort,
    forwarding_method: "haproxy_tcp",
    route_name: form.route_name.trim(),
    route_display_name: form.route_display_name.trim() || null,
    approval_stage: form.approval_stage.trim(),
    final_approval_text: form.final_approval_text.trim(),
    real_execution_text: form.real_execution_text.trim(),
    firewall_security_group_confirmed: confirmations.firewall_security_group_confirmed,
    cloud_firewall_confirmed: confirmations.cloud_firewall_confirmed,
    server_firewall_confirmed: confirmations.server_firewall_confirmed,
    no_cutover_confirmed: confirmations.no_cutover_confirmed,
    no_node_share_link_change_confirmed: confirmations.no_node_share_link_change_confirmed,
    no_full_client_link_confirmed: confirmations.no_full_client_link_confirmed,
  };
}

function buildDraftPayload(form: DebugForm, confirmations: Confirmations) {
  return {
    dry_run_command_id: form.dry_run_command_id,
    transit_resource_id: form.transit_resource_id,
    landing_node_id: form.landing_node_id,
    planned_listen_port: form.planned_listen_port,
    landing_target_host: form.landing_target_host,
    landing_target_port: form.landing_target_port,
    forwarding_method: form.forwarding_method,
    route_name: form.route_name,
    route_display_name: form.route_display_name || null,
    approval_stage: form.approval_stage,
    final_approval_text: form.final_approval_text,
    real_execution_text: form.real_execution_text,
    firewall_security_group_confirmed: confirmations.firewall_security_group_confirmed,
    cloud_firewall_confirmed: confirmations.cloud_firewall_confirmed,
    server_firewall_confirmed: confirmations.server_firewall_confirmed,
    no_cutover_confirmed: confirmations.no_cutover_confirmed,
    no_node_share_link_change_confirmed: confirmations.no_node_share_link_change_confirmed,
    no_transit_share_link_write_confirmed: confirmations.no_transit_share_link_write_confirmed,
    no_full_client_link_confirmed: confirmations.no_full_client_link_confirmed,
  };
}

function validateForm(form: DebugForm, confirmations: Confirmations) {
  const errors: string[] = [];
  const requiredFields: Array<[keyof DebugForm, string]> = [
    ["dry_run_command_id", "dry_run_command_id 不能为空"],
    ["transit_resource_id", "transit_resource_id 不能为空"],
    ["landing_node_id", "landing_node_id 不能为空"],
    ["planned_listen_port", "planned_listen_port 不能为空"],
    ["landing_target_host", "landing_target_host 不能为空"],
    ["landing_target_port", "landing_target_port 不能为空"],
    ["route_name", "route_name 不能为空"],
    ["approval_stage", "approval_stage 不能为空"],
    ["final_approval_text", "final_approval_text 不能为空"],
    ["real_execution_text", "real_execution_text 不能为空"],
  ];
  for (const [key, message] of requiredFields) {
    if (!form[key].trim()) {
      errors.push(message);
    }
  }
  if (form.planned_listen_port && parsePort(form.planned_listen_port) === null) {
    errors.push("planned_listen_port 必须是 1-65535 的整数");
  }
  if (form.landing_target_port && parsePort(form.landing_target_port) === null) {
    errors.push("landing_target_port 必须是 1-65535 的整数");
  }
  if (form.route_name && !isSafeRouteName(form.route_name)) {
    errors.push("route_name 只能包含字母、数字、点、下划线、短横线，且必须以字母或数字开头");
  }
  if (form.forwarding_method !== "haproxy_tcp") {
    errors.push("forwarding_method 只能是 haproxy_tcp");
  }
  if (!Object.values(confirmations).every(Boolean)) {
    errors.push("运行 readiness 前必须完成全部端口放行和安全确认");
  }
  return errors;
}
