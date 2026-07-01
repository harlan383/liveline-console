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
  type HaproxyRuntimeDebugIntegrityCheck,
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

type HaproxyResourceRebuildPlanAction = {
  id: string;
  title: string;
  severity: "info" | "warning" | "danger";
  description: string;
  steps: string[];
};

type HaproxyResourceRebuildPlan = {
  status: "ready" | "blocked" | "no_candidate";
  summary: string;
  candidate_summary: Array<{ label: string; value: string }>;
  blocking_checks: HaproxyRuntimeDebugIntegrityCheck[];
  required_actions: HaproxyResourceRebuildPlanAction[];
  recommended_next_stage: string;
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

function valueOrDash(value: string | number | boolean | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

function buildHaproxyResourceRebuildPlan(
  candidate: HaproxyRuntimeDebugDryRunCandidate | null,
): HaproxyResourceRebuildPlan {
  if (!candidate) {
    return {
      status: "no_candidate",
      summary: "请先读取上下文并选择一个 HAProxy dry-run candidate。",
      candidate_summary: [],
      blocking_checks: [],
      required_actions: [],
      recommended_next_stage: "Stage 3.4.25-advanced-debug-resource-registration-plan",
    };
  }

  const blockingChecks = candidate.integrity_checks.filter(
    (check) => !check.passed && check.severity === "danger",
  );
  const blockedIds = new Set(blockingChecks.map((check) => check.id));
  const hasAnyBlocked = (ids: string[]) => ids.some((id) => blockedIds.has(id));
  const requiredActions: HaproxyResourceRebuildPlanAction[] = [];

  if (
    hasAnyBlocked([
      "transit_resource_record_exists",
      "transit_resource_not_deleted",
      "transit_resource_status_supported",
    ])
  ) {
    requiredActions.push({
      id: "transit-resource-record",
      title: "需要补齐：正式中转资源记录",
      severity: "danger",
      description: "candidate 引用的中转资源不能作为当前有效资源继续执行。",
      steps: [
        "不要复用已 deleted 的中转资源。",
        "重新登记一个 active / worker_online 的中转服务器资源。",
        "确保该中转服务器绑定 transit Worker。",
        "补齐后重新生成 HAProxy dry-run。",
      ],
    });
  }

  if (
    hasAnyBlocked([
      "transit_worker_record_exists",
      "transit_worker_online",
      "transit_worker_role_is_transit",
      "transit_worker_interface_detected",
    ])
  ) {
    requiredActions.push({
      id: "transit-worker-status",
      title: "需要补齐：Transit Worker 状态",
      severity: "danger",
      description: "中转 Worker 必须在线、角色正确并上报网卡后才能继续。",
      steps: [
        "确认中转服务器上的 liveline-worker 在线。",
        "确认 role=transit。",
        "确认 heartbeat 正常。",
        "确认 interface_name 已上报。",
        "恢复后重新生成 HAProxy dry-run。",
      ],
    });
  }

  if (
    hasAnyBlocked([
      "landing_node_record_exists",
      "landing_node_not_deleted",
      "landing_node_active",
      "landing_node_has_vps_ip",
      "landing_node_xray_port_present",
    ])
  ) {
    requiredActions.push({
      id: "landing-node-record",
      title: "需要补齐：正式落地节点记录",
      severity: "danger",
      description: "candidate 引用的落地节点必须是当前有效 active 节点。",
      steps: [
        "选择或登记 active 落地节点。",
        "落地节点必须有 VPS IP。",
        "落地节点必须有 xray_port。",
        "不读取、不输出完整 share_link。",
        "用正式落地节点重新生成 HAProxy dry-run。",
      ],
    });
  }

  if (
    hasAnyBlocked([
      "candidate_landing_host_matches_node_vps_ip",
      "candidate_landing_port_matches_node_xray_port",
    ])
  ) {
    requiredActions.push({
      id: "regenerate-dry-run-for-current-node",
      title: "需要重新生成 dry-run：candidate host/port 与当前正式落地节点不一致",
      severity: "warning",
      description: "旧 candidate 的目标地址或端口不能代表当前正式落地节点。",
      steps: [
        "不要继续使用旧 candidate。",
        "以当前 active 落地节点的 VPS IP / xray_port 重新生成 HAProxy dry-run。",
      ],
    });
  }

  if (hasAnyBlocked(["candidate_status_succeeded"])) {
    requiredActions.push({
      id: "dry-run-not-succeeded",
      title: "需要重新生成或等待成功的 dry-run",
      severity: "warning",
      description: "只有 succeeded 的 HAProxy dry-run candidate 才能进入 readiness。",
      steps: [
        "当前 dry-run 不是 succeeded。",
        "不允许 readiness。",
        "重新生成成功的 HAProxy dry-run。",
      ],
    });
  }

  if (!requiredActions.length && blockingChecks.length) {
    requiredActions.push({
      id: "review-blocking-checks",
      title: "需要处理：其它完整性阻塞项",
      severity: "danger",
      description: "当前 candidate 仍有未归类的 danger 级阻塞项。",
      steps: ["查看 blocked checks 的 next_action，处理后重新读取上下文。"],
    });
  }

  const needsResourceOrNode = requiredActions.some((action) =>
    ["transit-resource-record", "transit-worker-status", "landing-node-record"].includes(action.id),
  );
  const recommendedNextStage =
    candidate.integrity_ready
      ? "不需要下一阶段资源重建"
      : needsResourceOrNode
        ? "Stage 3.4.25-advanced-debug-resource-registration-plan"
        : "Stage 3.4.25-advanced-debug-haproxy-dry-run-regenerate";

  return {
    status: candidate.integrity_ready ? "ready" : "blocked",
    summary: candidate.integrity_ready
      ? "当前 candidate 上下文完整，不需要重建资源。请人工确认端口放行和安全边界后再运行 readiness。"
      : "当前 candidate 是历史 dry-run 参数，正式资源上下文不完整。请先按下方方案补齐资源或重新生成 dry-run。",
    candidate_summary: [
      { label: "dry_run_command_id", value: valueOrDash(candidate.id) },
      { label: "status", value: valueOrDash(candidate.status) },
      { label: "integrity", value: candidate.integrity_ready ? "ready" : "blocked" },
      { label: "planned_listen_port", value: valueOrDash(candidate.planned_listen_port) },
      { label: "landing_target_host", value: valueOrDash(candidate.landing_target_host) },
      { label: "landing_target_port", value: valueOrDash(candidate.landing_target_port) },
      { label: "route_name", value: valueOrDash(candidate.route_name) },
      { label: "route_display_name", value: valueOrDash(candidate.route_display_name) },
      { label: "planned_service_name", value: valueOrDash(candidate.planned_service_name) },
      { label: "transit_resource_id", value: valueOrDash(candidate.transit_resource_id) },
      { label: "landing_node_id", value: valueOrDash(candidate.landing_node_id) },
      { label: "target_worker_id", value: valueOrDash(candidate.target_worker_id) },
    ],
    blocking_checks: blockingChecks,
    required_actions: requiredActions,
    recommended_next_stage: recommendedNextStage,
  };
}

function formatHaproxyResourceRebuildPlanText(plan: HaproxyResourceRebuildPlan) {
  const lines = [
    "HAProxy Resource Rebuild Plan",
    "",
    "Candidate Summary",
    ...plan.candidate_summary.map((item) => `- ${item.label}: ${item.value}`),
    "",
    "Plan Summary",
    `- status: ${plan.status}`,
    `- summary: ${plan.summary}`,
    `- recommended_next_stage: ${plan.recommended_next_stage}`,
    "",
    "Blocked Checks",
    ...(plan.blocking_checks.length
      ? plan.blocking_checks.flatMap((check) => [
          `- ${check.label} (${check.id})`,
          `  message: ${check.message}`,
          `  next_action: ${check.next_action}`,
          `  evidence_summary: ${check.evidence_summary ?? "-"}`,
        ])
      : ["- none"]),
    "",
    "Required Resources / Actions",
    ...(plan.required_actions.length
      ? plan.required_actions.flatMap((action) => [
          `- ${action.title}`,
          `  description: ${action.description}`,
          ...action.steps.map((step) => `  * ${step}`),
        ])
      : ["- none"]),
  ];
  return lines.join("\n");
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
  const selectedDryRunCandidate = useMemo(
    () => debugContext?.haproxy_dry_run_commands.find((candidate) => candidate.id === selectedDryRunCommandId) ?? null,
    [debugContext?.haproxy_dry_run_commands, selectedDryRunCommandId],
  );
  const rebuildPlan = useMemo(
    () => buildHaproxyResourceRebuildPlan(selectedDryRunCandidate),
    [selectedDryRunCandidate],
  );
  const selectedCandidateIntegrityReady = selectedDryRunCandidate?.integrity_ready === true;
  const canRunReadiness = formErrors.length === 0 && Boolean(requestPayload) && selectedCandidateIntegrityReady;
  const selectedTransitResource = useMemo(
    () => debugContext?.transit_resources.find((resource) => resource.id === selectedTransitResourceId) ?? null,
    [debugContext?.transit_resources, selectedTransitResourceId],
  );
  const selectedLandingNode = useMemo(
    () => debugContext?.landing_nodes.find((node) => node.id === selectedLandingNodeId) ?? null,
    [debugContext?.landing_nodes, selectedLandingNodeId],
  );
  const candidateTransitResourceMissing = Boolean(
    selectedDryRunCandidate?.transit_resource_id && debugContext && !selectedTransitResource,
  );
  const candidateLandingNodeMissing = Boolean(
    selectedDryRunCandidate?.landing_node_id && debugContext && !selectedLandingNode,
  );
  const canCreateRealExecution =
    Boolean(requestPayload) &&
    Boolean(readinessResult?.ready_for_real_execution) &&
    selectedCandidateIntegrityReady &&
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
    if (!selectedDryRunCandidate) {
      setMessage("请先选择一个通过完整性检查的 HAProxy dry-run candidate。");
      return;
    }
    if (!selectedDryRunCandidate.integrity_ready) {
      setMessage(selectedDryRunCandidate.integrity_summary || "上下文不完整，不能继续 readiness / real execution。");
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
    if (candidate.integrity_ready) {
      setContextMessage("已填充上下文字段；端口放行与安全确认仍需人工逐项确认。");
      setMessage("已从 HAProxy dry-run 候选填充 payload。请人工确认端口放行后再运行 readiness。");
    } else {
      setContextMessage("已填充上下文字段；上下文不完整，仅供查看，不能继续 readiness / real execution。");
      setMessage(candidate.integrity_summary || "上下文不完整，不能继续 readiness / real execution。");
    }
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
                  {candidateTransitResourceMissing ? (
                    <option value={selectedDryRunCandidate?.transit_resource_id ?? ""}>
                      未找到：{selectedDryRunCandidate?.transit_resource_id}
                    </option>
                  ) : null}
                  {debugContext?.transit_resources.map((resource) => (
                    <option key={resource.id} value={resource.id}>
                      {resource.name} / {resource.entry_host ?? "no-entry"} / {resource.worker_online ? "worker online" : resource.worker_runtime_status ?? "worker unknown"}
                    </option>
                  ))}
                </select>
                {selectedTransitResource ? (
                  <small>
                    已匹配正式中转资源。Worker：{selectedTransitResource.worker_id ?? "-"} / {selectedTransitResource.worker_version ?? "-"}
                  </small>
                ) : null}
                {candidateTransitResourceMissing ? (
                  <small className="danger">
                    candidate 引用的 transit_resource_id：{selectedDryRunCandidate?.transit_resource_id}；当前资源列表未找到该记录。
                  </small>
                ) : null}
              </label>

              <label>
                <span>落地节点</span>
                <select value={selectedLandingNodeId} onChange={(event) => setSelectedLandingNodeId(event.target.value)}>
                  <option value="">未选择</option>
                  {candidateLandingNodeMissing ? (
                    <option value={selectedDryRunCandidate?.landing_node_id ?? ""}>
                      未找到：{selectedDryRunCandidate?.landing_node_id}
                    </option>
                  ) : null}
                  {debugContext?.landing_nodes.map((node) => (
                    <option key={node.id} value={node.id}>
                      {node.node_name} / {node.target_host ?? "no-host"}:{node.target_port ?? "-"} / {node.status}
                    </option>
                  ))}
                </select>
                {selectedLandingNode ? (
                  <small>
                    已匹配正式落地节点。服务：{selectedLandingNode.service_status ?? "-"} / 客户端配置：{selectedLandingNode.share_link_present ? "已生成" : "未生成"}
                  </small>
                ) : null}
                {candidateLandingNodeMissing ? (
                  <small className="danger">
                    candidate 引用的 landing_node_id：{selectedDryRunCandidate?.landing_node_id}；当前节点列表未找到该记录。
                  </small>
                ) : null}
              </label>

              <label>
                <span>HAProxy dry-run 候选</span>
                <select value={selectedDryRunCommandId} onChange={(event) => selectDryRunCandidate(event.target.value)}>
                  <option value="">未选择</option>
                  {debugContext?.haproxy_dry_run_commands.map((candidate) => (
                    <option key={candidate.id} value={candidate.id}>
                      {candidate.integrity_ready ? "ready" : "blocked"} / {candidate.status} / {candidate.route_name ?? "haproxy route"} / {candidate.planned_listen_port ?? "-"} → {candidate.landing_target_port ?? "-"}
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

            {selectedDryRunCandidate ? (
              <section className={`advanced-debug-v2-integrity ${selectedDryRunCandidate.integrity_ready ? "success" : "danger"}`}>
                <header>
                  <div>
                    <span>上下文完整性</span>
                    <strong>{selectedDryRunCandidate.integrity_ready ? "完整 / ready" : "不完整 / blocked"}</strong>
                  </div>
                  <p>{selectedDryRunCandidate.integrity_summary}</p>
                  <small>{selectedDryRunCandidate.integrity_next_action}</small>
                </header>
                <div className="advanced-debug-v2-integrity-list">
                  {selectedDryRunCandidate.integrity_checks.map((check) => (
                    <article key={check.id} className={`advanced-debug-v2-integrity-check ${check.severity}`}>
                      <span>{check.passed ? "通过" : check.severity === "warning" ? "警告" : "阻塞"}</span>
                      <div>
                        <strong>{check.label}</strong>
                        <code>{check.id}</code>
                        <p>{check.message}</p>
                        <small>{check.next_action}</small>
                        {check.evidence_summary ? <em>evidence: {check.evidence_summary}</em> : null}
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ) : null}

            {selectedDryRunCandidate ? (
              <section className={`advanced-debug-v2-rebuild-plan advanced-debug-v2-rebuild-${rebuildPlan.status === "ready" ? "ready" : "blocked"}`}>
                <header className="advanced-debug-v2-card-title">
                  <div>
                    <h2>资源重建方案</h2>
                    <p>{rebuildPlan.summary}</p>
                  </div>
                  <button
                    type="button"
                    className="ghost small advanced-debug-v2-rebuild-copy"
                    onClick={() => copyText(formatHaproxyResourceRebuildPlanText(rebuildPlan), "重建方案已复制。")}
                  >
                    复制重建方案
                  </button>
                </header>

                <div className="advanced-debug-v2-rebuild-grid">
                  {rebuildPlan.candidate_summary.map((item) => (
                    <div key={item.label}>
                      <span>{item.label}</span>
                      <strong>{item.value}</strong>
                    </div>
                  ))}
                </div>

                {rebuildPlan.status === "blocked" ? (
                  <div className="advanced-debug-v2-context-warning">
                    当前 candidate 只能作为历史参数参考，不能继续 readiness / real execution。
                  </div>
                ) : (
                  <div className="advanced-debug-v2-context-message">
                    当前 candidate 上下文完整，不需要资源重建。请人工确认端口放行和安全边界后再运行 readiness。
                  </div>
                )}

                <div className="advanced-debug-v2-rebuild-section">
                  <h3>缺失 / 阻塞项摘要</h3>
                  {rebuildPlan.blocking_checks.length ? (
                    <div className="advanced-debug-v2-rebuild-checks">
                      {rebuildPlan.blocking_checks.map((check) => (
                        <article key={check.id}>
                          <strong>{check.label}</strong>
                          <code>{check.id}</code>
                          <p>{check.message}</p>
                          <small>{check.next_action}</small>
                          {check.evidence_summary ? <em>evidence: {check.evidence_summary}</em> : null}
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="advanced-debug-v2-rebuild-empty">没有 danger 级阻塞项。</p>
                  )}
                </div>

                <div className="advanced-debug-v2-rebuild-section">
                  <h3>需要补齐的正式资源</h3>
                  {rebuildPlan.required_actions.length ? (
                    <div className="advanced-debug-v2-rebuild-actions">
                      {rebuildPlan.required_actions.map((action) => (
                        <article key={action.id} className={`advanced-debug-v2-rebuild-action ${action.severity}`}>
                          <strong>{action.title}</strong>
                          <p>{action.description}</p>
                          <ul>
                            {action.steps.map((step) => (
                              <li key={step}>{step}</li>
                            ))}
                          </ul>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="advanced-debug-v2-rebuild-empty">无需补齐资源。</p>
                  )}
                </div>

                <footer className="advanced-debug-v2-rebuild-next">
                  <span>建议下一阶段</span>
                  <strong>{rebuildPlan.recommended_next_stage}</strong>
                </footer>
              </section>
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
