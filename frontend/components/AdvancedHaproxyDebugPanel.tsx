"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";

import { ProductIcon } from "@/components/ProductIcons";
import {
  apiFetch,
  createTransitHaproxyRouteRealExecution,
  getHaproxyRuntimeDebugContext,
  requestProtectedResourceRegistrationApprovalDryRun,
  requestProtectedResourceRegistrationDryRun,
  requestTransitHaproxyRouteRealExecutionReadiness,
  type CsrfResult,
  type HaproxyRuntimeDebugContextResult,
  type HaproxyRuntimeDebugDryRunCandidate,
  type HaproxyRuntimeDebugIntegrityCheck,
  type ProtectedResourceRegistrationApprovalDryRunRequest,
  type ProtectedResourceRegistrationApprovalDryRunResult,
  type ProtectedResourceRegistrationDryRunResult,
  type ReadonlyPreflightCheckItem,
  type TransitHaproxyRouteCreateRealExecutionRequest,
  type TransitHaproxyRouteCreateRealExecutionResult,
  type TransitHaproxyRouteRealExecutionReadinessResult,
} from "@/lib/api";

const FINAL_APPROVAL_TEXT = "CONFIRM_HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_ONLY";
const REAL_EXECUTION_STAGE = "Stage 3.3.139-new-transit-haproxy-route-create-real-execution";
const MANUAL_REAL_EXECUTION_CONFIRM = "CONFIRM_CREATE_HAPROXY_REAL_EXECUTION_COMMAND";
const PROTECTED_RESOURCE_REGISTRATION_STAGE = "Stage 3.4.26-advanced-debug-protected-resource-registration-ui";
const PROTECTED_RESOURCE_REGISTRATION_NEXT_STAGE = "Stage 3.4.27-advanced-debug-protected-resource-registration-dry-run";
const PROTECTED_RESOURCE_REGISTRATION_APPROVAL_STAGE = "3.4.28";
const PROTECTED_RESOURCE_REGISTRATION_APPROVAL_MODE = "approval_dry_run";
const PROTECTED_RESOURCE_REGISTRATION_APPROVAL_NEXT_STAGE =
  "Stage 3.4.29-protected-resource-registration-command-create";

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

type ResourceRegistrationField = {
  key: string;
  value: string;
  source: "candidate" | "integrity_check" | "manual_required" | "unknown";
  required: boolean;
  note: string;
};

type ResourceRegistrationSection = {
  id: string;
  title: string;
  severity: "info" | "warning" | "danger";
  description: string;
  fields: ResourceRegistrationField[];
  steps: string[];
};

type ResourceRegistrationPlan = {
  status: "ready" | "blocked" | "no_candidate";
  summary: string;
  required_sections: ResourceRegistrationSection[];
  missing_manual_inputs: string[];
  recommended_next_stage: string;
};

type ProtectedResourceRegistrationDraft = {
  transit_resource_name: string;
  transit_entry_host: string;
  transit_entry_port: string;
  transit_entry_region: string;
  transit_exit_region: string;
  transit_resource_type: "server";
  transit_expected_status: "active" | "worker_online";
  transit_worker_role: "transit";
  transit_worker_binding_required: boolean;
  landing_node_name: string;
  landing_vps_ip: string;
  landing_xray_port: string;
  landing_expected_status: "active";
  landing_share_link_handling: "do_not_export_or_modify_full_share_link";
  source_dry_run_command_id: string;
  source_candidate_route_name: string;
  source_candidate_listen_port: string;
  source_candidate_landing_host: string;
  source_candidate_landing_port: string;
  manual_confirm_transit_host: boolean;
  manual_confirm_worker_binding: boolean;
  manual_confirm_landing_host: boolean;
  manual_confirm_landing_port: boolean;
  manual_confirm_no_share_link_export: boolean;
  manual_confirm_no_remote_execution: boolean;
  manual_confirm_no_firewall_change: boolean;
  manual_confirm_no_cutover: boolean;
};

type ProtectedResourceRegistrationPayloadPreview = {
  stage: typeof PROTECTED_RESOURCE_REGISTRATION_STAGE;
  mode: "preview_only";
  source: {
    dry_run_command_id: string;
    route_name: string;
    planned_listen_port: number | null;
    landing_target_host: string;
    landing_target_port: number | null;
    candidate_integrity_ready: boolean;
  };
  transit_resource_registration: {
    name: string;
    resource_type: "server";
    entry_host: string;
    entry_port: number | null;
    entry_region: string;
    exit_region: string;
    expected_status: "active" | "worker_online";
    worker_role: "transit";
    worker_binding_required: boolean;
  };
  landing_node_registration: {
    node_name: string;
    vps_ip: string;
    xray_port: number | null;
    expected_status: "active";
    share_link_handling: "do_not_export_or_modify_full_share_link";
  };
  confirmations: {
    manual_confirm_transit_host: boolean;
    manual_confirm_worker_binding: boolean;
    manual_confirm_landing_host: boolean;
    manual_confirm_landing_port: boolean;
    manual_confirm_no_share_link_export: boolean;
    manual_confirm_no_remote_execution: boolean;
    manual_confirm_no_firewall_change: boolean;
    manual_confirm_no_cutover: boolean;
  };
  safety_boundary: string[];
};

type ProtectedResourceRegistrationApprovalConfirmations =
  ProtectedResourceRegistrationApprovalDryRunRequest["confirmations"];

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

const protectedRegistrationSafetyBoundary = [
  "preview_only",
  "不提交后端",
  "不创建 transit_resource",
  "不创建 landing_node",
  "不创建 WorkerCommand",
  "不创建 TransitRoute",
  "不创建 HAProxy route",
  "不绑定监听端口",
  "不 SSH / 不远程执行",
  "不修改防火墙 / 云安全组 / 云防火墙",
  "不读取、不输出、不修改完整 share_link",
  "不 cutover",
];

const defaultProtectedRegistrationApprovalConfirmations: ProtectedResourceRegistrationApprovalConfirmations = {
  registration_dry_run_passed: false,
  approval_text_matches_expected: false,
  no_real_resource_creation: false,
  no_worker_command_creation: false,
  no_transit_route_creation: false,
  no_haproxy_route_creation: false,
  no_ssh_or_remote_execution: false,
  no_firewall_change: false,
  no_cutover: false,
  ordinary_product_ui_unchanged: false,
  sensitive_fields_redacted: false,
};

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

function findIntegrityCheck(
  candidate: HaproxyRuntimeDebugDryRunCandidate,
  checkId: string,
) {
  return candidate.integrity_checks.find((check) => check.id === checkId) ?? null;
}

function fieldFromCheck(
  candidate: HaproxyRuntimeDebugDryRunCandidate,
  checkId: string,
  fallback = "-",
) {
  const check = findIntegrityCheck(candidate, checkId);
  return valueOrDash(check?.evidence_summary ?? check?.message ?? fallback);
}

function buildResourceRegistrationPlan(
  candidate: HaproxyRuntimeDebugDryRunCandidate | null,
  rebuildPlan: HaproxyResourceRebuildPlan,
): ResourceRegistrationPlan {
  if (!candidate) {
    return {
      status: "no_candidate",
      summary: "请先读取上下文并选择一个 HAProxy dry-run candidate。",
      required_sections: [],
      missing_manual_inputs: [],
      recommended_next_stage: "Stage 3.4.26-advanced-debug-protected-resource-registration-ui",
    };
  }

  const blockedIds = new Set(rebuildPlan.blocking_checks.map((check) => check.id));
  const actionIds = new Set(rebuildPlan.required_actions.map((action) => action.id));
  const hasAnyBlocked = (ids: string[]) => ids.some((id) => blockedIds.has(id));
  const requiredSections: ResourceRegistrationSection[] = [];

  const needsTransitResource = actionIds.has("transit-resource-record") || hasAnyBlocked([
    "transit_resource_record_exists",
    "transit_resource_not_deleted",
    "transit_resource_status_supported",
  ]);
  const needsTransitWorker = actionIds.has("transit-worker-status");
  const needsLandingNode = actionIds.has("landing-node-record") || hasAnyBlocked([
    "landing_node_record_exists",
    "landing_node_not_deleted",
    "landing_node_active",
    "landing_node_has_vps_ip",
    "landing_node_xray_port_present",
  ]);

  if (needsTransitResource) {
    requiredSections.push({
      id: "transit-resource-registration-draft",
      title: "正式中转资源登记草案",
      severity: "danger",
      description: "用于准备新的有效中转资源记录；历史 deleted resource id 只能作为审计线索。",
      fields: [
        {
          key: "transit_resource_id_from_candidate",
          value: valueOrDash(candidate.transit_resource_id),
          source: "candidate",
          required: true,
          note: "仅作为历史引用，不可直接复用 deleted 记录。",
        },
        {
          key: "transit_resource_status_problem",
          value: fieldFromCheck(candidate, "transit_resource_not_deleted", fieldFromCheck(candidate, "transit_resource_status_supported")),
          source: "integrity_check",
          required: true,
          note: "当前资源不可用，需重新登记或恢复有效资源。",
        },
        {
          key: "transit_resource_name_hint",
          value: fieldFromCheck(candidate, "transit_resource_record_exists", valueOrDash(candidate.route_display_name ?? candidate.route_name)),
          source: "integrity_check",
          required: false,
          note: "仅作命名参考，需人工确认。",
        },
        {
          key: "entry_host",
          value: "manual_required",
          source: "manual_required",
          required: true,
          note: "必须人工确认中转服务器公网入口 IP / host。",
        },
        {
          key: "entry_port",
          value: "manual_required",
          source: "manual_required",
          required: true,
          note: "中转资源入口端口需人工确认，不从旧 route 监听端口自动套用。",
        },
        {
          key: "ssh_port",
          value: "manual_required",
          source: "manual_required",
          required: true,
          note: "仅作为后续受保护登记所需信息；本阶段不会连接 SSH。",
        },
        {
          key: "resource_type",
          value: "server",
          source: "manual_required",
          required: true,
          note: "仅表示普通自建中转服务器资源。",
        },
        {
          key: "expected_status",
          value: "active 或 worker_online",
          source: "manual_required",
          required: true,
          note: "必须由受保护登记流程确认。",
        },
        {
          key: "worker_role",
          value: "transit",
          source: "manual_required",
          required: true,
          note: "中转 Worker 必须以 transit role 注册。",
        },
        {
          key: "worker_binding_required",
          value: "true",
          source: "manual_required",
          required: true,
          note: "需要确保 liveline-worker 已登记、在线，并绑定该中转资源。",
        },
      ],
      steps: [
        "不要复用已 deleted 的旧 transit_resource_id。",
        "确认中转服务器公网 IP / host、SSH 端口、区域、用途。",
        "确认或重新绑定 transit Worker。",
        "Worker online 且 interface_name 上报后，再重新生成 HAProxy dry-run。",
      ],
    });
  }

  if (needsLandingNode) {
    requiredSections.push({
      id: "landing-node-registration-draft",
      title: "正式落地节点登记草案",
      severity: "danger",
      description: "用于准备当前 active 落地节点记录；candidate 字段只是历史目标参数。",
      fields: [
        {
          key: "landing_node_id_from_candidate",
          value: valueOrDash(candidate.landing_node_id),
          source: "candidate",
          required: true,
          note: "仅作为历史引用，不可直接复用 deleted / missing 记录。",
        },
        {
          key: "landing_target_host_from_candidate",
          value: valueOrDash(candidate.landing_target_host),
          source: "candidate",
          required: true,
          note: "历史落地目标 IP，需要人工确认是否仍是当前 active 落地 VPS。",
        },
        {
          key: "landing_target_port_from_candidate",
          value: valueOrDash(candidate.landing_target_port),
          source: "candidate",
          required: true,
          note: "历史 Xray 端口，需要人工确认是否仍监听。",
        },
        {
          key: "node_name_hint",
          value: valueOrDash(candidate.route_display_name ?? candidate.route_name),
          source: "candidate",
          required: false,
          note: "仅作节点命名参考。",
        },
        {
          key: "vps_ip",
          value: valueOrDash(candidate.landing_target_host),
          source: "candidate",
          required: true,
          note: "需要人工确认这是当前正式落地 VPS IP。",
        },
        {
          key: "xray_port",
          value: valueOrDash(candidate.landing_target_port),
          source: "candidate",
          required: true,
          note: "需要人工确认这是当前 active Reality/Xray 端口。",
        },
        {
          key: "expected_status",
          value: "active",
          source: "manual_required",
          required: true,
          note: "落地节点必须是 active。",
        },
        {
          key: "share_link_handling",
          value: "do_not_export_or_modify_full_share_link",
          source: "manual_required",
          required: true,
          note: "本阶段不读取、不输出、不修改完整 share_link。",
        },
      ],
      steps: [
        "确认落地 VPS IP 是否仍为 candidate landing_target_host。",
        "确认落地 Xray / Reality 端口是否仍为 candidate landing_target_port。",
        "如果系统里没有 active 落地节点记录，下一阶段只允许通过受保护登记入口补登记。",
        "不读取、不输出完整 share_link。",
        "补登记后重新生成 HAProxy dry-run。",
      ],
    });
  }

  if (needsTransitWorker) {
    requiredSections.push({
      id: "transit-worker-preparation",
      title: "Transit Worker 准备清单",
      severity: "warning",
      description: "用于确认中转服务器上的 Worker 可以作为 HAProxy 创建目标。",
      fields: [
        {
          key: "target_worker_id_from_candidate",
          value: valueOrDash(candidate.target_worker_id),
          source: "candidate",
          required: true,
          note: "仅作为历史 Worker 引用，必须确认当前 Worker 仍在线并绑定有效资源。",
        },
        {
          key: "required_role",
          value: "transit",
          source: "manual_required",
          required: true,
          note: "Worker role 必须是 transit。",
        },
        {
          key: "required_status",
          value: "online",
          source: "manual_required",
          required: true,
          note: "Worker 必须在线且 heartbeat 未过期。",
        },
        {
          key: "interface_name_required",
          value: "true",
          source: "manual_required",
          required: true,
          note: "Worker 必须上报 interface_name。",
        },
        {
          key: "heartbeat_required",
          value: "true",
          source: "manual_required",
          required: true,
          note: "必须等待主控收到 Worker heartbeat。",
        },
      ],
      steps: [
        "确认中转服务器上 liveline-worker 已安装。",
        "确认 worker role=transit。",
        "确认 worker online。",
        "确认 heartbeat 正常。",
        "确认 interface_name 已上报。",
      ],
    });
  }

  const missingManualInputs = [
    "中转服务器公网 IP / host",
    "中转服务器 SSH 端口",
    "中转服务器区域 / 名称",
    "transit Worker 是否在线并绑定",
    "落地 VPS IP 是否仍有效",
    "落地 Xray / Reality 端口是否仍有效",
    "落地节点是否 active",
  ];
  const recommendedNextStage =
    candidate.integrity_ready
      ? "不需要下一阶段资源登记"
      : requiredSections.some((section) => ["transit-resource-registration-draft", "landing-node-registration-draft"].includes(section.id))
        ? "Stage 3.4.26-advanced-debug-protected-resource-registration-ui"
        : "Stage 3.4.26-advanced-debug-haproxy-dry-run-regenerate";

  return {
    status: candidate.integrity_ready ? "ready" : "blocked",
    summary: candidate.integrity_ready
      ? "当前 candidate 上下文完整，暂不需要登记新资源。可以继续按 readiness 流程人工确认端口和安全边界。"
      : "当前 candidate 引用的正式资源上下文不完整。下面是登记正式资源前的准备清单。本阶段只生成方案，不创建资源。",
    required_sections: requiredSections,
    missing_manual_inputs: candidate.integrity_ready ? [] : missingManualInputs,
    recommended_next_stage: recommendedNextStage,
  };
}

function formatResourceRegistrationPlanText(
  candidate: HaproxyRuntimeDebugDryRunCandidate | null,
  plan: ResourceRegistrationPlan,
) {
  const candidateSummary = candidate
    ? [
        `- dry_run_command_id: ${valueOrDash(candidate.id)}`,
        `- status: ${valueOrDash(candidate.status)}`,
        `- integrity: ${candidate.integrity_ready ? "ready" : "blocked"}`,
        `- route_name: ${valueOrDash(candidate.route_name)}`,
        `- planned_listen_port: ${valueOrDash(candidate.planned_listen_port)}`,
        `- landing_target_host: ${valueOrDash(candidate.landing_target_host)}`,
        `- landing_target_port: ${valueOrDash(candidate.landing_target_port)}`,
      ]
    : ["- no candidate selected"];
  const lines = [
    "Resource Registration Plan",
    "",
    "Candidate Summary",
    ...candidateSummary,
    "",
    "Plan Summary",
    `- status: ${plan.status}`,
    `- summary: ${plan.summary}`,
    `- recommended_next_stage: ${plan.recommended_next_stage}`,
    "",
    "Required Sections",
    ...(plan.required_sections.length
      ? plan.required_sections.flatMap((section) => [
          `- ${section.title}`,
          `  description: ${section.description}`,
          ...section.fields.flatMap((field) => [
            `  field: ${field.key}`,
            `    value: ${field.value}`,
            `    source: ${field.source}`,
            `    required: ${field.required ? "yes" : "no"}`,
            `    note: ${field.note}`,
          ]),
          ...section.steps.map((step) => `  * ${step}`),
        ])
      : ["- none"]),
    "",
    "Missing Manual Inputs",
    ...(plan.missing_manual_inputs.length ? plan.missing_manual_inputs.map((item) => `- ${item}`) : ["- none"]),
  ];
  return lines.join("\n");
}

function buildProtectedResourceRegistrationDraft(
  candidate: HaproxyRuntimeDebugDryRunCandidate | null,
): ProtectedResourceRegistrationDraft {
  const candidateRouteName = candidate?.route_name ?? "";
  const landingNameHint = candidate?.route_display_name ?? candidateRouteName;
  return {
    transit_resource_name: "",
    transit_entry_host: "",
    transit_entry_port: "",
    transit_entry_region: "",
    transit_exit_region: "",
    transit_resource_type: "server",
    transit_expected_status: "active",
    transit_worker_role: "transit",
    transit_worker_binding_required: true,
    landing_node_name: landingNameHint,
    landing_vps_ip: candidate?.landing_target_host ?? "",
    landing_xray_port: candidate?.landing_target_port ? String(candidate.landing_target_port) : "",
    landing_expected_status: "active",
    landing_share_link_handling: "do_not_export_or_modify_full_share_link",
    source_dry_run_command_id: candidate?.id ?? "",
    source_candidate_route_name: candidateRouteName,
    source_candidate_listen_port: candidate?.planned_listen_port ? String(candidate.planned_listen_port) : "",
    source_candidate_landing_host: candidate?.landing_target_host ?? "",
    source_candidate_landing_port: candidate?.landing_target_port ? String(candidate.landing_target_port) : "",
    manual_confirm_transit_host: false,
    manual_confirm_worker_binding: false,
    manual_confirm_landing_host: false,
    manual_confirm_landing_port: false,
    manual_confirm_no_share_link_export: false,
    manual_confirm_no_remote_execution: false,
    manual_confirm_no_firewall_change: false,
    manual_confirm_no_cutover: false,
  };
}

function validateProtectedResourceRegistrationDraft(draft: ProtectedResourceRegistrationDraft) {
  const errors: string[] = [];
  const requiredFields: Array<[keyof ProtectedResourceRegistrationDraft, string]> = [
    ["transit_resource_name", "transit_resource_name 不能为空"],
    ["transit_entry_host", "transit_entry_host 不能为空"],
    ["transit_entry_region", "transit_entry_region 不能为空"],
    ["transit_exit_region", "transit_exit_region 不能为空"],
    ["landing_node_name", "landing_node_name 不能为空"],
    ["landing_vps_ip", "landing_vps_ip 不能为空"],
  ];

  for (const [key, message] of requiredFields) {
    const value = draft[key];
    if (typeof value === "string" && !value.trim()) {
      errors.push(message);
    }
  }
  if (!draft.transit_entry_port.trim() || parsePort(draft.transit_entry_port) === null) {
    errors.push("transit_entry_port 必须是 1-65535 的整数");
  }
  if (!draft.landing_xray_port.trim() || parsePort(draft.landing_xray_port) === null) {
    errors.push("landing_xray_port 必须是 1-65535 的整数");
  }

  const confirmationChecks: Array<[keyof ProtectedResourceRegistrationDraft, string]> = [
    ["manual_confirm_transit_host", "需要人工确认中转服务器入口 host / IP"],
    ["manual_confirm_worker_binding", "需要人工确认 transit Worker 后续需要在线并绑定"],
    ["manual_confirm_landing_host", "需要人工确认落地 VPS IP 仍有效"],
    ["manual_confirm_landing_port", "需要人工确认落地 Xray / Reality 端口仍有效"],
    ["manual_confirm_no_share_link_export", "需要确认不读取、不输出、不修改完整 share_link"],
    ["manual_confirm_no_remote_execution", "需要确认本阶段不 SSH、不远程执行"],
    ["manual_confirm_no_firewall_change", "需要确认本阶段不修改防火墙 / 云安全组 / 云防火墙"],
    ["manual_confirm_no_cutover", "需要确认本阶段不 cutover"],
  ];
  for (const [key, message] of confirmationChecks) {
    if (!draft[key]) {
      errors.push(message);
    }
  }
  return errors;
}

function protectedRegistrationManualConfirmationCount(draft: ProtectedResourceRegistrationDraft) {
  return [
    draft.manual_confirm_transit_host,
    draft.manual_confirm_worker_binding,
    draft.manual_confirm_landing_host,
    draft.manual_confirm_landing_port,
    draft.manual_confirm_no_share_link_export,
    draft.manual_confirm_no_remote_execution,
    draft.manual_confirm_no_firewall_change,
    draft.manual_confirm_no_cutover,
  ].filter(Boolean).length;
}

function buildProtectedResourceRegistrationPayloadPreview(
  draft: ProtectedResourceRegistrationDraft,
  candidate: HaproxyRuntimeDebugDryRunCandidate | null,
): ProtectedResourceRegistrationPayloadPreview {
  return {
    stage: PROTECTED_RESOURCE_REGISTRATION_STAGE,
    mode: "preview_only",
    source: {
      dry_run_command_id: draft.source_dry_run_command_id.trim(),
      route_name: draft.source_candidate_route_name.trim(),
      planned_listen_port: parsePort(draft.source_candidate_listen_port),
      landing_target_host: draft.source_candidate_landing_host.trim(),
      landing_target_port: parsePort(draft.source_candidate_landing_port),
      candidate_integrity_ready: candidate?.integrity_ready === true,
    },
    transit_resource_registration: {
      name: draft.transit_resource_name.trim(),
      resource_type: draft.transit_resource_type,
      entry_host: draft.transit_entry_host.trim(),
      entry_port: parsePort(draft.transit_entry_port),
      entry_region: draft.transit_entry_region.trim(),
      exit_region: draft.transit_exit_region.trim(),
      expected_status: draft.transit_expected_status,
      worker_role: draft.transit_worker_role,
      worker_binding_required: draft.transit_worker_binding_required,
    },
    landing_node_registration: {
      node_name: draft.landing_node_name.trim(),
      vps_ip: draft.landing_vps_ip.trim(),
      xray_port: parsePort(draft.landing_xray_port),
      expected_status: draft.landing_expected_status,
      share_link_handling: draft.landing_share_link_handling,
    },
    confirmations: {
      manual_confirm_transit_host: draft.manual_confirm_transit_host,
      manual_confirm_worker_binding: draft.manual_confirm_worker_binding,
      manual_confirm_landing_host: draft.manual_confirm_landing_host,
      manual_confirm_landing_port: draft.manual_confirm_landing_port,
      manual_confirm_no_share_link_export: draft.manual_confirm_no_share_link_export,
      manual_confirm_no_remote_execution: draft.manual_confirm_no_remote_execution,
      manual_confirm_no_firewall_change: draft.manual_confirm_no_firewall_change,
      manual_confirm_no_cutover: draft.manual_confirm_no_cutover,
    },
    safety_boundary: protectedRegistrationSafetyBoundary,
  };
}

function formatProtectedResourceRegistrationExplanation(
  draft: ProtectedResourceRegistrationDraft,
  errors: string[],
  readyForNextStage: boolean,
) {
  const lines = [
    "Protected Resource Registration Preparation",
    "",
    `stage: ${PROTECTED_RESOURCE_REGISTRATION_STAGE}`,
    "mode: preview_only",
    `draft_ready_for_next_stage: ${readyForNextStage ? "true" : "false"}`,
    `recommended_next_stage: ${PROTECTED_RESOURCE_REGISTRATION_NEXT_STAGE}`,
    "",
    "Source Candidate",
    `- dry_run_command_id: ${valueOrDash(draft.source_dry_run_command_id)}`,
    `- route_name: ${valueOrDash(draft.source_candidate_route_name)}`,
    `- planned_listen_port: ${valueOrDash(draft.source_candidate_listen_port)}`,
    `- landing_target_host: ${valueOrDash(draft.source_candidate_landing_host)}`,
    `- landing_target_port: ${valueOrDash(draft.source_candidate_landing_port)}`,
    "",
    "Transit Resource Draft",
    `- name: ${valueOrDash(draft.transit_resource_name)}`,
    `- resource_type: ${draft.transit_resource_type}`,
    `- entry_host: ${valueOrDash(draft.transit_entry_host)}`,
    `- entry_port: ${valueOrDash(draft.transit_entry_port)}`,
    `- entry_region: ${valueOrDash(draft.transit_entry_region)}`,
    `- exit_region: ${valueOrDash(draft.transit_exit_region)}`,
    `- expected_status: ${draft.transit_expected_status}`,
    `- worker_role: ${draft.transit_worker_role}`,
    `- worker_binding_required: ${draft.transit_worker_binding_required ? "true" : "false"}`,
    "",
    "Landing Node Draft",
    `- node_name: ${valueOrDash(draft.landing_node_name)}`,
    `- vps_ip: ${valueOrDash(draft.landing_vps_ip)}`,
    `- xray_port: ${valueOrDash(draft.landing_xray_port)}`,
    `- expected_status: ${draft.landing_expected_status}`,
    `- share_link_handling: ${draft.landing_share_link_handling}`,
    "",
    "Blocked Items",
    ...(errors.length ? errors.map((error) => `- ${error}`) : ["- none"]),
    "",
    "Safety Boundary",
    ...protectedRegistrationSafetyBoundary.map((item) => `- ${item}`),
  ];
  return lines.join("\n");
}

function toRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function extractProtectedRegistrationDryRunResult(value: unknown): ProtectedResourceRegistrationDryRunResult | null {
  const root = toRecord(value);
  if (!root) {
    return null;
  }
  const data = toRecord(root.data) ?? root;
  if (data.dry_run !== true || typeof data.expected_approval_text !== "string") {
    return null;
  }
  return data as unknown as ProtectedResourceRegistrationDryRunResult;
}

function parseProtectedRegistrationDryRunSource(
  sourceText: string,
  currentResult: ProtectedResourceRegistrationDryRunResult | null,
) {
  if (!sourceText.trim()) {
    return { result: currentResult, error: "" };
  }
  try {
    const parsed = JSON.parse(sourceText);
    const result = extractProtectedRegistrationDryRunResult(parsed);
    if (!result) {
      return { result: null, error: "粘贴内容不是 Stage 3.4.27 registration dry-run 结果。" };
    }
    return { result, error: "" };
  } catch (error) {
    return { result: null, error: error instanceof Error ? error.message : "JSON 解析失败。" };
  }
}

function buildProtectedRegistrationApprovalPayload(
  sourceResult: ProtectedResourceRegistrationDryRunResult | null,
  approvalText: string,
  confirmations: ProtectedResourceRegistrationApprovalConfirmations,
): ProtectedResourceRegistrationApprovalDryRunRequest {
  const expectedApprovalText = sourceResult?.expected_approval_text ?? "";
  const approvalTextMatchesExpected = Boolean(expectedApprovalText && approvalText.trim() === expectedApprovalText);
  return {
    stage: PROTECTED_RESOURCE_REGISTRATION_APPROVAL_STAGE,
    mode: PROTECTED_RESOURCE_REGISTRATION_APPROVAL_MODE,
    source_registration_dry_run: {
      dry_run: sourceResult?.dry_run === true,
      ready_for_next_stage: sourceResult?.ready_for_next_stage === true,
      expected_approval_text: expectedApprovalText,
      normalized_preview: sourceResult?.normalized_preview ?? {},
    },
    approval_text: approvalText.trim(),
    confirmations: {
      ...confirmations,
      approval_text_matches_expected: approvalTextMatchesExpected,
    },
  };
}

function formatProtectedRegistrationApprovalExplanation(
  sourceResult: ProtectedResourceRegistrationDryRunResult | null,
  approvalTextMatchesExpected: boolean,
) {
  const lines = [
    "Protected Resource Registration Approval Dry-run",
    "",
    `stage: ${PROTECTED_RESOURCE_REGISTRATION_APPROVAL_STAGE}`,
    `mode: ${PROTECTED_RESOURCE_REGISTRATION_APPROVAL_MODE}`,
    `source_dry_run: ${sourceResult?.dry_run === true ? "true" : "false"}`,
    `source_ready_for_next_stage: ${sourceResult?.ready_for_next_stage === true ? "true" : "false"}`,
    `approval_text_matches_expected: ${approvalTextMatchesExpected ? "true" : "false"}`,
    `recommended_next_stage: ${PROTECTED_RESOURCE_REGISTRATION_APPROVAL_NEXT_STAGE}`,
    "",
    "Safety Boundary",
    "- approval dry-run only",
    "- no resource creation",
    "- no WorkerCommand creation",
    "- no TransitRoute creation",
    "- no HAProxy route creation",
    "- no SSH or remote execution",
    "- no firewall change",
    "- no cutover",
    "- ordinary product UI unchanged",
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
  const [protectedRegistrationDraft, setProtectedRegistrationDraft] = useState<ProtectedResourceRegistrationDraft>(() =>
    buildProtectedResourceRegistrationDraft(null),
  );
  const [protectedRegistrationDryRunResult, setProtectedRegistrationDryRunResult] =
    useState<ProtectedResourceRegistrationDryRunResult | null>(null);
  const [loadingProtectedRegistrationDryRun, setLoadingProtectedRegistrationDryRun] = useState(false);
  const [protectedRegistrationApprovalSourceText, setProtectedRegistrationApprovalSourceText] = useState("");
  const [protectedRegistrationApprovalText, setProtectedRegistrationApprovalText] = useState("");
  const [protectedRegistrationApprovalConfirmations, setProtectedRegistrationApprovalConfirmations] =
    useState<ProtectedResourceRegistrationApprovalConfirmations>(defaultProtectedRegistrationApprovalConfirmations);
  const [protectedRegistrationApprovalResult, setProtectedRegistrationApprovalResult] =
    useState<ProtectedResourceRegistrationApprovalDryRunResult | null>(null);
  const [loadingProtectedRegistrationApprovalDryRun, setLoadingProtectedRegistrationApprovalDryRun] = useState(false);

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
  const registrationPlan = useMemo(
    () => buildResourceRegistrationPlan(selectedDryRunCandidate, rebuildPlan),
    [selectedDryRunCandidate, rebuildPlan],
  );
  useEffect(() => {
    setProtectedRegistrationDraft(buildProtectedResourceRegistrationDraft(selectedDryRunCandidate));
    setProtectedRegistrationDryRunResult(null);
    setProtectedRegistrationApprovalSourceText("");
    setProtectedRegistrationApprovalText("");
    setProtectedRegistrationApprovalConfirmations(defaultProtectedRegistrationApprovalConfirmations);
    setProtectedRegistrationApprovalResult(null);
  }, [selectedDryRunCandidate?.id]);
  const selectedCandidateIntegrityReady = selectedDryRunCandidate?.integrity_ready === true;
  const protectedRegistrationErrors = useMemo(
    () => validateProtectedResourceRegistrationDraft(protectedRegistrationDraft),
    [protectedRegistrationDraft],
  );
  const protectedRegistrationPayloadPreview = useMemo(
    () => buildProtectedResourceRegistrationPayloadPreview(protectedRegistrationDraft, selectedDryRunCandidate),
    [protectedRegistrationDraft, selectedDryRunCandidate],
  );
  const protectedRegistrationReady = Boolean(selectedDryRunCandidate) && protectedRegistrationErrors.length === 0;
  const protectedRegistrationConfirmationCount = protectedRegistrationManualConfirmationCount(protectedRegistrationDraft);
  const canRunProtectedRegistrationDryRun =
    Boolean(selectedDryRunCandidate) &&
    protectedRegistrationReady &&
    Boolean(protectedRegistrationPayloadPreview) &&
    !loadingProtectedRegistrationDryRun;
  const protectedRegistrationApprovalSource = useMemo(
    () => parseProtectedRegistrationDryRunSource(protectedRegistrationApprovalSourceText, protectedRegistrationDryRunResult),
    [protectedRegistrationApprovalSourceText, protectedRegistrationDryRunResult],
  );
  const protectedRegistrationApprovalExpectedText =
    protectedRegistrationApprovalSource.result?.expected_approval_text ?? "";
  const protectedRegistrationApprovalTextMatches = Boolean(
    protectedRegistrationApprovalExpectedText &&
      protectedRegistrationApprovalText.trim() === protectedRegistrationApprovalExpectedText,
  );
  const protectedRegistrationApprovalPayload = useMemo(
    () =>
      buildProtectedRegistrationApprovalPayload(
        protectedRegistrationApprovalSource.result,
        protectedRegistrationApprovalText,
        protectedRegistrationApprovalConfirmations,
      ),
    [
      protectedRegistrationApprovalConfirmations,
      protectedRegistrationApprovalSource.result,
      protectedRegistrationApprovalText,
    ],
  );
  const protectedRegistrationApprovalConfirmationCount = Object.entries({
    ...protectedRegistrationApprovalConfirmations,
    approval_text_matches_expected: protectedRegistrationApprovalTextMatches,
  }).filter(([, value]) => value).length;
  const protectedRegistrationApprovalReady =
    Boolean(protectedRegistrationApprovalSource.result) &&
    !protectedRegistrationApprovalSource.error &&
    protectedRegistrationApprovalSource.result?.ready_for_next_stage === true &&
    protectedRegistrationApprovalTextMatches &&
    Object.entries(protectedRegistrationApprovalConfirmations)
      .filter(([key]) => key !== "approval_text_matches_expected")
      .every(([, value]) => value) &&
    !loadingProtectedRegistrationApprovalDryRun;
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

  function updateProtectedRegistrationDraft<K extends keyof ProtectedResourceRegistrationDraft>(
    key: K,
    value: ProtectedResourceRegistrationDraft[K],
  ) {
    setProtectedRegistrationDraft((current) => ({ ...current, [key]: value }));
    setProtectedRegistrationDryRunResult(null);
    setProtectedRegistrationApprovalResult(null);
  }

  function updateProtectedRegistrationApprovalConfirmation<K extends keyof ProtectedResourceRegistrationApprovalConfirmations>(
    key: K,
    value: boolean,
  ) {
    if (key === "approval_text_matches_expected") {
      return;
    }
    setProtectedRegistrationApprovalConfirmations((current) => ({ ...current, [key]: value }));
    setProtectedRegistrationApprovalResult(null);
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

  function clearProtectedRegistrationDraft() {
    setProtectedRegistrationDraft(buildProtectedResourceRegistrationDraft(selectedDryRunCandidate));
    setProtectedRegistrationDryRunResult(null);
    setProtectedRegistrationApprovalSourceText("");
    setProtectedRegistrationApprovalText("");
    setProtectedRegistrationApprovalConfirmations(defaultProtectedRegistrationApprovalConfirmations);
    setProtectedRegistrationApprovalResult(null);
    setMessage("登记草案已清空为当前 candidate 的默认 hint。");
  }

  function clearProtectedRegistrationApprovalDraft() {
    setProtectedRegistrationApprovalSourceText("");
    setProtectedRegistrationApprovalText("");
    setProtectedRegistrationApprovalConfirmations(defaultProtectedRegistrationApprovalConfirmations);
    setProtectedRegistrationApprovalResult(null);
    setMessage("审批草案已清空。");
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

  async function runProtectedRegistrationDryRun() {
    if (!selectedDryRunCandidate) {
      setMessage("请先选择一个 HAProxy dry-run candidate。");
      return;
    }
    if (!protectedRegistrationReady) {
      setMessage(protectedRegistrationErrors[0] ?? "登记草案未通过本地校验。");
      return;
    }
    setLoadingProtectedRegistrationDryRun(true);
    setMessage("正在运行 registration dry-run；这是只读校验，不会创建资源。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await requestProtectedResourceRegistrationDryRun(protectedRegistrationPayloadPreview, csrfToken);
      if (!result.success) {
        setMessage(result.message);
        return;
      }
      setProtectedRegistrationDryRunResult(result.data);
      setProtectedRegistrationApprovalResult(null);
      setMessage(
        result.data.ready_for_next_stage
          ? "registration dry-run 已通过。下一阶段仍需单独 approval，不会在本阶段创建资源。"
          : "registration dry-run 存在阻塞项。请先修正 payload 或人工确认信息。",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "运行 registration dry-run 失败。");
    } finally {
      setLoadingProtectedRegistrationDryRun(false);
    }
  }

  async function runProtectedRegistrationApprovalDryRun() {
    if (!protectedRegistrationApprovalSource.result) {
      setMessage(protectedRegistrationApprovalSource.error || "请先运行或粘贴 Stage 3.4.27 registration dry-run 结果。");
      return;
    }
    if (!protectedRegistrationApprovalReady) {
      setMessage(
        protectedRegistrationApprovalSource.error ||
          "审批草案未 ready：需要来源 dry-run ready、approval text 完全匹配，并勾选所有安全确认项。",
      );
      return;
    }
    setLoadingProtectedRegistrationApprovalDryRun(true);
    setMessage("正在运行 approval dry-run；这是只读审批校验，不会创建资源或 WorkerCommand。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await requestProtectedResourceRegistrationApprovalDryRun(
        protectedRegistrationApprovalPayload,
        csrfToken,
      );
      if (!result.success) {
        setMessage(result.message);
        return;
      }
      setProtectedRegistrationApprovalResult(result.data);
      setMessage(
        result.data.approved_for_next_stage
          ? "approval dry-run 已通过。下一阶段才能单独设计 command create，本阶段仍未创建任何资源。"
          : "approval dry-run 存在阻塞项。请检查审批文本和安全确认项。",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "运行 approval dry-run 失败。");
    } finally {
      setLoadingProtectedRegistrationApprovalDryRun(false);
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

            {selectedDryRunCandidate ? (
              <section
                className={`advanced-debug-v2-registration-plan advanced-debug-v2-registration-${
                  registrationPlan.status === "ready" ? "ready" : "blocked"
                }`}
              >
                <header className="advanced-debug-v2-card-title">
                  <div>
                    <h2>正式资源登记方案</h2>
                    <p>{registrationPlan.summary}</p>
                  </div>
                  <button
                    type="button"
                    className="ghost small advanced-debug-v2-registration-copy"
                    onClick={() =>
                      copyText(
                        formatResourceRegistrationPlanText(selectedDryRunCandidate, registrationPlan),
                        "登记方案已复制。",
                      )
                    }
                  >
                    复制登记方案
                  </button>
                </header>

                {registrationPlan.status === "blocked" ? (
                  <div className="advanced-debug-v2-context-warning">
                    这是只读登记前准备清单；不会创建中转资源、落地节点、WorkerCommand 或 TransitRoute。
                  </div>
                ) : (
                  <div className="advanced-debug-v2-context-message">
                    当前 candidate 上下文完整，暂不需要登记新资源。
                  </div>
                )}

                {registrationPlan.required_sections.length ? (
                  <div className="advanced-debug-v2-registration-sections">
                    {registrationPlan.required_sections.map((section) => (
                      <article key={section.id} className={`advanced-debug-v2-registration-section ${section.severity}`}>
                        <header>
                          <strong>{section.title}</strong>
                          <p>{section.description}</p>
                        </header>
                        <div className="advanced-debug-v2-registration-grid">
                          {section.fields.map((field) => (
                            <div key={`${section.id}-${field.key}`} className={`advanced-debug-v2-registration-field ${field.source}`}>
                              <span>{field.key}</span>
                              <strong>{field.value}</strong>
                              <small>
                                source: {field.source} / required: {field.required ? "yes" : "no"}
                              </small>
                              <em>{field.note}</em>
                            </div>
                          ))}
                        </div>
                        <ul>
                          {section.steps.map((step) => (
                            <li key={step}>{step}</li>
                          ))}
                        </ul>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="advanced-debug-v2-registration-empty">无需生成资源登记草案。</p>
                )}

                <div className="advanced-debug-v2-registration-manual">
                  <h3>缺失人工输入</h3>
                  {registrationPlan.missing_manual_inputs.length ? (
                    <ul>
                      {registrationPlan.missing_manual_inputs.map((input) => (
                        <li key={input}>
                          {input}
                          <span>candidate hint, must verify manually</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>没有待补充的人工输入。</p>
                  )}
                </div>

                <footer className="advanced-debug-v2-registration-next">
                  <span>建议下一阶段</span>
                  <strong>{registrationPlan.recommended_next_stage}</strong>
                </footer>
              </section>
            ) : null}

            {selectedDryRunCandidate ? (
              <section
                className={`advanced-debug-v2-protected-registration advanced-debug-v2-protected-registration-${
                  protectedRegistrationReady ? "ready" : "blocked"
                }`}
              >
                <header className="advanced-debug-v2-card-title">
                  <div>
                    <h2>受保护资源登记准备</h2>
                    <p>
                      {selectedDryRunCandidate.integrity_ready
                        ? "当前 candidate 上下文完整，通常不需要登记新资源。此区域仅用于查看，不建议创建新的登记 payload。"
                        : "当前 candidate 引用的正式资源上下文不完整。可以在这里准备下一阶段受保护资源登记所需的 payload。本阶段只准备，不提交。"}
                    </p>
                  </div>
                </header>

                <div className="advanced-debug-v2-protected-registration-grid">
                  <div>
                    <span>draft_ready_for_next_stage</span>
                    <strong>{protectedRegistrationReady ? "true" : "false"}</strong>
                  </div>
                  <div>
                    <span>blocked_fields_count</span>
                    <strong>{protectedRegistrationErrors.length}</strong>
                  </div>
                  <div>
                    <span>manual_confirmations_count</span>
                    <strong>{protectedRegistrationConfirmationCount} / 8</strong>
                  </div>
                  <div>
                    <span>recommended_next_stage</span>
                    <strong>{PROTECTED_RESOURCE_REGISTRATION_NEXT_STAGE}</strong>
                  </div>
                </div>

                <div className="advanced-debug-v2-context-warning">
                  candidate 字段只是历史 hint，必须人工确认，不代表当前真实状态。此卡片不会提交后端、不会创建资源、不会创建 WorkerCommand。
                </div>

                <section className="advanced-debug-v2-protected-registration-section advanced-debug-v2-protected-registration-source">
                  <header>
                    <strong>来源 candidate</strong>
                    <p>以下字段来自历史 dry-run candidate，仅作为登记准备参考。</p>
                  </header>
                  <div className="advanced-debug-v2-protected-registration-grid">
                    {[
                      ["source_dry_run_command_id", protectedRegistrationDraft.source_dry_run_command_id],
                      ["source_candidate_route_name", protectedRegistrationDraft.source_candidate_route_name],
                      ["source_candidate_listen_port", protectedRegistrationDraft.source_candidate_listen_port],
                      ["source_candidate_landing_host", protectedRegistrationDraft.source_candidate_landing_host],
                      ["source_candidate_landing_port", protectedRegistrationDraft.source_candidate_landing_port],
                      ["candidate_integrity_status", selectedDryRunCandidate.integrity_ready ? "ready" : "blocked"],
                    ].map(([label, value]) => (
                      <div key={label}>
                        <span>{label}</span>
                        <strong>{valueOrDash(value)}</strong>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="advanced-debug-v2-protected-registration-section">
                  <header>
                    <strong>中转资源登记准备</strong>
                    <p>中转资源字段必须人工填写；不会从历史 candidate 自动硬填入口 host、端口或区域。</p>
                  </header>
                  <div className="advanced-debug-v2-form-grid">
                    <Field label="transit_resource_name" required>
                      <input
                        value={protectedRegistrationDraft.transit_resource_name}
                        placeholder="例如：广州IEPL-香港出口01"
                        onChange={(event) => updateProtectedRegistrationDraft("transit_resource_name", event.target.value)}
                      />
                    </Field>
                    <Field label="transit_entry_host" required>
                      <input
                        value={protectedRegistrationDraft.transit_entry_host}
                        placeholder="例如：109.244.79.147"
                        onChange={(event) => updateProtectedRegistrationDraft("transit_entry_host", event.target.value)}
                      />
                    </Field>
                    <Field label="transit_entry_port" required>
                      <input
                        value={protectedRegistrationDraft.transit_entry_port}
                        placeholder="例如：22"
                        onChange={(event) => updateProtectedRegistrationDraft("transit_entry_port", event.target.value)}
                      />
                    </Field>
                    <Field label="transit_entry_region" required>
                      <input
                        value={protectedRegistrationDraft.transit_entry_region}
                        placeholder="例如：广州"
                        onChange={(event) => updateProtectedRegistrationDraft("transit_entry_region", event.target.value)}
                      />
                    </Field>
                    <Field label="transit_exit_region" required>
                      <input
                        value={protectedRegistrationDraft.transit_exit_region}
                        placeholder="例如：香港"
                        onChange={(event) => updateProtectedRegistrationDraft("transit_exit_region", event.target.value)}
                      />
                    </Field>
                    <Field label="transit_expected_status" required>
                      <select
                        value={protectedRegistrationDraft.transit_expected_status}
                        onChange={(event) =>
                          updateProtectedRegistrationDraft(
                            "transit_expected_status",
                            event.target.value as ProtectedResourceRegistrationDraft["transit_expected_status"],
                          )
                        }
                      >
                        <option value="active">active</option>
                        <option value="worker_online">worker_online</option>
                      </select>
                    </Field>
                    <Field label="transit_resource_type" required>
                      <input value={protectedRegistrationDraft.transit_resource_type} readOnly />
                    </Field>
                    <Field label="transit_worker_role" required>
                      <input value={protectedRegistrationDraft.transit_worker_role} readOnly />
                    </Field>
                    <CheckboxRow
                      checked={protectedRegistrationDraft.transit_worker_binding_required}
                      label="transit_worker_binding_required"
                      detail="默认 true，仅表示后续登记必须绑定在线 transit Worker。"
                      onChange={(checked) => updateProtectedRegistrationDraft("transit_worker_binding_required", checked)}
                    />
                  </div>
                </section>

                <section className="advanced-debug-v2-protected-registration-section">
                  <header>
                    <strong>落地节点登记准备</strong>
                    <p>落地节点名称、VPS IP 与端口来自 candidate hint，必须人工核对后才能进入下一阶段。</p>
                  </header>
                  <div className="advanced-debug-v2-form-grid">
                    <Field label="landing_node_name" required>
                      <input
                        value={protectedRegistrationDraft.landing_node_name}
                        onChange={(event) => updateProtectedRegistrationDraft("landing_node_name", event.target.value)}
                      />
                    </Field>
                    <Field label="landing_vps_ip" required>
                      <input
                        value={protectedRegistrationDraft.landing_vps_ip}
                        onChange={(event) => updateProtectedRegistrationDraft("landing_vps_ip", event.target.value)}
                      />
                    </Field>
                    <Field label="landing_xray_port" required>
                      <input
                        value={protectedRegistrationDraft.landing_xray_port}
                        onChange={(event) => updateProtectedRegistrationDraft("landing_xray_port", event.target.value)}
                      />
                    </Field>
                    <Field label="landing_expected_status" required>
                      <input value={protectedRegistrationDraft.landing_expected_status} readOnly />
                    </Field>
                    <Field label="landing_share_link_handling" required>
                      <input value={protectedRegistrationDraft.landing_share_link_handling} readOnly />
                    </Field>
                  </div>
                </section>

                <section className="advanced-debug-v2-protected-registration-section advanced-debug-v2-protected-registration-confirm">
                  <header>
                    <strong>人工确认</strong>
                    <p>全部确认后，登记草案才会标记为 ready_for_next_stage；即使 ready，本阶段仍只能复制 payload。</p>
                  </header>
                  <div className="advanced-debug-v2-confirmation-grid">
                    <CheckboxRow
                      checked={protectedRegistrationDraft.manual_confirm_transit_host}
                      label="我已人工确认中转服务器入口 host / IP"
                      onChange={(checked) => updateProtectedRegistrationDraft("manual_confirm_transit_host", checked)}
                    />
                    <CheckboxRow
                      checked={protectedRegistrationDraft.manual_confirm_worker_binding}
                      label="我已人工确认 transit Worker 后续需要在线并绑定"
                      onChange={(checked) => updateProtectedRegistrationDraft("manual_confirm_worker_binding", checked)}
                    />
                    <CheckboxRow
                      checked={protectedRegistrationDraft.manual_confirm_landing_host}
                      label="我已人工确认落地 VPS IP 仍有效"
                      onChange={(checked) => updateProtectedRegistrationDraft("manual_confirm_landing_host", checked)}
                    />
                    <CheckboxRow
                      checked={protectedRegistrationDraft.manual_confirm_landing_port}
                      label="我已人工确认落地 Xray / Reality 端口仍有效"
                      onChange={(checked) => updateProtectedRegistrationDraft("manual_confirm_landing_port", checked)}
                    />
                    <CheckboxRow
                      checked={protectedRegistrationDraft.manual_confirm_no_share_link_export}
                      label="我确认本阶段不读取、不输出、不修改完整 share_link"
                      onChange={(checked) => updateProtectedRegistrationDraft("manual_confirm_no_share_link_export", checked)}
                    />
                    <CheckboxRow
                      checked={protectedRegistrationDraft.manual_confirm_no_remote_execution}
                      label="我确认本阶段不 SSH、不远程执行"
                      onChange={(checked) => updateProtectedRegistrationDraft("manual_confirm_no_remote_execution", checked)}
                    />
                    <CheckboxRow
                      checked={protectedRegistrationDraft.manual_confirm_no_firewall_change}
                      label="我确认本阶段不修改防火墙 / 云安全组 / 云防火墙"
                      onChange={(checked) => updateProtectedRegistrationDraft("manual_confirm_no_firewall_change", checked)}
                    />
                    <CheckboxRow
                      checked={protectedRegistrationDraft.manual_confirm_no_cutover}
                      label="我确认本阶段不 cutover"
                      onChange={(checked) => updateProtectedRegistrationDraft("manual_confirm_no_cutover", checked)}
                    />
                  </div>
                </section>

                <section className="advanced-debug-v2-protected-registration-section advanced-debug-v2-protected-registration-preview">
                  <header>
                    <strong>Payload 预览</strong>
                    <p>只读、脱敏、仅供复制到下一阶段设计；没有提交动作。</p>
                  </header>
                  {protectedRegistrationErrors.length ? (
                    <div className="advanced-debug-v2-protected-registration-blocked-list">
                      <strong>blocked items</strong>
                      <ul>
                        {protectedRegistrationErrors.map((error) => (
                          <li key={error}>{error}</li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <div className="advanced-debug-v2-context-message">
                      登记草案已通过本地校验，可复制给下一阶段 registration dry-run 使用。
                    </div>
                  )}
                  <pre>{formatJson(protectedRegistrationPayloadPreview)}</pre>
                </section>

                <section
                  className={`advanced-debug-v2-registration-dry-run ${
                    protectedRegistrationDryRunResult?.ready_for_next_stage
                      ? "advanced-debug-v2-registration-dry-run-ready"
                      : protectedRegistrationDryRunResult
                        ? "advanced-debug-v2-registration-dry-run-blocked"
                        : ""
                  }`}
                >
                  <header>
                    <div>
                      <strong>Registration Dry-run（只读）</strong>
                      <p>提交到后端做只读校验；不会创建资源、不会创建 WorkerCommand、不会远程执行。</p>
                    </div>
                    <div className="advanced-debug-v2-registration-dry-run-actions">
                      <button
                        type="button"
                        className="ghost small"
                        onClick={runProtectedRegistrationDryRun}
                        disabled={!canRunProtectedRegistrationDryRun}
                      >
                        {loadingProtectedRegistrationDryRun ? "校验中..." : "运行 registration dry-run（只读）"}
                      </button>
                      <button
                        type="button"
                        className="ghost small"
                        disabled={!protectedRegistrationDryRunResult}
                        onClick={() =>
                          protectedRegistrationDryRunResult
                            ? copyText(formatJson(protectedRegistrationDryRunResult), "registration dry-run 结果已复制。")
                            : undefined
                        }
                      >
                        复制 dry-run 结果
                      </button>
                      <button
                        type="button"
                        className="ghost small"
                        disabled={!protectedRegistrationDryRunResult}
                        onClick={() => {
                          setProtectedRegistrationDryRunResult(null);
                          setMessage("registration dry-run 结果已清空。");
                        }}
                      >
                        清空 dry-run 结果
                      </button>
                    </div>
                  </header>

                  {protectedRegistrationDryRunResult ? (
                    <>
                      <div className="advanced-debug-v2-registration-dry-run-summary">
                        <div>
                          <span>dry_run</span>
                          <strong>{String(protectedRegistrationDryRunResult.dry_run)}</strong>
                        </div>
                        <div>
                          <span>ready_for_next_stage</span>
                          <strong>{String(protectedRegistrationDryRunResult.ready_for_next_stage)}</strong>
                        </div>
                        <div>
                          <span>recommended_next_stage</span>
                          <strong>{protectedRegistrationDryRunResult.recommended_next_stage}</strong>
                        </div>
                        <div>
                          <span>expected_approval_text</span>
                          <strong>{protectedRegistrationDryRunResult.expected_approval_text}</strong>
                        </div>
                      </div>

                      {protectedRegistrationDryRunResult.ready_for_next_stage ? (
                        <div className="advanced-debug-v2-context-message">
                          registration dry-run 已通过。下一阶段仍需单独 approval，不会在本阶段创建资源。
                        </div>
                      ) : (
                        <div className="advanced-debug-v2-protected-registration-blocked-list">
                          <strong>blocked_reasons</strong>
                          {protectedRegistrationDryRunResult.blocked_reasons.length ? (
                            <ul>
                              {protectedRegistrationDryRunResult.blocked_reasons.map((reason) => (
                                <li key={reason}>{reason}</li>
                              ))}
                            </ul>
                          ) : (
                            <p>无 danger 阻塞项；请查看 warning 检查项。</p>
                          )}
                        </div>
                      )}

                      <div className="advanced-debug-v2-registration-dry-run-checks">
                        {protectedRegistrationDryRunResult.checks.map((check) => (
                          <article key={check.id} className={check.severity}>
                            <div>
                              <strong>{check.label}</strong>
                              <span>{check.id}</span>
                            </div>
                            <p>{check.message}</p>
                            <small>{check.next_action}</small>
                            {check.evidence_summary ? <em>{check.evidence_summary}</em> : null}
                          </article>
                        ))}
                      </div>

                      <div className="advanced-debug-v2-registration-dry-run-preview">
                        <strong>normalized_preview</strong>
                        <pre>{formatJson(protectedRegistrationDryRunResult.normalized_preview)}</pre>
                      </div>
                    </>
                  ) : (
                    <div className="advanced-debug-v2-registration-dry-run-empty">
                      尚未运行 registration dry-run。按钮启用前必须先让登记草案通过本地校验。
                    </div>
                  )}
                </section>

                <section
                  className={`advanced-debug-v2-registration-approval-dry-run ${
                    protectedRegistrationApprovalResult?.approved_for_next_stage
                      ? "advanced-debug-v2-registration-approval-dry-run-ready"
                      : protectedRegistrationApprovalResult
                        ? "advanced-debug-v2-registration-approval-dry-run-blocked"
                        : ""
                  }`}
                >
                  <header>
                    <div>
                      <strong>受保护资源登记审批 · Stage 3.4.28</strong>
                      <p>
                        approval dry-run only：不会创建资源、不会创建 WorkerCommand、不会创建 TransitRoute、不会创建 HAProxy route、不会 SSH、不会修改防火墙、不会 cutover。
                      </p>
                    </div>
                    <div className="advanced-debug-v2-registration-dry-run-actions">
                      <button
                        type="button"
                        className="ghost small"
                        onClick={() => {
                          setProtectedRegistrationApprovalResult(null);
                          setMessage("审批 Payload 预览已生成；这只是前端预览，不会创建资源。");
                        }}
                      >
                        生成审批 Payload
                      </button>
                      <button
                        type="button"
                        className="ghost small"
                        onClick={() => copyText(formatJson(protectedRegistrationApprovalPayload), "审批 Payload 已复制。")}
                      >
                        复制审批 Payload
                      </button>
                      <button
                        type="button"
                        className="ghost small"
                        onClick={runProtectedRegistrationApprovalDryRun}
                        disabled={!protectedRegistrationApprovalReady}
                      >
                        {loadingProtectedRegistrationApprovalDryRun ? "校验中..." : "运行 Approval Dry-run"}
                      </button>
                      <button
                        type="button"
                        className="ghost small"
                        onClick={() =>
                          copyText(
                            formatProtectedRegistrationApprovalExplanation(
                              protectedRegistrationApprovalSource.result,
                              protectedRegistrationApprovalTextMatches,
                            ),
                            "审批说明已复制。",
                          )
                        }
                      >
                        复制审批说明
                      </button>
                      <button type="button" className="ghost small" onClick={clearProtectedRegistrationApprovalDraft}>
                        清空审批草案
                      </button>
                    </div>
                  </header>

                  <div className="advanced-debug-v2-registration-approval-source">
                    <Field label="Stage 3.4.27 registration dry-run result JSON（可选粘贴）">
                      <textarea
                        value={protectedRegistrationApprovalSourceText}
                        placeholder="留空时自动使用本页刚运行的 registration dry-run 结果；也可以粘贴已复制的 dry-run result JSON。"
                        onChange={(event) => {
                          setProtectedRegistrationApprovalSourceText(event.target.value);
                          setProtectedRegistrationApprovalResult(null);
                        }}
                      />
                    </Field>
                    <div className="advanced-debug-v2-registration-approval-summary">
                      <div>
                        <span>source_dry_run</span>
                        <strong>{String(protectedRegistrationApprovalSource.result?.dry_run === true)}</strong>
                      </div>
                      <div>
                        <span>source_ready_for_next_stage</span>
                        <strong>{String(protectedRegistrationApprovalSource.result?.ready_for_next_stage === true)}</strong>
                      </div>
                      <div>
                        <span>expected_approval_text</span>
                        <strong>{valueOrDash(protectedRegistrationApprovalExpectedText)}</strong>
                      </div>
                      <div>
                        <span>local_exact_match</span>
                        <strong>{protectedRegistrationApprovalTextMatches ? "matched" : "not matched"}</strong>
                      </div>
                    </div>
                    {protectedRegistrationApprovalSource.error ? (
                      <div className="advanced-debug-v2-protected-registration-blocked-list">
                        <strong>source parse error</strong>
                        <p>{protectedRegistrationApprovalSource.error}</p>
                      </div>
                    ) : null}
                  </div>

                  <section className="advanced-debug-v2-protected-registration-section">
                    <header>
                      <strong>Approval Text</strong>
                      <p>必须与 expected_approval_text 完全一致；匹配结果会自动写入 approval payload。</p>
                    </header>
                    <Field label="approval_text">
                      <input
                        value={protectedRegistrationApprovalText}
                        placeholder="逐字符输入 expected_approval_text"
                        onChange={(event) => {
                          setProtectedRegistrationApprovalText(event.target.value);
                          setProtectedRegistrationApprovalResult(null);
                        }}
                      />
                    </Field>
                    <div
                      className={`advanced-debug-v2-registration-approval-match ${
                        protectedRegistrationApprovalTextMatches ? "matched" : "blocked"
                      }`}
                    >
                      <span>{protectedRegistrationApprovalTextMatches ? "完全匹配" : "尚未完全匹配"}</span>
                      <strong>approval_text_matches_expected</strong>
                    </div>
                  </section>

                  <section className="advanced-debug-v2-protected-registration-section advanced-debug-v2-protected-registration-confirm">
                    <header>
                      <strong>审批安全确认</strong>
                      <p>这些确认只用于 approval dry-run 校验，不会触发任何资源登记、命令创建或远程动作。</p>
                    </header>
                    <div className="advanced-debug-v2-confirmation-grid">
                      <CheckboxRow
                        checked={protectedRegistrationApprovalConfirmations.registration_dry_run_passed}
                        label="我确认 Stage 3.4.27 registration dry-run 已通过"
                        onChange={(checked) =>
                          updateProtectedRegistrationApprovalConfirmation("registration_dry_run_passed", checked)
                        }
                      />
                      <CheckboxRow
                        checked={protectedRegistrationApprovalTextMatches}
                        label="approval text 与 expected 完全匹配（自动判断）"
                        onChange={() => undefined}
                      />
                      <CheckboxRow
                        checked={protectedRegistrationApprovalConfirmations.no_real_resource_creation}
                        label="我确认本阶段不创建实际资源"
                        onChange={(checked) =>
                          updateProtectedRegistrationApprovalConfirmation("no_real_resource_creation", checked)
                        }
                      />
                      <CheckboxRow
                        checked={protectedRegistrationApprovalConfirmations.no_worker_command_creation}
                        label="我确认本阶段不创建 WorkerCommand"
                        onChange={(checked) =>
                          updateProtectedRegistrationApprovalConfirmation("no_worker_command_creation", checked)
                        }
                      />
                      <CheckboxRow
                        checked={protectedRegistrationApprovalConfirmations.no_transit_route_creation}
                        label="我确认本阶段不创建 TransitRoute"
                        onChange={(checked) =>
                          updateProtectedRegistrationApprovalConfirmation("no_transit_route_creation", checked)
                        }
                      />
                      <CheckboxRow
                        checked={protectedRegistrationApprovalConfirmations.no_haproxy_route_creation}
                        label="我确认本阶段不创建 HAProxy route"
                        onChange={(checked) =>
                          updateProtectedRegistrationApprovalConfirmation("no_haproxy_route_creation", checked)
                        }
                      />
                      <CheckboxRow
                        checked={protectedRegistrationApprovalConfirmations.no_ssh_or_remote_execution}
                        label="我确认本阶段不 SSH、不远程执行"
                        onChange={(checked) =>
                          updateProtectedRegistrationApprovalConfirmation("no_ssh_or_remote_execution", checked)
                        }
                      />
                      <CheckboxRow
                        checked={protectedRegistrationApprovalConfirmations.no_firewall_change}
                        label="我确认本阶段不修改防火墙 / 云安全组 / 云防火墙"
                        onChange={(checked) =>
                          updateProtectedRegistrationApprovalConfirmation("no_firewall_change", checked)
                        }
                      />
                      <CheckboxRow
                        checked={protectedRegistrationApprovalConfirmations.no_cutover}
                        label="我确认本阶段不 cutover"
                        onChange={(checked) => updateProtectedRegistrationApprovalConfirmation("no_cutover", checked)}
                      />
                      <CheckboxRow
                        checked={protectedRegistrationApprovalConfirmations.ordinary_product_ui_unchanged}
                        label="我确认普通产品 UI 不改"
                        onChange={(checked) =>
                          updateProtectedRegistrationApprovalConfirmation("ordinary_product_ui_unchanged", checked)
                        }
                      />
                      <CheckboxRow
                        checked={protectedRegistrationApprovalConfirmations.sensitive_fields_redacted}
                        label="我确认没有完整客户端配置、凭证、命令或密钥"
                        onChange={(checked) =>
                          updateProtectedRegistrationApprovalConfirmation("sensitive_fields_redacted", checked)
                        }
                      />
                    </div>
                  </section>

                  <section className="advanced-debug-v2-protected-registration-section advanced-debug-v2-protected-registration-preview">
                    <header>
                      <strong>Approval Payload 预览</strong>
                      <p>当前确认进度：{protectedRegistrationApprovalConfirmationCount} / 11；复制内容会在浏览器侧脱敏显示。</p>
                    </header>
                    <pre>{formatJson(protectedRegistrationApprovalPayload)}</pre>
                  </section>

                  {protectedRegistrationApprovalResult ? (
                    <>
                      <div className="advanced-debug-v2-registration-dry-run-summary">
                        <div>
                          <span>dry_run</span>
                          <strong>{String(protectedRegistrationApprovalResult.dry_run)}</strong>
                        </div>
                        <div>
                          <span>approved_for_next_stage</span>
                          <strong>{String(protectedRegistrationApprovalResult.approved_for_next_stage)}</strong>
                        </div>
                        <div>
                          <span>ready_for_command_create_next_stage</span>
                          <strong>{String(protectedRegistrationApprovalResult.ready_for_command_create_next_stage)}</strong>
                        </div>
                        <div>
                          <span>recommended_next_stage</span>
                          <strong>{protectedRegistrationApprovalResult.recommended_next_stage}</strong>
                        </div>
                      </div>

                      {protectedRegistrationApprovalResult.blocked_reasons.length ? (
                        <div className="advanced-debug-v2-protected-registration-blocked-list">
                          <strong>blocked_reasons</strong>
                          <ul>
                            {protectedRegistrationApprovalResult.blocked_reasons.map((reason) => (
                              <li key={reason}>{reason}</li>
                            ))}
                          </ul>
                        </div>
                      ) : (
                        <div className="advanced-debug-v2-context-message">
                          Approval dry-run 已通过。下一阶段仍需单独设计 command create；本阶段未创建任何资源。
                        </div>
                      )}

                      <div className="advanced-debug-v2-registration-dry-run-checks">
                        {protectedRegistrationApprovalResult.checks.map((check) => (
                          <article key={check.id} className={check.severity}>
                            <div>
                              <strong>{check.label}</strong>
                              <span>{check.id}</span>
                            </div>
                            <p>{check.message}</p>
                            <small>{check.next_action}</small>
                            {check.evidence_summary ? <em>{check.evidence_summary}</em> : null}
                          </article>
                        ))}
                      </div>

                      <div className="advanced-debug-v2-registration-dry-run-preview">
                        <strong>normalized_approval_preview</strong>
                        <pre>{formatJson(protectedRegistrationApprovalResult.normalized_approval_preview)}</pre>
                      </div>
                    </>
                  ) : (
                    <div className="advanced-debug-v2-registration-dry-run-empty">
                      尚未运行 approval dry-run。按钮启用前需要来源 dry-run ready、审批文本完全匹配，并勾选所有安全确认。
                    </div>
                  )}
                </section>

                <div className="advanced-debug-v2-protected-registration-actions">
                  <button
                    type="button"
                    className="ghost small"
                    onClick={() => copyText(formatJson(protectedRegistrationPayloadPreview), "登记 Payload 已复制。")}
                  >
                    复制登记 Payload
                  </button>
                  <button
                    type="button"
                    className="ghost small"
                    onClick={() =>
                      copyText(
                        formatProtectedResourceRegistrationExplanation(
                          protectedRegistrationDraft,
                          protectedRegistrationErrors,
                          protectedRegistrationReady,
                        ),
                        "登记说明已复制。",
                      )
                    }
                  >
                    复制登记说明
                  </button>
                  <button type="button" className="ghost small" onClick={clearProtectedRegistrationDraft}>
                    清空登记草案
                  </button>
                </div>
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
