"use client";

import { Fragment, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import QRCode from "react-qr-code";

import { TransitReadonlyPreflightSimplePanel } from "@/components/TransitReadonlyPreflightSimplePanel";
import {
  apiFetch,
  createTransitResource,
  createTransitHaproxyRouteDryRun,
  createTransitHaproxyRouteRealExecution,
  createTransitRouteWorkerExecuteCommand,
  createTransitReadonlyPreflightCommand,
  createWorkerCommand,
  exportTransitRouteCandidate,
  generateTransitWorkerInstallCommand,
  getTransitWorkerAcceptance,
  getTransitWorkerUpgradeAcceptance,
  getWorkerCommand,
  getTransitRouteCandidateSummary,
  listWorkerCommands,
  OFFLINE_LOCAL_REMOVE_CONFIRM_TEXT,
  remoteCleanupDeleteTransitResource,
  remoteCleanupDeleteTransitRoute,
  REMOTE_CLEANUP_CONFIRM_TEXT,
  requestReadonlyPreflightPlan,
  requestTransitHaproxyReadinessApproval,
  requestTransitHaproxyRouteFinalApproval,
  type CsrfResult,
  type NodeData,
  type NodeListResult,
  type ReadonlyPreflightPlanRequest,
  type ReadonlyPreflightPlanResponse,
  type RemoteCleanupUnavailableData,
  type TransitRouteCandidateExportResult,
  type TransitRouteCandidateSummary,
  type TransitCreateForwardingMethod,
  type TransitForwardingMethod,
  type TransitReadonlyPreflightCommandRequest,
  type TransitResourceData,
  type TransitResourceListResult,
  type TransitHaproxyReadinessApprovalResult,
  type TransitHaproxyRouteCreateDryRunResult,
  type TransitHaproxyRouteCreateFinalApprovalResult,
  type TransitHaproxyRouteCreateRealExecutionResult,
  type TransitWorkerAcceptanceResult,
  type TransitWorkerUpgradeAcceptanceResult,
  type TransitWorkerInstallCommandGenerationResult,
  type TransitRouteWorkerCreateExecuteResponse,
  type TransitRouteData,
  type TransitRouteListResult,
  type TransitResourcePayload,
  type WorkerCommandData,
} from "@/lib/api";

type TransitResourceDraftFormState = {
  name: string;
  provider: string;
  entryHost: string;
  sshHost: string;
  sshPort: string;
  sshUsername: string;
  entryRegion: string;
  exitRegion: string;
  bandwidthMbps: string;
  trafficLimitGb: string;
  plannedInterface: string;
  protocolHint: "haproxy_tcp" | "socat" | "unknown";
  hasSsh: boolean;
  notes: string;
};

type TransitRouteDraftState = {
  transitResourceId: string;
  landingNodeId: string;
  plannedListenPort: string;
  forwardingMethod: TransitForwardingMethod;
  purpose: string;
};

type TransitRouteCreateFormState = {
  routeName: string;
  transitResourceId: string;
  landingNodeId: string;
  listenPort: string;
  forwardingMethod: TransitCreateForwardingMethod;
  firewallConfirmed: boolean;
};

type TransitRouteCreateStep =
  | "idle"
  | "preflight_create"
  | "preflight_running"
  | "command_create"
  | "command_running"
  | "refresh"
  | "export_link"
  | "complete"
  | "failed";

type TransitRouteWorkerCreatePlanResult = {
  command: WorkerCommandData;
  target_worker_id: string;
  target_worker_version: string | null;
  minimum_supported_worker_version: string;
  dry_run: boolean;
  planned_service_name: string;
  planned_listen_port: number;
  landing_target_host: string;
  landing_target_port: number;
  safety_boundary: string[];
};

type DeleteFlowMode = "remote_cleanup" | "offline_local_remove";

type HaproxyReadinessConfirmations = {
  securityGroup: boolean;
  cloudFirewall: boolean;
  serverFirewall: boolean;
  noCutover: boolean;
  noShareLinkMutation: boolean;
  noFullClientLink: boolean;
};

const emptyHaproxyReadinessConfirmations: HaproxyReadinessConfirmations = {
  securityGroup: false,
  cloudFirewall: false,
  serverFirewall: false,
  noCutover: false,
  noShareLinkMutation: false,
  noFullClientLink: false,
};

const HAPROXY_FINAL_APPROVAL_TEXT = "CONFIRM_HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_ONLY";
const HAPROXY_REAL_EXECUTION_TEXT = "CONFIRM_REAL_HAPROXY_ROUTE_CREATE_23843";

function isOfflineLocalRemoveOffer(data: unknown): data is RemoteCleanupUnavailableData {
  return Boolean(
    data &&
      typeof data === "object" &&
      "offline_local_remove_available" in data &&
      (data as RemoteCleanupUnavailableData).offline_local_remove_available,
  );
}

function requiredDeleteConfirmText(mode: DeleteFlowMode) {
  return mode === "offline_local_remove" ? OFFLINE_LOCAL_REMOVE_CONFIRM_TEXT : REMOTE_CLEANUP_CONFIRM_TEXT;
}

function transitRouteDeleteConfirmText(route: TransitRouteData, mode: DeleteFlowMode) {
  if (mode === "offline_local_remove") {
    return `我确认离线本地移除 ${route.name}，并理解远程 ${route.listen_port} 可能仍在监听`;
  }
  if (isHaproxyForwardingMethod(route.forwarding_method)) {
    return `我确认远程清理删除 ${route.name} 并接受 ${route.listen_port} 临时不可用`;
  }
  return `我确认远程清理删除 ${route.name} 并接受 ${route.listen_port} 临时不可用`;
}

function SafeDeleteModal({
  title,
  description,
  offlineDescription,
  targetLabel,
  requiredConfirmTextOverride,
  remoteConfirmButtonLabel,
  offlineConfirmButtonLabel,
  mode,
  confirmText,
  submitting,
  onCancel,
  onConfirmTextChange,
  onConfirm,
}: {
  title: string;
  description: ReactNode;
  offlineDescription?: ReactNode;
  targetLabel: string;
  requiredConfirmTextOverride?: string;
  remoteConfirmButtonLabel?: string;
  offlineConfirmButtonLabel?: string;
  mode: DeleteFlowMode;
  confirmText: string;
  submitting: boolean;
  onCancel: () => void;
  onConfirmTextChange: (value: string) => void;
  onConfirm: () => void;
}) {
  const requiredConfirmText = requiredConfirmTextOverride ?? requiredDeleteConfirmText(mode);
  const isOfflineLocalRemove = mode === "offline_local_remove";
  return (
    <div className="modal-backdrop" role="presentation">
      <div className="modal-card safe-delete-modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-header">
          <h3>{isOfflineLocalRemove ? "离线本地移除确认" : title}</h3>
          <button className="ghost-button" type="button" onClick={onCancel}>
            取消
          </button>
        </div>
        <div className="failure-box safe-delete-warning">
          <strong>{isOfflineLocalRemove ? "仅本地移除记录" : "真实远程清理"}</strong>
          {isOfflineLocalRemove ? (
            offlineDescription ?? (
              <>
                <span>当前资源对应的 Worker 离线，系统无法远程清理该服务器上的服务。</span>
                <span>如果该资源已到期、无法登录、已释放，或你确认不再使用，可以只从 LiveLine Console 本地移除记录。</span>
                <span>此操作不会连接远程服务器，不会停止远程服务，不会修改防火墙，不会 cutover。</span>
              </>
            )
          ) : (
            <span>{description}</span>
          )}
        </div>
        <div className="server-delete-target">{targetLabel}</div>
        <div className="delete-safety-grid">
          <span>远程清理是否会执行</span>
          <strong>{isOfflineLocalRemove ? "否" : "是"}</strong>
          <span>是否会创建 Worker command</span>
          <strong>{isOfflineLocalRemove ? "否" : "是"}</strong>
          <span>是否会 cutover</span>
          <strong>否</strong>
          <span>是否会修改 share_link</span>
          <strong>否</strong>
        </div>
        <label className="safe-delete-input">
          输入 {requiredConfirmText} 后才能{isOfflineLocalRemove ? "本地移除记录" : "创建远程清理任务"}
          <input value={confirmText} onChange={(event) => onConfirmTextChange(event.target.value)} placeholder={requiredConfirmText} />
        </label>
        <div className="modal-actions">
          <button className="secondary" type="button" onClick={onCancel}>
            取消
          </button>
          <button className="danger" disabled={submitting || confirmText !== requiredConfirmText} type="button" onClick={onConfirm}>
            {isOfflineLocalRemove ? offlineConfirmButtonLabel ?? "确认离线本地移除" : remoteConfirmButtonLabel ?? "确认远程清理删除"}
          </button>
        </div>
      </div>
    </div>
  );
}

const requiredTransitWorkerVersion = "0.1.25-stage-3.3.137-hotfix-2";
const transitWorkerBinaryChecksum = "fbc2e240bbb8cd64962e5151752cf410951673efadae704d192ca83f2ab89d2b";
const transitWorkerPublicControllerUrl = "http://my-con.golirong.xyz:8200";
const transitWorkerPlaceholderToken = "<generated-in-later-stage>";
const transitWorkerInstallCommandApprovalConfirmText = "CONFIRM_GENERATE_WORKER_INSTALL_COMMAND_LATER";
const transitWorkerRealCommandApprovalConfirmText = "CONFIRM_REAL_WORKER_INSTALL_COMMAND_GENERATION_NEXT_STAGE";

const emptyTransitResourceDraftForm: TransitResourceDraftFormState = {
  name: "",
  provider: "",
  entryHost: "",
  sshHost: "",
  sshPort: "22",
  sshUsername: "root",
  entryRegion: "",
  exitRegion: "",
  bandwidthMbps: "",
  trafficLimitGb: "",
  plannedInterface: "eth0",
  protocolHint: "haproxy_tcp",
  hasSsh: false,
  notes: "",
};

const emptyRouteDraft: TransitRouteDraftState = {
  transitResourceId: "",
  landingNodeId: "",
  plannedListenPort: "23843",
  forwardingMethod: "socat",
  purpose: "直播",
};

const approvedTransitRouteName = "hk-socat-live-23843";
const approvedTransitListenPort = 23843;
const approvedTransitRealCreateStage = "Stage 3.3.73d-transit-route-real-create-code-path";
const transitCreateTerminalStatuses = new Set(["succeeded", "failed", "cancelled", "expired"]);
const cleanupCommandTerminalStatuses = new Set(["succeeded", "failed", "cancelled", "timeout", "expired"]);
const cleanupCommandPollIntervalMs = 2000;
const cleanupCommandMaxPolls = 30;
const workerCommandNotFoundRetryMs = 30_000;

const transitRouteCreateProgressLabels: Record<TransitRouteCreateStep, string> = {
  idle: "准备中",
  preflight_create: "创建只读预检",
  preflight_running: "预检中",
  command_create: "创建中转命令",
  command_running: "创建 socat 服务 / 检查监听",
  refresh: "刷新中转链路",
  export_link: "生成客户端链接",
  complete: "完成",
  failed: "创建未完成",
};

function forwardingMethodLabel(method: string | null | undefined) {
  if (method === "haproxy_tcp") {
    return "HAProxy TCP mode";
  }
  if (method === "socat") {
    return "socat";
  }
  if (method === "gost") {
    return "gost";
  }
  return method || "-";
}

function isHaproxyForwardingMethod(method: string | null | undefined) {
  const cleaned = (method || "").trim().toLowerCase().replaceAll("-", "_");
  return cleaned === "haproxy" || cleaned === "haproxy_tcp";
}

function defaultTransitRouteName(method: TransitCreateForwardingMethod, listenPort: string) {
  const cleanedPort = listenPort.trim() || String(approvedTransitListenPort);
  return method === "haproxy_tcp" ? `haproxy-tcp-${cleanedPort}` : approvedTransitRouteName;
}

function transitRouteCreateProgressLabel(step: TransitRouteCreateStep, method: TransitCreateForwardingMethod) {
  if (step === "command_running") {
    return method === "haproxy_tcp" ? "创建 HAProxy TCP 服务 / 检查监听" : "创建 socat 服务 / 检查监听";
  }
  return transitRouteCreateProgressLabels[step];
}

function findTransitPortConflictRoute(
  routes: TransitRouteData[],
  transitResourceId: string | null | undefined,
  listenPort: number | null,
) {
  if (!transitResourceId || listenPort === null) {
    return null;
  }
  return (
    routes.find(
      (route) =>
        route.transit_resource_id === transitResourceId &&
        route.listen_port === listenPort &&
        !route.deleted_at &&
        ["active", "creating"].includes(route.status),
    ) ?? null
  );
}

function duplicateTransitPortMessage(method: TransitCreateForwardingMethod, listenPort: number, route: TransitRouteData) {
  if (method === "haproxy_tcp") {
    return `该中转服务器的端口 ${listenPort} 已存在可用中转链路：${route.name}。请直接使用现有链路的临时导出，或先远程清理删除旧链路后再创建。`;
  }
  return `该中转服务器的端口 ${listenPort} 已存在中转链路：${route.name}。请直接使用现有链路，或先远程清理删除旧链路后再创建。`;
}

const emptyRouteCreateForm: TransitRouteCreateFormState = {
  routeName: approvedTransitRouteName,
  transitResourceId: "",
  landingNodeId: "",
  listenPort: String(approvedTransitListenPort),
  forwardingMethod: "socat",
  firewallConfirmed: false,
};

function statusClass(status: string) {
  if (["active", "online", "worker_online", "succeeded", "success", "passed"].includes(status)) {
    return "ok";
  }
  if (["failed", "error", "deleted", "offline", "stale"].includes(status)) {
    return "bad";
  }
  return "warn";
}

function displayStatusLabel(status: string | null | undefined) {
  const labels: Record<string, string> = {
    active: "已启用",
    disabled: "已停用",
    pending_worker: "等待 Worker",
    worker_online: "Worker 在线",
    worker_offline: "Worker 离线",
    online: "在线",
    stale: "心跳过期 / 离线",
    offline: "离线",
    unchecked: "未检测",
    creating: "创建中",
    error: "异常",
    deleted: "已删除",
    succeeded: "成功",
    failed: "失败",
    running: "执行中",
    pending: "等待中",
    cancelled: "已取消",
    timeout: "超时",
    expired: "已过期",
  };
  return labels[status ?? ""] ?? status ?? "未知";
}

function formatTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "-";
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

function nullableText(value: string) {
  const cleaned = value.trim();
  return cleaned ? cleaned : null;
}

function nullableInteger(value: string) {
  const cleaned = value.trim();
  if (!cleaned) {
    return null;
  }
  if (!/^\d+$/.test(cleaned)) {
    return null;
  }
  const parsed = Number(cleaned);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
}

function nullableDecimal(value: string) {
  const cleaned = value.trim();
  if (!cleaned) {
    return null;
  }
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function protocolHintLabel(value: string | null | undefined) {
  const labels: Record<string, string> = {
    haproxy_tcp: "HAProxy TCP",
    socat: "socat",
    tcp: "TCP",
    udp: "UDP",
    tcp_udp: "TCP/UDP",
    unknown: "待确认",
  };
  return labels[value ?? ""] ?? value ?? "待确认";
}

function buildTransitResourceDraftNotes(form: TransitResourceDraftFormState) {
  const lines = [
    "Draft resource only. No Worker install credential generated.",
    `Planned interface: ${form.plannedInterface.trim() || "pending"}`,
    `Preferred forwarding: ${form.protocolHint}`,
  ];
  const notes = form.notes.trim();
  if (notes) {
    lines.push(`Operator notes: ${notes}`);
  }
  return lines.join("\n");
}

function noteValue(resource: TransitResourceData, label: string) {
  const notes = resource.notes ?? "";
  const prefix = `${label}:`;
  const line = notes
    .split(/\r?\n/)
    .map((value) => value.trim())
    .find((value) => value.toLowerCase().startsWith(prefix.toLowerCase()));
  if (!line) {
    return null;
  }
  const value = line.slice(prefix.length).trim();
  return value || null;
}

function plannedInterfaceForResource(resource: TransitResourceData) {
  return resource.worker_interface_name ?? noteValue(resource, "Planned interface") ?? "待确认";
}

function protocolIntentForResource(resource: TransitResourceData) {
  const fromNotes = noteValue(resource, "Preferred forwarding");
  return protocolHintLabel(fromNotes ?? resource.protocol_hint);
}

function sshSummaryForResource(resource: TransitResourceData) {
  if (!resource.has_ssh) {
    return "未记录 SSH 管理元信息";
  }
  const host = resource.ssh_host ?? "待确认";
  const port = resource.ssh_port ?? 22;
  const username = resource.ssh_username ?? "root";
  return `${username}@${host}:${port}`;
}

function transitWorkerInstallPlaceholderCommand() {
  return [
    `curl -fsSL ${transitWorkerPublicControllerUrl}/worker/install.sh | \\`,
    "  sudo bash -s -- \\",
    `  --controller-url ${transitWorkerPublicControllerUrl} \\`,
    `  --worker-token ${transitWorkerPlaceholderToken} \\`,
    "  --role transit",
  ].join("\n");
}

function transitWorkerApprovalChecklist(resource: TransitResourceData) {
  return [
    "Stage 3.3.130 Worker install approval preview",
    "",
    `Resource: ${resource.name}`,
    `Status: ${resource.status}`,
    `Entry host: ${resource.entry_host ?? "待确认"}`,
    `SSH: ${sshSummaryForResource(resource)}`,
    `Entry region: ${resource.entry_region ?? "待确认"}`,
    `Exit region: ${resource.exit_region ?? "待确认"}`,
    `Planned interface: ${plannedInterfaceForResource(resource)}`,
    `Protocol intent: ${protocolIntentForResource(resource)}`,
    `Required Worker version: ${requiredTransitWorkerVersion}`,
    `Worker binary checksum: ${transitWorkerBinaryChecksum}`,
    `Public controller URL: ${transitWorkerPublicControllerUrl}`,
    "",
    "Placeholder command only, not executable in this stage:",
    transitWorkerInstallPlaceholderCommand(),
    "",
    "Go / No-Go checks:",
    "- Public controller backend health returns 200.",
    "- Worker binary local/public checksum match.",
    "- New VPS can access the public controller URL.",
    "- New VPS has root or sudo, systemd, and curl.",
    "- Command must use the public controller URL, not localhost or 127.0.0.1.",
    "- Do not put SSH private keys, passwords, Worker tokens, or secrets in notes, README, PR, or chat.",
    "",
    "Stage 3.3.130 confirmations:",
    "- No Worker token generated.",
    "- No real install command generated.",
    "- No Worker installed.",
    "- Real installation requires a later independent approval stage.",
  ].join("\n");
}

function transitWorkerCommandGenerationApprovalChecklist(resource: TransitResourceData) {
  return [
    "Stage 3.3.131 Worker install command generation approval",
    "",
    `Resource: ${resource.name}`,
    `Status: ${resource.status}`,
    `Entry host: ${resource.entry_host ?? "待补充"}`,
    `SSH: ${sshSummaryForResource(resource)}`,
    `Entry region: ${resource.entry_region ?? "待确认"}`,
    `Exit region: ${resource.exit_region ?? "待确认"}`,
    `Planned interface: ${plannedInterfaceForResource(resource)}`,
    `Protocol intent: ${protocolIntentForResource(resource)}`,
    `Required Worker version: ${requiredTransitWorkerVersion}`,
    `Worker binary checksum: ${transitWorkerBinaryChecksum}`,
    `Public controller URL: ${transitWorkerPublicControllerUrl}`,
    "",
    "Approval requirements:",
    "- Generate one-time Worker token only in a later approved stage.",
    "- Generate install command only in a later approved stage.",
    "- Do not execute SSH or remote command in this approval stage.",
    "- Do not store token in docs, README, PR, logs, chat, or notes.",
    "- Use public controller URL, not localhost or 127.0.0.1.",
    "- Confirm the real VPS can access the public controller.",
    "- Confirm root/sudo, systemd, and curl are available.",
    "",
    "Typed confirmation required later:",
    transitWorkerInstallCommandApprovalConfirmText,
    "",
    "Placeholder token:",
    transitWorkerPlaceholderToken,
    "",
    "Placeholder command only, not executable in this stage:",
    transitWorkerInstallPlaceholderCommand(),
  ].join("\n");
}

function transitWorkerInstallDryRunRows(resource: TransitResourceData) {
  return [
    ["mode", "dry_run"],
    ["resource_id", resource.id],
    ["resource_name", resource.name],
    ["resource_status", resource.status],
    ["role", "transit"],
    ["controller_url", transitWorkerPublicControllerUrl],
    ["target_worker_version", requiredTransitWorkerVersion],
    ["worker_binary_checksum", transitWorkerBinaryChecksum],
    ["token_status", "not_generated"],
    ["install_command_status", "placeholder_only"],
    ["remote_execution", "disabled"],
    ["worker_command_created", "false"],
  ] as const;
}

function transitWorkerInstallDryRunChecks(resource: TransitResourceData, typedConfirmed: boolean) {
  const controllerUrlIsPublic =
    /^https?:\/\//.test(transitWorkerPublicControllerUrl) &&
    !/localhost|127\.0\.0\.1/.test(transitWorkerPublicControllerUrl);
  return [
    ["typed confirmation", typedConfirmed ? "通过" : "未通过", typedConfirmed],
    [
      "resource status 是否 pending_worker",
      resource.status === "pending_worker" ? "通过" : `未通过：${resource.status}`,
      resource.status === "pending_worker",
    ],
    ["entry_host 是否存在", resource.entry_host ? "通过" : "待补充", Boolean(resource.entry_host)],
    [
      "SSH metadata 是否完整或待补充",
      resource.has_ssh ? `完整或待确认：${sshSummaryForResource(resource)}` : "待补充或后续确认",
      true,
    ],
    ["controller_url 是否公网 URL", controllerUrlIsPublic ? "通过" : "未通过", controllerUrlIsPublic],
    [
      "placeholder token 是否仍为 <generated-in-later-stage>",
      transitWorkerPlaceholderToken === "<generated-in-later-stage>" ? "通过" : "未通过",
      transitWorkerPlaceholderToken === "<generated-in-later-stage>",
    ],
    ["是否禁止 localhost / 127.0.0.1", controllerUrlIsPublic ? "通过" : "未通过", controllerUrlIsPublic],
    ["是否禁止真实 token 输出", "通过：real token output forbidden", true],
  ] as const;
}

function transitWorkerInstallDryRunResultText(resource: TransitResourceData, typedConfirmed: boolean) {
  const rows = transitWorkerInstallDryRunRows(resource).map(([label, value]) => `${label}: ${value}`);
  const checks = transitWorkerInstallDryRunChecks(resource, typedConfirmed).map(([label, value]) => `${label}: ${value}`);
  return [
    "Stage 3.3.132 Worker install command generation dry-run",
    "",
    ...rows,
    "",
    "dry-run checks:",
    ...checks,
    "",
    "placeholder command template only:",
    transitWorkerInstallPlaceholderCommand(),
    "",
    "Safety:",
    "- no Worker token generated",
    "- no real install command generated",
    "- no Worker install performed",
    "- no Worker command created",
    "- no SSH or remote command executed",
  ].join("\n");
}

function transitWorkerRealCommandApprovalRows(resource: TransitResourceData) {
  return [
    ["当前资源名称", resource.name],
    ["当前资源状态", resource.status],
    ["entry_host", resource.entry_host ?? "待确认"],
    ["SSH host / port / username", sshSummaryForResource(resource)],
    ["入口地区 / 出口地区", `${resource.entry_region ?? "待确认"} / ${resource.exit_region ?? "待确认"}`],
    ["计划网卡", plannedInterfaceForResource(resource)],
    ["协议意图", protocolIntentForResource(resource)],
    ["公网主控 URL", transitWorkerPublicControllerUrl],
    ["目标 Worker 版本", requiredTransitWorkerVersion],
    ["Worker binary checksum", transitWorkerBinaryChecksum],
    ["真实 token 生成", "仍未执行"],
    ["真实 install command 生成", "仍未执行"],
    ["远程安装", "仍未执行"],
  ] as const;
}

function transitWorkerRealCommandReadinessChecks(resource: TransitResourceData) {
  const controllerUrlIsPublic =
    /^https?:\/\//.test(transitWorkerPublicControllerUrl) &&
    !/localhost|127\.0\.0\.1/.test(transitWorkerPublicControllerUrl);
  return [
    ["测试 VPS 已真实存在", "需人工确认"],
    ["测试 VPS 公网 IP / 域名已确认", resource.entry_host ? `已填写：${resource.entry_host}` : "待确认"],
    ["SSH host / port / username 已确认", resource.has_ssh ? sshSummaryForResource(resource) : "待补充或后续确认"],
    ["root 或 sudo 权限已确认", "需人工确认"],
    ["systemd 已确认", "需人工确认"],
    ["curl 已确认", "需人工确认"],
    ["测试 VPS 能访问公网主控", "需人工确认"],
    ["安装命令必须使用公网主控 URL", controllerUrlIsPublic ? "通过" : "未通过"],
    ["禁止 localhost / 127.0.0.1", controllerUrlIsPublic ? "通过" : "未通过"],
    ["真实 token 不得写入 README / docs / PR / chat / logs / notes", "必须遵守"],
    ["真实安装仍必须在后续独立阶段执行", "必须遵守"],
  ] as const;
}

function transitWorkerRealCommandApprovalPackage(resource: TransitResourceData, typedConfirmed: boolean) {
  return [
    "Stage 3.3.133 Real Worker install command generation approval",
    "",
    "Resource:",
    `Name: ${resource.name}`,
    `Status: ${resource.status}`,
    `Entry host: ${resource.entry_host ?? "待确认"}`,
    `SSH: ${sshSummaryForResource(resource)}`,
    `Entry region: ${resource.entry_region ?? "待确认"}`,
    `Exit region: ${resource.exit_region ?? "待确认"}`,
    `Planned interface: ${plannedInterfaceForResource(resource)}`,
    `Protocol intent: ${protocolIntentForResource(resource)}`,
    `Required Worker version: ${requiredTransitWorkerVersion}`,
    `Worker binary checksum: ${transitWorkerBinaryChecksum}`,
    `Public controller URL: ${transitWorkerPublicControllerUrl}`,
    "",
    "Real VPS readiness:",
    "- Test VPS exists.",
    "- SSH host / port / username confirmed.",
    "- root/sudo confirmed.",
    "- systemd confirmed.",
    "- curl confirmed.",
    "- VPS can access public controller.",
    "- command must use public controller URL.",
    "- no localhost / 127.0.0.1.",
    "- token must not be stored in docs, README, PR, logs, chat, or notes.",
    "",
    "Typed confirmation required:",
    transitWorkerRealCommandApprovalConfirmText,
    "",
    `Typed confirmation status: ${typedConfirmed ? "passed" : "not_passed"}`,
    "",
    "Token status:",
    "not_generated",
    "",
    "Install command status:",
    "not_generated",
    "",
    "Remote execution:",
    "disabled",
    "",
    "Next stage required:",
    "Generate one-time Worker token / install command only after explicit approval.",
  ].join("\n");
}

function transitResourcePayloadFromForm(
  form: TransitResourceDraftFormState,
  status = "pending_worker",
): TransitResourcePayload {
  const sshPort = nullableInteger(form.sshPort);
  return {
    name: form.name.trim(),
    resource_type: "server",
    provider: nullableText(form.provider),
    entry_host: nullableText(form.entryHost),
    entry_port: null,
    entry_region: nullableText(form.entryRegion),
    exit_region: nullableText(form.exitRegion),
    bandwidth_mbps: nullableInteger(form.bandwidthMbps),
    traffic_limit_gb: nullableDecimal(form.trafficLimitGb),
    traffic_used_gb: null,
    protocol_hint: form.protocolHint,
    has_ssh: form.hasSsh,
    ssh_host: form.hasSsh ? nullableText(form.sshHost) : null,
    ssh_port: form.hasSsh ? sshPort : null,
    ssh_username: form.hasSsh ? nullableText(form.sshUsername) : null,
    status,
    expires_at: null,
    notes: buildTransitResourceDraftNotes(form),
  };
}

function draftFormFromResource(resource: TransitResourceData): TransitResourceDraftFormState {
  return {
    name: resource.name,
    provider: resource.provider ?? "",
    entryHost: resource.entry_host ?? "",
    sshHost: resource.ssh_host ?? "",
    sshPort: resource.ssh_port ? String(resource.ssh_port) : "22",
    sshUsername: resource.ssh_username ?? "root",
    entryRegion: resource.entry_region ?? "",
    exitRegion: resource.exit_region ?? "",
    bandwidthMbps: resource.bandwidth_mbps !== null ? String(resource.bandwidth_mbps) : "",
    trafficLimitGb: resource.traffic_limit_gb !== null ? String(resource.traffic_limit_gb) : "",
    plannedInterface: resource.worker_interface_name ?? "eth0",
    protocolHint:
      resource.protocol_hint === "haproxy_tcp" || resource.protocol_hint === "socat"
        ? resource.protocol_hint
        : "unknown",
    hasSsh: resource.has_ssh,
    notes: resource.notes ?? "",
  };
}

function parsePort(value: string) {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) {
    return null;
  }
  const port = Number(trimmed);
  return Number.isInteger(port) && port >= 1 && port <= 65535 ? port : null;
}

function sleep(ms: number) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function isPlanningSelectableTransitResource(resource: TransitResourceData) {
  return (
    resource.resource_type === "server" &&
    (resource.status === "active" ||
      resource.worker_online === true ||
      resource.display_status === "online" ||
      resource.display_status === "worker_online")
  );
}

function targetPortForNode(node: NodeData | null) {
  return typeof node?.port === "number" ? node.port : 0;
}

function landingHostForNode(node: NodeData | null) {
  return node?.vps_ip ?? "";
}

async function ensureCsrfToken() {
  const csrf = await apiFetch<CsrfResult>("/api/auth/csrf");
  if (!csrf.success) {
    throw new Error(csrf.message);
  }
  return csrf.data.csrf_token;
}

async function copyText(value: string) {
  if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
    throw new Error("Clipboard API unavailable");
  }
  await navigator.clipboard.writeText(value);
}

export function TransitServersPanel() {
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("中转服务器页面可保存待安装 Worker 的草稿资源；不会生成 Worker token 或执行远程安装。");
  const [modalMode, setModalMode] = useState<"add" | "edit" | "delete" | null>(null);
  const [selectedResource, setSelectedResource] = useState<TransitResourceData | null>(null);
  const [draftForm, setDraftForm] = useState<TransitResourceDraftFormState>(emptyTransitResourceDraftForm);
  const [workerCommandsByWorkerId, setWorkerCommandsByWorkerId] = useState<Record<string, WorkerCommandData[]>>({});
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deleteMode, setDeleteMode] = useState<DeleteFlowMode>("remote_cleanup");
  const [approvalPreviewResource, setApprovalPreviewResource] = useState<TransitResourceData | null>(null);
  const [approvalPreviewCopied, setApprovalPreviewCopied] = useState(false);
  const [commandApprovalConfirmText, setCommandApprovalConfirmText] = useState("");
  const [commandApprovalCopied, setCommandApprovalCopied] = useState(false);
  const [commandDryRunCopied, setCommandDryRunCopied] = useState(false);
  const [placeholderCommandCopied, setPlaceholderCommandCopied] = useState(false);
  const [realCommandApprovalConfirmText, setRealCommandApprovalConfirmText] = useState("");
  const [realCommandApprovalCopied, setRealCommandApprovalCopied] = useState(false);
  const [workerInstallCommandResult, setWorkerInstallCommandResult] =
    useState<TransitWorkerInstallCommandGenerationResult | null>(null);
  const [workerInstallCommandCopied, setWorkerInstallCommandCopied] = useState(false);
  const [workerInstallCommandGenerating, setWorkerInstallCommandGenerating] = useState(false);
  const [workerAcceptanceResult, setWorkerAcceptanceResult] = useState<TransitWorkerAcceptanceResult | null>(null);
  const [workerAcceptanceLoading, setWorkerAcceptanceLoading] = useState(false);
  const [workerUpgradeAcceptanceResult, setWorkerUpgradeAcceptanceResult] =
    useState<TransitWorkerUpgradeAcceptanceResult | null>(null);
  const [workerUpgradeAcceptanceLoading, setWorkerUpgradeAcceptanceLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function loadResources() {
    setLoading(true);
    const result = await apiFetch<TransitResourceListResult>("/api/transit-resources?resource_type=server");
    if (!result.success) {
      setMessage(`${result.error_code}: ${result.message}`);
      setLoading(false);
      return;
    }
    setResources(result.data.resources);
    await Promise.all(
      result.data.resources
        .filter((resource) => resource.worker_id)
        .map((resource) => loadWorkerCommands(resource.worker_id as string)),
    );
    setMessage("中转服务器列表已刷新。");
    setLoading(false);
  }

  async function loadWorkerCommands(workerId: string) {
    const result = await listWorkerCommands(workerId);
    if (result.success) {
      setWorkerCommandsByWorkerId((current) => ({ ...current, [workerId]: result.data.commands }));
    }
  }

  function scheduleResourceRefresh(command?: WorkerCommandData | null) {
    [1500, 4000].forEach((delay) => {
      window.setTimeout(() => {
        void loadResources();
        if (command?.target_worker_id) {
          void loadWorkerCommands(command.target_worker_id);
        } else if (command?.worker_id) {
          void loadWorkerCommands(command.worker_id);
        }
      }, delay);
    });
  }

  async function refreshWhenResourceCleanupCommandCompletes(command?: WorkerCommandData | null) {
    if (!command?.id) {
      return;
    }

    let latestCommand: WorkerCommandData | null = command;

    for (let attempt = 0; attempt < cleanupCommandMaxPolls; attempt += 1) {
      await sleep(cleanupCommandPollIntervalMs);
      const result = await getWorkerCommand(command.id);
      if (result.success) {
        latestCommand = result.data;
        if (cleanupCommandTerminalStatuses.has(result.data.status)) {
          const workerId = result.data.target_worker_id || result.data.worker_id;
          await loadResources();
          if (workerId) {
            await loadWorkerCommands(workerId);
          }
          setMessage(
            result.data.status === "succeeded"
              ? "清理任务已完成，中转服务器列表已自动刷新。"
              : `清理任务已进入终态：${displayStatusLabel(result.data.status)}。列表已自动刷新，请查看最近命令详情。`,
          );
          return;
        }
      }
    }

    await loadResources();
    const workerId = latestCommand?.target_worker_id || latestCommand?.worker_id;
    if (workerId) {
      await loadWorkerCommands(workerId);
    }
    setMessage("清理任务仍在执行，中转服务器列表已再次刷新；请稍后查看任务中心或再次刷新。");
  }

  useEffect(() => {
    void loadResources();
  }, []);

  function closeModal() {
    setModalMode(null);
    setSelectedResource(null);
    setDraftForm(emptyTransitResourceDraftForm);
    setDeleteConfirmText("");
    setDeleteMode("remote_cleanup");
  }

  function closeApprovalPreview() {
    setApprovalPreviewResource(null);
    setApprovalPreviewCopied(false);
    setCommandApprovalConfirmText("");
    setCommandApprovalCopied(false);
    setCommandDryRunCopied(false);
    setPlaceholderCommandCopied(false);
    setRealCommandApprovalConfirmText("");
    setRealCommandApprovalCopied(false);
    setWorkerInstallCommandResult(null);
    setWorkerInstallCommandCopied(false);
    setWorkerInstallCommandGenerating(false);
    setWorkerAcceptanceResult(null);
    setWorkerAcceptanceLoading(false);
    setWorkerUpgradeAcceptanceResult(null);
    setWorkerUpgradeAcceptanceLoading(false);
  }

  function openAdd() {
    setSelectedResource(null);
    setDraftForm(emptyTransitResourceDraftForm);
    setModalMode("add");
  }

  function openEdit(resource: TransitResourceData) {
    setSelectedResource(resource);
    setDraftForm(draftFormFromResource(resource));
    setModalMode("edit");
  }

  function openDeleteResource(resource: TransitResourceData) {
    setSelectedResource(resource);
    setDeleteConfirmText("");
    setDeleteMode(resource.worker_online ? "remote_cleanup" : "offline_local_remove");
    setModalMode("delete");
  }

  function openWorkerInstallApprovalPreview(resource: TransitResourceData) {
    setApprovalPreviewResource(resource);
    setApprovalPreviewCopied(false);
    setCommandApprovalConfirmText("");
    setCommandApprovalCopied(false);
    setCommandDryRunCopied(false);
    setPlaceholderCommandCopied(false);
    setRealCommandApprovalConfirmText("");
    setRealCommandApprovalCopied(false);
    setWorkerInstallCommandResult(null);
    setWorkerInstallCommandCopied(false);
    setWorkerInstallCommandGenerating(false);
    setWorkerAcceptanceResult(null);
    setWorkerAcceptanceLoading(false);
    setWorkerUpgradeAcceptanceResult(null);
    setWorkerUpgradeAcceptanceLoading(false);
  }

  async function copyWorkerInstallApprovalChecklist(resource: TransitResourceData) {
    try {
      await copyText(transitWorkerApprovalChecklist(resource));
      setApprovalPreviewCopied(true);
      setMessage("Worker 安装审批清单已复制；内容不包含真实 token 或密钥。");
    } catch (error) {
      setApprovalPreviewCopied(false);
      setMessage(error instanceof Error ? `复制失败：${error.message}` : "复制审批清单失败。");
    }
  }

  async function copyWorkerCommandGenerationApprovalPackage(resource: TransitResourceData) {
    try {
      await copyText(transitWorkerCommandGenerationApprovalChecklist(resource));
      setCommandApprovalCopied(true);
      setMessage("生成命令审批包已复制；内容只包含占位 token 和安全检查。");
    } catch (error) {
      setCommandApprovalCopied(false);
      setMessage(error instanceof Error ? `复制失败：${error.message}` : "复制生成命令审批包失败。");
    }
  }

  async function copyWorkerInstallDryRunResult(resource: TransitResourceData) {
    try {
      await copyText(transitWorkerInstallDryRunResultText(resource, commandApprovalConfirmed));
      setCommandDryRunCopied(true);
      setMessage("Worker install command dry-run 结果已复制；内容只包含占位 token 和检查结果。");
    } catch (error) {
      setCommandDryRunCopied(false);
      setMessage(error instanceof Error ? `复制失败：${error.message}` : "复制 dry-run 结果失败。");
    }
  }

  async function copyWorkerInstallPlaceholderCommand() {
    try {
      await copyText(transitWorkerInstallPlaceholderCommand());
      setPlaceholderCommandCopied(true);
      setMessage("占位命令模板已复制；仍不是可执行真实安装命令。");
    } catch (error) {
      setPlaceholderCommandCopied(false);
      setMessage(error instanceof Error ? `复制失败：${error.message}` : "复制占位命令模板失败。");
    }
  }

  async function copyWorkerRealCommandApprovalPackage(resource: TransitResourceData) {
    const typedConfirmed = realCommandApprovalConfirmText === transitWorkerRealCommandApprovalConfirmText;
    try {
      await copyText(transitWorkerRealCommandApprovalPackage(resource, typedConfirmed));
      setRealCommandApprovalCopied(true);
      setMessage("真实生成命令最终审批包已复制；内容不包含真实 token 或真实安装命令。");
    } catch (error) {
      setRealCommandApprovalCopied(false);
      setMessage(error instanceof Error ? `复制失败：${error.message}` : "复制真实生成命令最终审批包失败。");
    }
  }

  async function submitWorkerInstallCommandGeneration(resource: TransitResourceData) {
    if (resource.status !== "pending_worker" || realCommandApprovalConfirmText !== transitWorkerRealCommandApprovalConfirmText) {
      setMessage("请先完成真实生成命令最终审批。");
      return;
    }
    setWorkerInstallCommandGenerating(true);
    setWorkerInstallCommandCopied(false);
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await generateTransitWorkerInstallCommand(
        resource.id,
        {
          confirmation: transitWorkerRealCommandApprovalConfirmText,
          expires_in_minutes: 60,
        },
        csrfToken,
      );
      if (!result.success) {
        setWorkerInstallCommandResult(null);
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setWorkerInstallCommandResult(result.data);
      setMessage("一次性 Worker 安装命令已生成；请只在当前页面复制，不要写入 README/docs/PR/chat/logs。");
    } catch (error) {
      setWorkerInstallCommandResult(null);
      setMessage(error instanceof Error ? error.message : "生成 Worker 安装命令失败。");
    } finally {
      setWorkerInstallCommandGenerating(false);
    }
  }

  async function copyGeneratedWorkerInstallCommand() {
    if (!workerInstallCommandResult) {
      return;
    }
    try {
      await copyText(workerInstallCommandResult.install_command);
      setWorkerInstallCommandCopied(true);
      setMessage("安装命令已复制。请不要粘贴到 README/docs/PR/chat/logs。");
    } catch (error) {
      setWorkerInstallCommandCopied(false);
      setMessage(error instanceof Error ? `复制失败：${error.message}` : "复制安装命令失败。");
    }
  }

  async function refreshWorkerAcceptance(resource: TransitResourceData) {
    setWorkerAcceptanceLoading(true);
    try {
      const result = await getTransitWorkerAcceptance(resource.id);
      if (!result.success) {
        setWorkerAcceptanceResult(null);
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setWorkerAcceptanceResult(result.data);
      setMessage(result.data.accepted ? "Worker 手动安装验收通过。" : result.data.next_action);
    } catch (error) {
      setWorkerAcceptanceResult(null);
      setMessage(error instanceof Error ? error.message : "读取 Worker 验收状态失败。");
    } finally {
      setWorkerAcceptanceLoading(false);
    }
  }

  async function refreshWorkerUpgradeAcceptance(resource: TransitResourceData) {
    setWorkerUpgradeAcceptanceLoading(true);
    try {
      const result = await getTransitWorkerUpgradeAcceptance(resource.id);
      if (!result.success) {
        setWorkerUpgradeAcceptanceResult(null);
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setWorkerUpgradeAcceptanceResult(result.data);
      setMessage(result.data.acceptance_passed ? "Transit Worker 升级验收通过。" : result.data.next_action);
    } catch (error) {
      setWorkerUpgradeAcceptanceResult(null);
      setMessage(error instanceof Error ? error.message : "读取 Transit Worker 升级验收状态失败。");
    } finally {
      setWorkerUpgradeAcceptanceLoading(false);
    }
  }

  async function submitDraftResource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = transitResourcePayloadFromForm(draftForm, "pending_worker");
    if (!payload.name) {
      setMessage("请填写中转资源名称。");
      return;
    }
    if (draftForm.hasSsh && draftForm.sshPort.trim() && parsePort(draftForm.sshPort) === null) {
      setMessage("SSH 端口必须是 1-65535 之间的整数；也可以取消 SSH 管理能力。");
      return;
    }

    setSubmitting(true);
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await createTransitResource(payload, csrfToken);
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setMessage("中转 VPS 草稿已保存为 pending_worker；未生成 Worker token，未生成安装命令，未执行远程操作。");
      closeModal();
      await loadResources();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存中转 VPS 草稿失败。");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedResource) {
      return;
    }
    setSubmitting(true);
    try {
      const csrfToken = await ensureCsrfToken();
      const payload = transitResourcePayloadFromForm(draftForm, selectedResource.status);
      const result = await apiFetch<TransitResourceData>(`/api/transit-resources/${selectedResource.id}`, {
        method: "PATCH",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify(payload),
      });
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setMessage("中转服务器本地记录已更新；未执行远程操作。");
      closeModal();
      await loadResources();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存中转服务器失败。");
    } finally {
      setSubmitting(false);
    }
  }

  async function runWorkerCheck(resource: TransitResourceData) {
    if (!resource.worker_id || !resource.worker_online) {
      setMessage("Worker 未在线，不能创建检查命令。");
      return;
    }
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
      setMessage(`Worker 检查命令已创建：${result.data.command.id}`);
      await loadWorkerCommands(result.data.target_worker_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "创建 Worker 检查命令失败。");
    }
  }

  async function submitDeleteResource() {
    const requiredConfirmText = requiredDeleteConfirmText(deleteMode);
    if (!selectedResource || deleteConfirmText !== requiredConfirmText) {
      return;
    }
    setSubmitting(true);
    setMessage(
      deleteMode === "offline_local_remove"
        ? "正在本地移除中转服务器记录；不会创建 Worker command 或执行远程清理。"
        : "正在创建中转服务器远程清理任务；清理成功后才会软删除系统记录。",
    );
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await remoteCleanupDeleteTransitResource(selectedResource.id, csrfToken, requiredConfirmText);
      if (!result.success) {
        if (result.error_code === "REMOTE_CLEANUP_UNAVAILABLE" && isOfflineLocalRemoveOffer(result.data)) {
          setDeleteMode("offline_local_remove");
          setDeleteConfirmText("");
          setMessage(result.message);
          return;
        }
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setMessage(
        result.data.delete_mode === "offline_local_remove"
          ? "已本地移除记录。由于 Worker 离线，未执行远程清理。"
          : `清理任务已创建：${result.data.command_id}。等待 Worker 执行；远程清理成功后将软删除系统记录。`,
      );
      closeModal();
      await loadResources();
      scheduleResourceRefresh(result.data.command);
      void refreshWhenResourceCleanupCommandCompletes(result.data.command);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "删除中转服务器失败。");
    } finally {
      setSubmitting(false);
    }
  }

  const commandApprovalConfirmed = commandApprovalConfirmText === transitWorkerInstallCommandApprovalConfirmText;
  const realCommandApprovalConfirmed = realCommandApprovalConfirmText === transitWorkerRealCommandApprovalConfirmText;

  return (
    <section className="panel wide">
      <div className="status-row">
        <div>
          <h2>中转服务器</h2>
        </div>
        <button type="button" onClick={openAdd}>
          新增中转 VPS 草稿
        </button>
      </div>

      <div className="server-table" aria-label="中转服务器管理表格">
        <div className="server-table-row server-table-head">
          <span>名称</span>
          <span>IP 地址</span>
          <span>端口</span>
          <span>状态</span>
          <span>操作</span>
        </div>
        {loading ? <div className="server-table-empty">正在加载中转服务器。</div> : null}
        {!loading && resources.length === 0 ? <div className="server-table-empty">暂无中转服务器记录。</div> : null}
        {!loading
          ? resources.map((resource) => {
              const commands = resource.worker_id ? workerCommandsByWorkerId[resource.worker_id] ?? [] : [];
              const pendingWorkerDraft = resource.status === "pending_worker" && !resource.worker_online;
              const canOpenWorkerAcceptance =
                pendingWorkerDraft ||
                Boolean(resource.worker_id) ||
                ["online", "worker_online", "worker_offline"].includes(resource.display_status);
              return (
                <div className="server-table-group" key={resource.id}>
                  <div className="server-table-row">
                    <strong>{resource.name}</strong>
                    <span>{resource.entry_host ?? "-"}</span>
                    <span>{pendingWorkerDraft ? "待安装 Worker" : resource.worker_online ? "Worker 在线" : "Worker 接入"}</span>
                    <span className={`pill ${statusClass(resource.display_status)}`}>
                      {displayStatusLabel(resource.display_status)}
                    </span>
                    <div className="server-actions">
                      {canOpenWorkerAcceptance ? (
                        <button className="secondary" type="button" onClick={() => openWorkerInstallApprovalPreview(resource)}>
                          {pendingWorkerDraft ? "查看 Worker 安装 / 验收" : "Worker 验收"}
                        </button>
                      ) : null}
                      <button className="secondary" type="button" onClick={() => openEdit(resource)}>
                        编辑
                      </button>
                      <button
                        className="secondary"
                        disabled={!resource.worker_id || !resource.worker_online}
                        type="button"
                        onClick={() => void runWorkerCheck(resource)}
                      >
                        Worker 检查
                      </button>
                      <button className="danger" type="button" onClick={() => openDeleteResource(resource)}>
                        删除
                      </button>
                    </div>
                  </div>
                  <div className="server-row-worker">
                    Worker：
                    {resource.worker_display_status
                      ? displayStatusLabel(resource.worker_display_status)
                      : resource.worker_status
                        ? displayStatusLabel(resource.worker_status)
                        : "未注册"}；主机名：
                    {resource.worker_hostname || "暂无"}；网卡：{resource.worker_interface_name || "暂无"}；版本：
                    {resource.worker_version || "暂无"}；最后心跳：{formatTime(resource.worker_last_heartbeat_at)}
                    {pendingWorkerDraft ? (
                      <div className="transit-draft-next-steps">
                        <span>草稿 / 等待安装 Worker</span>
                        <span>要求版本：{requiredTransitWorkerVersion}</span>
                        <span>首选转发：{protocolHintLabel(resource.protocol_hint)}</span>
                        <span>HAProxy readiness：后续检查，当前未验证</span>
                      </div>
                    ) : null}
                    {commands[0] ? (
                      <div className="worker-command-status">
                        最近命令：{commands[0].command_type} / {displayStatusLabel(commands[0].status)}
                        {commands[0].result_summary ? ` / ${commands[0].result_summary}` : ""}
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })
          : null}
      </div>

      <div className="server-management-footer">
        <p className="message">{message}</p>
        <button className="secondary" type="button" onClick={() => void loadResources()}>
          刷新
        </button>
      </div>

      {modalMode === "delete" && selectedResource ? (
        <SafeDeleteModal
          title="远程清理并删除中转服务器"
          targetLabel={`${selectedResource.name} / ${selectedResource.entry_host ?? "未填写 IP"}`}
          mode={deleteMode}
          confirmText={deleteConfirmText}
          submitting={submitting}
          onCancel={closeModal}
          onConfirmTextChange={setDeleteConfirmText}
          onConfirm={() => void submitDeleteResource()}
          description={
            <>
              这会真实清理该中转服务器下所有中转链路的中转服务，并清理 transit Worker。该中转服务器将不再被 LiveLine Console 纳管。
              清理成功后，中转链路记录和中转服务器记录会被软删除。不会修改防火墙、云安全组或云防火墙。
            </>
          }
        />
      ) : null}

      {approvalPreviewResource ? (
        <div className="modal-backdrop" role="presentation">
          <div
            className="modal-card transit-worker-approval-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Worker 安装审批预览"
          >
            <div className="modal-header">
              <h3>Worker 安装审批预览</h3>
              <button className="ghost-button" type="button" onClick={closeApprovalPreview}>
                关闭预览
              </button>
            </div>
            <div className="worker-bootstrap-intro">
              <strong>Worker 安装审批与只读验收</strong>
              <span>
                这里展示安装前审批、一次性命令生成入口，以及用户手动安装后的 heartbeat 验收。刷新验收状态只读，不会 SSH、不会安装 Worker、不会创建 Worker command。
              </span>
            </div>
            <div className="transit-worker-approval-grid">
              <span>资源名称</span>
              <strong>{approvalPreviewResource.name}</strong>
              <span>资源状态</span>
              <strong>{approvalPreviewResource.status}</strong>
              <span>入口地址</span>
              <strong>{approvalPreviewResource.entry_host ?? "待确认"}</strong>
              <span>SSH 元信息</span>
              <strong>{sshSummaryForResource(approvalPreviewResource)}</strong>
              <span>入口地区</span>
              <strong>{approvalPreviewResource.entry_region ?? "待确认"}</strong>
              <span>出口地区</span>
              <strong>{approvalPreviewResource.exit_region ?? "待确认"}</strong>
              <span>计划网卡</span>
              <strong>{plannedInterfaceForResource(approvalPreviewResource)}</strong>
              <span>协议意图</span>
              <strong>{protocolIntentForResource(approvalPreviewResource)}</strong>
              <span>目标 Worker 版本</span>
              <strong>{requiredTransitWorkerVersion}</strong>
              <span>Worker binary checksum</span>
              <strong>{transitWorkerBinaryChecksum}</strong>
              <span>公网主控 URL</span>
              <strong>{transitWorkerPublicControllerUrl}</strong>
            </div>
            <div className="transit-worker-approval-section worker-acceptance-panel">
              <strong>手动安装与心跳验收</strong>
              <span>
                先在 Stage 3.3.134 生成一次性 Worker 安装命令，再由用户手动复制到真实测试中转 VPS 执行。不要在公网主控 VPS
                执行该命令，也不要把命令写入 README / docs / PR / chat / logs / notes。执行完成后点击刷新。
              </span>
              <div className="worker-install-real-approval-grid">
                <span>当前资源名称</span>
                <strong>{approvalPreviewResource.name}</strong>
                <span>当前资源状态</span>
                <strong>{approvalPreviewResource.status}</strong>
                <span>期望 Worker role</span>
                <strong>transit</strong>
                <span>期望 Worker version</span>
                <strong>{requiredTransitWorkerVersion}</strong>
                <span>是否发现 Worker</span>
                <strong className={workerAcceptanceResult?.worker_found ? "approval-state-ok" : "approval-state-warn"}>
                  {workerAcceptanceResult ? (workerAcceptanceResult.worker_found ? "是" : "否") : "待刷新"}
                </strong>
                <span>Worker 在线状态</span>
                <strong className={workerAcceptanceResult?.heartbeat_ok ? "approval-state-ok" : "approval-state-warn"}>
                  {workerAcceptanceResult ? displayStatusLabel(workerAcceptanceResult.worker_status ?? "unknown") : "待刷新"}
                </strong>
                <span>Worker hostname</span>
                <strong>{workerAcceptanceResult?.worker_hostname || "待刷新"}</strong>
                <span>Worker interface_name</span>
                <strong>{workerAcceptanceResult?.worker_interface_name || "待刷新"}</strong>
                <span>Worker version</span>
                <strong className={workerAcceptanceResult?.version_ok ? "approval-state-ok" : "approval-state-warn"}>
                  {workerAcceptanceResult?.worker_version || "待刷新"}
                </strong>
                <span>最后心跳时间</span>
                <strong>{formatTime(workerAcceptanceResult?.worker_last_heartbeat_at ?? null)}</strong>
                <span>绑定是否正确</span>
                <strong className={workerAcceptanceResult?.server_binding_ok ? "approval-state-ok" : "approval-state-warn"}>
                  {workerAcceptanceResult ? (workerAcceptanceResult.server_binding_ok ? "是" : "否") : "待刷新"}
                </strong>
                <span>验收结论</span>
                <strong className={workerAcceptanceResult?.accepted ? "approval-state-ok" : "approval-state-warn"}>
                  {workerAcceptanceResult ? (workerAcceptanceResult.accepted ? "通过" : "未完成") : "待刷新"}
                </strong>
              </div>
              <div className={`approval-gate-status ${workerAcceptanceResult?.accepted ? "ok" : "warn"}`}>
                {workerAcceptanceResult
                  ? workerAcceptanceResult.summary
                  : "等待用户在真实测试中转 VPS 手动执行安装命令，然后刷新 Worker 验收状态。"}
              </div>
              {workerAcceptanceResult ? <p className="message">下一步：{workerAcceptanceResult.next_action}</p> : null}
              {workerAcceptanceResult ? (
                <div className="worker-acceptance-checks">
                  {workerAcceptanceResult.checks.map((check) => (
                    <div className="worker-acceptance-check-row" key={check.id}>
                      <span className={check.passed ? "approval-state-ok" : "approval-state-warn"}>
                        {check.passed ? "通过" : "待处理"}
                      </span>
                      <strong>{check.label}</strong>
                      <small>{check.detail}</small>
                    </div>
                  ))}
                </div>
              ) : null}
              <ul className="dry-run-safety-list">
                <li>本按钮不会 SSH。</li>
                <li>本按钮不会安装 Worker。</li>
                <li>本按钮不会创建 Worker command。</li>
                <li>本按钮不会创建 HAProxy route。</li>
                <li>本按钮不会修改防火墙。</li>
              </ul>
              <div className="dry-run-actions">
                <button
                  className="secondary"
                  type="button"
                  disabled={workerAcceptanceLoading}
                  onClick={() => void refreshWorkerAcceptance(approvalPreviewResource)}
                >
                  {workerAcceptanceLoading ? "刷新中..." : "刷新 Worker 验收状态"}
                </button>
              </div>
              {workerAcceptanceResult?.accepted ? (
                <p className="approval-copy-status">Worker 手动安装验收通过：role / binding / version / heartbeat 均满足要求。</p>
              ) : null}
            </div>
            <div className="transit-worker-approval-section worker-acceptance-panel">
              <strong>Stage 3.3.137-hotfix-3：Transit Worker 升级验收</strong>
              <span>
                HAProxy TCP dry-run 需要 transit Worker 升级到要求版本。这里仅读取当前 Worker 版本和 heartbeat，不生成 token、不生成安装命令、不创建
                Worker command，也不执行远程升级。
              </span>
              <div className="worker-install-real-approval-grid">
                <span>资源</span>
                <strong>{approvalPreviewResource.name}</strong>
                <span>当前 Worker 状态</span>
                <strong className={workerUpgradeAcceptanceResult?.heartbeat_ok ? "approval-state-ok" : "approval-state-warn"}>
                  {workerUpgradeAcceptanceResult ? displayStatusLabel(workerUpgradeAcceptanceResult.worker_status ?? "unknown") : "待刷新"}
                </strong>
                <span>当前 Worker version</span>
                <strong className={workerUpgradeAcceptanceResult?.version_ok ? "approval-state-ok" : "approval-state-warn"}>
                  {workerUpgradeAcceptanceResult?.current_worker_version || "待刷新"}
                </strong>
                <span>要求 Worker version</span>
                <strong>{workerUpgradeAcceptanceResult?.required_worker_version || requiredTransitWorkerVersion}</strong>
                <span>bundled binary checksum</span>
                <strong>{workerUpgradeAcceptanceResult?.required_worker_checksum || transitWorkerBinaryChecksum}</strong>
                <span>是否需要升级</span>
                <strong className={workerUpgradeAcceptanceResult?.upgrade_required ? "approval-state-warn" : "approval-state-ok"}>
                  {workerUpgradeAcceptanceResult ? (workerUpgradeAcceptanceResult.upgrade_required ? "需要升级" : "不需要") : "待刷新"}
                </strong>
                <span>验收状态</span>
                <strong className={workerUpgradeAcceptanceResult?.acceptance_passed ? "approval-state-ok" : "approval-state-warn"}>
                  {workerUpgradeAcceptanceResult ? (workerUpgradeAcceptanceResult.acceptance_passed ? "通过" : "阻塞") : "待刷新"}
                </strong>
              </div>
              <div className={`approval-gate-status ${workerUpgradeAcceptanceResult?.acceptance_passed ? "ok" : "warn"}`}>
                {workerUpgradeAcceptanceResult
                  ? workerUpgradeAcceptanceResult.summary
                  : "请刷新 Transit Worker 升级验收。未满足最低版本前，不要重新生成 Stage 3.3.137 HAProxy route dry-run。"}
              </div>
              {workerUpgradeAcceptanceResult?.blocked_reason ? (
                <p className="message">阻塞原因：{workerUpgradeAcceptanceResult.blocked_reason}</p>
              ) : null}
              {workerUpgradeAcceptanceResult ? <p className="message">下一步：{workerUpgradeAcceptanceResult.next_action}</p> : null}
              {workerUpgradeAcceptanceResult ? (
                <div className="worker-acceptance-checks">
                  {workerUpgradeAcceptanceResult.checks.map((check) => (
                    <div className="worker-acceptance-check-row" key={check.id}>
                      <span className={check.passed ? "approval-state-ok" : "approval-state-warn"}>
                        {check.passed ? "通过" : "待处理"}
                      </span>
                      <strong>{check.label}</strong>
                      <small>{check.detail}</small>
                    </div>
                  ))}
                </div>
              ) : null}
              <ul className="dry-run-safety-list">
                <li>本验收不会生成 Worker token 或 install command。</li>
                <li>本验收不会 SSH、不会安装或重启远端 Worker。</li>
                <li>本验收不会创建 Worker command 或真实 execution command。</li>
                <li>本验收不会创建 HAProxy route、TransitRoute active record 或绑定 23843。</li>
                <li>本验收不会读取 / 写入 share_link，也不会 cutover。</li>
              </ul>
              <div className="transit-worker-approval-section">
                <strong>Stage 3.3.137-hotfix-4：手动升级 runbook</strong>
                <span>
                  这是手动升级 Worker 的准备阶段。系统不会远程执行任何命令；升级需要用户在 transit VPS 上手动完成。
                  升级完成后刷新验收，看到 Worker version 满足要求后，才能重新执行 Stage 3.3.137 dry-run。
                </span>
                <div className="worker-install-real-approval-grid">
                  <span>目标资源</span>
                  <strong>{approvalPreviewResource.name}</strong>
                  <span>当前 Worker version</span>
                  <strong>{workerUpgradeAcceptanceResult?.current_worker_version || approvalPreviewResource.worker_version || "待刷新"}</strong>
                  <span>目标 Worker version</span>
                  <strong>{workerUpgradeAcceptanceResult?.required_worker_version || requiredTransitWorkerVersion}</strong>
                  <span>bundled binary checksum</span>
                  <strong>{workerUpgradeAcceptanceResult?.required_worker_checksum || transitWorkerBinaryChecksum}</strong>
                </div>
                <ol className="dry-run-safety-list">
                  <li>在公网主控确认 bundled Worker binary 已是目标版本，并记录 checksum。</li>
                  <li>由用户自行登录 transit VPS，先备份旧的 liveline-worker binary。</li>
                  <li>由用户手动把目标版本 binary 放到 `/usr/local/bin/liveline-worker`，并保留可执行权限。</li>
                  <li>由用户手动重启远端 `liveline-worker.service`，等待 heartbeat 回到 online。</li>
                  <li>回到本页面点击“刷新 Worker 升级验收”，确认版本满足要求。</li>
                  <li>验收通过后，再回到 Stage 3.3.137 重新生成 HAProxy route dry-run。</li>
                </ol>
                <ul className="dry-run-safety-list">
                  <li>本 runbook 不生成 Worker token。</li>
                  <li>本 runbook 不生成完整 install command。</li>
                  <li>本 runbook 不自动安装或重启远端 Worker。</li>
                  <li>本 runbook 不创建 Worker command、HAProxy route 或 TransitRoute active record。</li>
                </ul>
                <details className="node-create-safety-details">
                  <summary>Stage 3.3.137-hotfix-5：手动升级命令审核</summary>
                  <div className="worker-install-dry-run">
                    <strong>A. 公网主控 VPS 执行：确认 bundled binary</strong>
                    <span>以下是只读核对命令，用于确认公网主控仓库内 binary 版本和 checksum；不生成 token，不连接 transit VPS。</span>
                    <pre className="worker-install-placeholder-command">{`cd /opt/liveline-console
sha256sum backend/worker-binaries/liveline-worker-linux-amd64
chmod +x backend/worker-binaries/liveline-worker-linux-amd64
./backend/worker-binaries/liveline-worker-linux-amd64 version`}</pre>
                    <strong>B. transit VPS 手动执行：替换本地 Worker binary</strong>
                    <span>
                      这是用户手动执行模板，不是系统生成的 SSH 命令。`/tmp/liveline-worker-linux-amd64`
                      只是用户手动上传到 transit VPS 后的临时路径，LiveLine Console 不上传文件、不远程执行。
                    </span>
                    <pre className="worker-install-placeholder-command">{`sudo systemctl stop liveline-worker.service
sudo cp /usr/local/bin/liveline-worker /usr/local/bin/liveline-worker.bak.$(date +%Y%m%d%H%M%S)
sudo install -m 0755 /tmp/liveline-worker-linux-amd64 /usr/local/bin/liveline-worker
/usr/local/bin/liveline-worker version
sudo systemctl start liveline-worker.service
sudo systemctl status liveline-worker.service --no-pager -l`}</pre>
                    <strong>C. 升级后验收：只查 Worker 状态</strong>
                    <span>优先在页面点击“刷新 Worker 升级验收”。如需数据库只读核对，只查询 Worker 版本和 heartbeat，不查询 token、secret 或 share_link。</span>
                    <pre className="worker-install-placeholder-command">{`cd /opt/liveline-console
docker compose exec -T postgres psql -U livelines -d livelines -c "
SELECT id, role, status, server_id, hostname, interface_name, worker_version, last_heartbeat_at
FROM workers
WHERE server_id = '80ec346d-3ac1-402e-ab09-33cb404ca81c'
ORDER BY last_heartbeat_at DESC NULLS LAST, created_at DESC
LIMIT 5;
"`}</pre>
                    <ul className="dry-run-safety-list">
                      <li>验收通过条件：role=transit，heartbeat online，interface_name=eth0。</li>
                      <li>server_id 必须是 80ec346d-3ac1-402e-ab09-33cb404ca81c。</li>
                      <li>worker_version 必须满足 {requiredTransitWorkerVersion} 或更高。</li>
                      <li>通过后才能回到 Stage 3.3.137 重新生成 HAProxy route dry-run。</li>
                    </ul>
                  </div>
                </details>
              </div>
              <div className="dry-run-actions">
                <button
                  className="secondary"
                  type="button"
                  disabled={workerUpgradeAcceptanceLoading}
                  onClick={() => void refreshWorkerUpgradeAcceptance(approvalPreviewResource)}
                >
                  {workerUpgradeAcceptanceLoading ? "刷新中..." : "刷新 Worker 升级验收"}
                </button>
              </div>
            </div>
            <div className="transit-worker-approval-section">
              <strong>占位安装命令模板</strong>
              <span>这不是本阶段可执行命令；`worker-token` 是后续独立阶段生成的占位符。</span>
              <pre className="worker-install-placeholder-command">{transitWorkerInstallPlaceholderCommand()}</pre>
            </div>
            <div className="transit-worker-approval-section">
              <strong>Go / No-Go 检查</strong>
              <ul>
                <li>公网主控 backend health 返回 200。</li>
                <li>Worker binary 本地 / 公网文件 checksum 一致。</li>
                <li>新 VPS 可以访问公网主控 URL。</li>
                <li>新 VPS 具备 root 或 sudo、systemd、curl。</li>
                <li>安装命令必须使用公网主控 URL，不能使用 localhost 或 127.0.0.1。</li>
                <li>不要把 SSH 私钥、密码、Worker token 或 secret 写入 notes、README、PR 或聊天。</li>
              </ul>
            </div>
            <div className="transit-worker-approval-section command-generation-gate">
              <strong>生成命令前审批门</strong>
              <span>
                这里展示生成一次性 Worker token / install command 前需要确认的条件。仅输入确认不会生成；只有点击生成按钮才会调用受保护 API。
              </span>
              <div className="transit-worker-approval-requirements" aria-label="生成命令前审批要求">
                <span>资源状态必须是 pending_worker</span>
                <strong className={approvalPreviewResource.status === "pending_worker" ? "approval-state-ok" : "approval-state-warn"}>
                  {approvalPreviewResource.status === "pending_worker" ? "满足" : "需调整"}
                </strong>
                <span>资源必须有 entry_host</span>
                <strong className={approvalPreviewResource.entry_host ? "approval-state-ok" : "approval-state-warn"}>
                  {approvalPreviewResource.entry_host ? approvalPreviewResource.entry_host : "待补充"}
                </strong>
                <span>SSH host / port / username</span>
                <strong className={approvalPreviewResource.has_ssh ? "approval-state-ok" : "approval-state-warn"}>
                  {approvalPreviewResource.has_ssh ? sshSummaryForResource(approvalPreviewResource) : "待补充或后续确认"}
                </strong>
                <span>真实命令使用公网主控 URL</span>
                <strong className="approval-state-ok">{transitWorkerPublicControllerUrl}</strong>
                <span>一次性 Worker token 生成时机</span>
                <strong className="approval-state-warn">仅后续独立审批阶段</strong>
              </div>
              <label className="command-approval-confirm">
                <span>模拟 typed confirmation。本阶段输入后也不会生成 token 或真实命令。</span>
                <input
                  value={commandApprovalConfirmText}
                  onChange={(event) => {
                    setCommandApprovalConfirmText(event.target.value);
                    setCommandApprovalCopied(false);
                    setCommandDryRunCopied(false);
                    setPlaceholderCommandCopied(false);
                    setRealCommandApprovalConfirmText("");
                    setRealCommandApprovalCopied(false);
                    setWorkerInstallCommandResult(null);
                    setWorkerInstallCommandCopied(false);
                  }}
                  placeholder={transitWorkerInstallCommandApprovalConfirmText}
                />
              </label>
              <div className={`approval-gate-status ${commandApprovalConfirmed ? "ok" : "warn"}`}>
                {commandApprovalConfirmed
                  ? "审批门 UI 已确认；仍需最终确认并点击生成按钮才会生成命令。"
                  : `请输入 ${transitWorkerInstallCommandApprovalConfirmText} 以模拟后续审批确认。`}
              </div>
              <button
                className="secondary"
                type="button"
                onClick={() => void copyWorkerCommandGenerationApprovalPackage(approvalPreviewResource)}
              >
                复制生成命令审批包
              </button>
              {commandApprovalCopied ? <p className="approval-copy-status">生成命令审批包已复制，只包含占位 token。</p> : null}
              {commandApprovalConfirmed ? (
                <div className="worker-install-dry-run" aria-label="生成命令 dry-run 结果">
                  <strong>生成命令 dry-run 结果</strong>
                  <ul className="dry-run-safety-list">
                    <li>这是 dry-run，不会生成 Worker token。</li>
                    <li>这是 dry-run，不会生成真实 install command。</li>
                    <li>这是 dry-run，不会安装 Worker。</li>
                    <li>这是 dry-run，不会创建 Worker command。</li>
                    <li>这是 dry-run，不会 SSH / 远程执行。</li>
                  </ul>
                  <div className="worker-install-dry-run-grid">
                    {transitWorkerInstallDryRunRows(approvalPreviewResource).map(([label, value]) => (
                      <Fragment key={label}>
                        <span>{label}</span>
                        <strong>{value}</strong>
                      </Fragment>
                    ))}
                  </div>
                  <div className="worker-install-dry-run-checks">
                    {transitWorkerInstallDryRunChecks(approvalPreviewResource, commandApprovalConfirmed).map(([label, value, passed]) => (
                      <Fragment key={label}>
                        <span>{label}</span>
                        <strong className={passed ? "approval-state-ok" : "approval-state-warn"}>{value}</strong>
                      </Fragment>
                    ))}
                  </div>
                  <div className="transit-worker-approval-section dry-run-command-template">
                    <strong>占位命令模板</strong>
                    <span>
                      这不是可执行真实安装命令。<code>{transitWorkerPlaceholderToken}</code> 仍是占位符。
                    </span>
                    <pre className="worker-install-placeholder-command">{transitWorkerInstallPlaceholderCommand()}</pre>
                  </div>
                  <div className="dry-run-actions">
                    <button className="secondary" type="button" onClick={() => void copyWorkerInstallDryRunResult(approvalPreviewResource)}>
                      复制 dry-run 结果
                    </button>
                    <button className="secondary" type="button" onClick={() => void copyWorkerInstallPlaceholderCommand()}>
                      复制占位命令模板
                    </button>
                  </div>
                  {commandDryRunCopied ? <p className="approval-copy-status">dry-run 结果已复制；不包含真实 token。</p> : null}
                  {placeholderCommandCopied ? <p className="approval-copy-status">占位命令模板已复制；仍不可直接执行。</p> : null}
                </div>
              ) : null}
              {commandApprovalConfirmed && approvalPreviewResource.status === "pending_worker" ? (
                <div className="worker-install-real-approval" aria-label="真实生成命令最终审批">
                  <strong>真实生成命令最终审批</strong>
                  <span>
                    这里仅确认下一阶段生成一次性 Worker token / install command 前的真实 VPS 条件。本阶段输入确认后仍不会生成
                    token，不会生成真实 install command，不会创建 Worker command，也不会 SSH 或远程执行。
                  </span>
                  <div className="worker-install-real-approval-grid">
                    {transitWorkerRealCommandApprovalRows(approvalPreviewResource).map(([label, value]) => (
                      <Fragment key={label}>
                        <span>{label}</span>
                        <strong>{value}</strong>
                      </Fragment>
                    ))}
                  </div>
                  <div className="worker-install-real-approval-checks">
                    {transitWorkerRealCommandReadinessChecks(approvalPreviewResource).map(([label, value]) => (
                      <Fragment key={label}>
                        <span>{label}</span>
                        <strong>{value}</strong>
                      </Fragment>
                    ))}
                  </div>
                  <label className="command-approval-confirm">
                    <span>最终 typed confirmation。输入后不会自动生成命令，只有点击生成按钮才会调用受保护 API。</span>
                    <input
                      value={realCommandApprovalConfirmText}
                      onChange={(event) => {
                        setRealCommandApprovalConfirmText(event.target.value);
                        setRealCommandApprovalCopied(false);
                        setWorkerInstallCommandResult(null);
                        setWorkerInstallCommandCopied(false);
                      }}
                      placeholder={transitWorkerRealCommandApprovalConfirmText}
                    />
                  </label>
                  <div className={`approval-gate-status ${realCommandApprovalConfirmed ? "ok" : "warn"}`}>
                    {realCommandApprovalConfirmed
                      ? "最终审批门已通过。点击生成按钮才会生成一次性 Worker token / install command。"
                      : "尚未确认进入真实命令生成阶段。"}
                  </div>
                  <ul className="dry-run-safety-list">
                    <li>仅输入最终确认不会生成 Worker token。</li>
                    <li>点击生成按钮后，只生成一次性 token / install command。</li>
                    <li>本阶段不会安装 Worker。</li>
                    <li>本阶段不会 SSH 或远程执行。</li>
                  </ul>
                  <div className="dry-run-actions">
                    <button className="secondary" type="button" onClick={() => void copyWorkerRealCommandApprovalPackage(approvalPreviewResource)}>
                      复制真实生成命令最终审批包
                    </button>
                    <button
                      type="button"
                      disabled={!realCommandApprovalConfirmed || workerInstallCommandGenerating}
                      onClick={() => void submitWorkerInstallCommandGeneration(approvalPreviewResource)}
                    >
                      {workerInstallCommandGenerating ? "生成中..." : "生成一次性 Worker 安装命令"}
                    </button>
                  </div>
                  <p className="message">只生成命令，不安装 Worker，不 SSH，不创建 Worker command。</p>
                  {realCommandApprovalCopied ? (
                    <p className="approval-copy-status">真实生成命令最终审批包已复制；不包含真实 token 或真实安装命令。</p>
                  ) : null}
                  {workerInstallCommandResult ? (
                    <div className="worker-install-command-result" aria-label="一次性 Worker 安装命令已生成">
                      <strong>一次性 Worker 安装命令已生成</strong>
                      <div className="worker-install-real-approval-grid">
                        <span>资源名</span>
                        <strong>{workerInstallCommandResult.resource.name}</strong>
                        <span>资源状态</span>
                        <strong>{workerInstallCommandResult.resource.status}</strong>
                        <span>controller_url</span>
                        <strong>{workerInstallCommandResult.controller_url}</strong>
                        <span>role</span>
                        <strong>{workerInstallCommandResult.role}</strong>
                        <span>token 过期时间</span>
                        <strong>{formatTime(workerInstallCommandResult.expires_at)}</strong>
                      </div>
                      <div className="approval-gate-status warn">
                        该命令包含一次性 token，只显示一次。不要保存到 README / docs / PR / chat / logs。不要在未确认真实 VPS 前执行。
                        下一阶段才进行手动安装验收。
                      </div>
                      <pre className="worker-install-placeholder-command">{workerInstallCommandResult.install_command}</pre>
                      <div className="dry-run-actions">
                        <button className="secondary" type="button" onClick={() => void copyGeneratedWorkerInstallCommand()}>
                          复制安装命令
                        </button>
                      </div>
                      {workerInstallCommandCopied ? (
                        <p className="approval-copy-status">安装命令已复制；请只在真实测试 VPS 的手动安装阶段使用。</p>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
            <div className="transit-worker-approval-section">
              <strong>Stage 3.3.134 执行边界确认</strong>
              <ul>
                <li>我确认本阶段只生成一次性 Worker token / install command。</li>
                <li>我确认本阶段不自动安装 Worker。</li>
                <li>我确认本阶段不执行 SSH / 远程命令。</li>
                <li>我确认本阶段不创建 Worker command。</li>
                <li>我确认本阶段不创建 HAProxy route。</li>
                <li>我确认生成的命令只在当前页面复制使用，不写入 README / docs / PR / chat / logs / notes。</li>
                <li>真实 Worker 安装与心跳验收必须在后续独立阶段执行。</li>
              </ul>
            </div>
            <div className="modal-actions">
              <button className="secondary" type="button" onClick={closeApprovalPreview}>
                关闭预览
              </button>
              <button type="button" onClick={() => void copyWorkerInstallApprovalChecklist(approvalPreviewResource)}>
                复制审批清单
              </button>
            </div>
            {approvalPreviewCopied ? <p className="approval-copy-status">审批清单已复制，不包含真实 token 或密钥。</p> : null}
          </div>
        </div>
      ) : null}

      {modalMode && modalMode !== "delete" ? (
        <div className="modal-backdrop" role="presentation">
          <div className="modal-card transit-resource-draft-modal" role="dialog" aria-modal="true" aria-label="中转服务器操作">
            <div className="modal-header">
              <h3>{modalMode === "edit" ? "编辑中转服务器记录" : "新增中转 VPS 草稿"}</h3>
              <button className="ghost-button" type="button" onClick={closeModal}>
                取消
              </button>
            </div>
            <form
              className="form server-modal-form transit-resource-draft-form"
              onSubmit={(event) => void (modalMode === "edit" ? submitEdit(event) : submitDraftResource(event))}
            >
              <div className="worker-bootstrap-intro wide-field">
                <strong>{modalMode === "edit" ? "只更新本地资源记录" : "草稿资源 / 等待安装 Worker"}</strong>
                <span>
                  本阶段只保存中转 VPS 草稿信息，状态为 pending_worker。不会生成 Worker token、不会生成安装命令、不会 SSH、不会创建 Worker command 或 HAProxy route。
                </span>
              </div>
              <label>
                资源名称
                <input
                  placeholder="例如 hk-haproxy-vps-draft"
                  value={draftForm.name}
                  onChange={(event) => setDraftForm({ ...draftForm, name: event.target.value })}
                />
              </label>
              <label>
                云厂商 / provider
                <input
                  placeholder="例如 Bandwagon / Vultr / unknown"
                  value={draftForm.provider}
                  onChange={(event) => setDraftForm({ ...draftForm, provider: event.target.value })}
                />
              </label>
              <label>
                公网 IP / 域名
                <input
                  placeholder="可先留空，或填写后续准备接入的入口地址"
                  value={draftForm.entryHost}
                  onChange={(event) => setDraftForm({ ...draftForm, entryHost: event.target.value })}
                />
              </label>
              <label>
                入口地区
                <input
                  placeholder="例如 Hong Kong"
                  value={draftForm.entryRegion}
                  onChange={(event) => setDraftForm({ ...draftForm, entryRegion: event.target.value })}
                />
              </label>
              <label>
                出口地区
                <input
                  placeholder="例如 landing region / US"
                  value={draftForm.exitRegion}
                  onChange={(event) => setDraftForm({ ...draftForm, exitRegion: event.target.value })}
                />
              </label>
              <label>
                带宽 Mbps
                <input
                  inputMode="numeric"
                  placeholder="可选"
                  value={draftForm.bandwidthMbps}
                  onChange={(event) => setDraftForm({ ...draftForm, bandwidthMbps: event.target.value })}
                />
              </label>
              <label>
                流量限制 GB
                <input
                  inputMode="decimal"
                  placeholder="可选"
                  value={draftForm.trafficLimitGb}
                  onChange={(event) => setDraftForm({ ...draftForm, trafficLimitGb: event.target.value })}
                />
              </label>
              <label>
                计划网卡名
                <input
                  placeholder="例如 eth0 / ens3"
                  value={draftForm.plannedInterface}
                  onChange={(event) => setDraftForm({ ...draftForm, plannedInterface: event.target.value })}
                />
              </label>
              <label>
                协议提示
                <select
                  value={draftForm.protocolHint}
                  onChange={(event) =>
                    setDraftForm({ ...draftForm, protocolHint: event.target.value as TransitResourceDraftFormState["protocolHint"] })
                  }
                >
                  <option value="haproxy_tcp">HAProxy TCP</option>
                  <option value="socat">socat</option>
                  <option value="unknown">待确认</option>
                </select>
              </label>
              <label className="transit-draft-checkbox wide-field">
                <input
                  checked={draftForm.hasSsh}
                  type="checkbox"
                  onChange={(event) => setDraftForm({ ...draftForm, hasSsh: event.target.checked })}
                />
                <span>记录 SSH 管理元信息。只保存 host/port/username，不保存密码、私钥或 token。</span>
              </label>
              {draftForm.hasSsh ? (
                <>
                  <label>
                    SSH host
                    <input
                      value={draftForm.sshHost}
                      onChange={(event) => setDraftForm({ ...draftForm, sshHost: event.target.value })}
                    />
                  </label>
                  <label>
                    SSH port
                    <input
                      inputMode="numeric"
                      value={draftForm.sshPort}
                      onChange={(event) => setDraftForm({ ...draftForm, sshPort: event.target.value })}
                    />
                  </label>
                  <label>
                    SSH username
                    <input
                      value={draftForm.sshUsername}
                      onChange={(event) => setDraftForm({ ...draftForm, sshUsername: event.target.value })}
                    />
                  </label>
                </>
              ) : null}
              <label className="wide-field">
                备注
                <textarea
                  placeholder="不要填写密码、私钥、Worker token、后台账号或其他敏感信息。"
                  value={draftForm.notes}
                  onChange={(event) => setDraftForm({ ...draftForm, notes: event.target.value })}
                />
              </label>
              <div className="transit-draft-readiness wide-field">
                <strong>后续 HAProxy TCP readiness</strong>
                <span>Worker 版本要求：{requiredTransitWorkerVersion}</span>
                <span>Worker binary checksum：{transitWorkerBinaryChecksum}</span>
                <ul>
                  <li>新 transit Worker online 后，才允许进入 HAProxy TCP route 创建审批。</li>
                  <li>后续需要确认 HAProxy 已安装、计划监听端口未占用、到落地目标端口 TCP 可达。</li>
                  <li>云安全组、云防火墙、服务器本机防火墙必须由用户自行放行监听 TCP 端口。</li>
                  <li>本页面不会安装 HAProxy，不会修改防火墙，不会创建 route。</li>
                </ul>
              </div>
              <div className="modal-actions wide-field">
                <button disabled={submitting} type="submit">
                  {modalMode === "edit" ? "保存本地记录" : "保存为待安装 Worker"}
                </button>
                <button className="secondary" type="button" onClick={closeModal}>
                  取消
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export function TransitRoutesPanel() {
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [routes, setRoutes] = useState<TransitRouteData[]>([]);
  const [draft, setDraft] = useState<TransitRouteDraftState>(emptyRouteDraft);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("中转链路页面只做 Worker 规划、只读预检和受控 dry-run；不会创建真实转发。");
  const [readonlyPlan, setReadonlyPlan] = useState<ReadonlyPreflightPlanResponse | null>(null);
  const [readonlyPreflightLoading, setReadonlyPreflightLoading] = useState(false);
  const [remotePreflightLoading, setRemotePreflightLoading] = useState(false);
  const [remotePreflightCommand, setRemotePreflightCommand] = useState<WorkerCommandData | null>(null);
  const [readonlyPreflightApiMessage, setReadonlyPreflightApiMessage] = useState("");
  const [remotePreflightMessage, setRemotePreflightMessage] = useState("");
  const [haproxyReadiness, setHaproxyReadiness] = useState<TransitHaproxyReadinessApprovalResult | null>(null);
  const [haproxyReadinessLoading, setHaproxyReadinessLoading] = useState(false);
  const [haproxyReadinessMessage, setHaproxyReadinessMessage] = useState("HAProxy TCP readiness 尚未生成。");
  const [haproxyReadinessConfirmations, setHaproxyReadinessConfirmations] = useState<HaproxyReadinessConfirmations>(
    emptyHaproxyReadinessConfirmations,
  );
  const [haproxyDryRun, setHaproxyDryRun] = useState<TransitHaproxyRouteCreateDryRunResult | null>(null);
  const [haproxyDryRunLoading, setHaproxyDryRunLoading] = useState(false);
  const [haproxyDryRunMessage, setHaproxyDryRunMessage] = useState("HAProxy route dry-run 尚未生成。");
  const [haproxyFinalApproval, setHaproxyFinalApproval] = useState<TransitHaproxyRouteCreateFinalApprovalResult | null>(null);
  const [haproxyFinalApprovalLoading, setHaproxyFinalApprovalLoading] = useState(false);
  const [haproxyFinalApprovalMessage, setHaproxyFinalApprovalMessage] = useState("HAProxy route 最终审批包尚未生成。");
  const [haproxyFinalApprovalText, setHaproxyFinalApprovalText] = useState("");
  const [haproxyRealExecution, setHaproxyRealExecution] = useState<TransitHaproxyRouteCreateRealExecutionResult | null>(null);
  const [haproxyRealExecutionLoading, setHaproxyRealExecutionLoading] = useState(false);
  const [haproxyRealExecutionMessage, setHaproxyRealExecutionMessage] = useState("HAProxy route 真实创建尚未授权。");
  const [haproxyRealExecutionText, setHaproxyRealExecutionText] = useState("");
  const [healthConfirmed, setHealthConfirmed] = useState(false);
  const [boundaryConfirmed, setBoundaryConfirmed] = useState(false);
  const [workerBoundaryConfirmed, setWorkerBoundaryConfirmed] = useState(false);
  const [preflightSummaryCopied, setPreflightSummaryCopied] = useState(false);
  const [workerCreatePlan, setWorkerCreatePlan] = useState<TransitRouteWorkerCreatePlanResult | null>(null);
  const [workerCreateLoading, setWorkerCreateLoading] = useState(false);
  const [candidateSummary, setCandidateSummary] = useState<TransitRouteCandidateSummary | null>(null);
  const [candidateExport, setCandidateExport] = useState<TransitRouteCandidateExportResult | null>(null);
  const [candidateLoading, setCandidateLoading] = useState(false);
  const [candidateMessage, setCandidateMessage] = useState("候选链路摘要尚未加载；不会自动导出完整测试配置。");
  const [candidateCopyFallbackRequired, setCandidateCopyFallbackRequired] = useState(false);
  const [candidateExportModalOpen, setCandidateExportModalOpen] = useState(false);
  const [candidateExportRouteId, setCandidateExportRouteId] = useState("");
  const [deleteRouteId, setDeleteRouteId] = useState("");
  const [deleteRouteConfirmText, setDeleteRouteConfirmText] = useState("");
  const [deleteRouteMode, setDeleteRouteMode] = useState<DeleteFlowMode>("remote_cleanup");
  const [advancedTransitOpsOpen, setAdvancedTransitOpsOpen] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createForm, setCreateForm] = useState<TransitRouteCreateFormState>(emptyRouteCreateForm);
  const [createStep, setCreateStep] = useState<TransitRouteCreateStep>("idle");
  const [createCommand, setCreateCommand] = useState<WorkerCommandData | null>(null);
  const [createExecuteResult, setCreateExecuteResult] = useState<TransitRouteWorkerCreateExecuteResponse | null>(null);
  const [createdRoute, setCreatedRoute] = useState<TransitRouteData | null>(null);
  const [createExport, setCreateExport] = useState<TransitRouteCandidateExportResult | null>(null);
  const [createError, setCreateError] = useState("");
  const [createCopyFallbackRequired, setCreateCopyFallbackRequired] = useState(false);
  const [createQrVisible, setCreateQrVisible] = useState(false);
  const createQrFrameRef = useRef<HTMLDivElement | null>(null);
  const [candidateRouteId, setCandidateRouteId] = useState("");

  const selectableResources = useMemo(() => resources.filter(isPlanningSelectableTransitResource), [resources]);
  const activeNodes = useMemo(() => nodes.filter((node) => node.status === "active"), [nodes]);
  const primaryActiveRoute = useMemo(
    () => routes.find((route) => route.status === "active" && !route.deleted_at) ?? routes.find((route) => !route.deleted_at) ?? null,
    [routes],
  );
  const candidateExportRoute = routes.find((route) => route.id === candidateExportRouteId) ?? null;
  const deleteRoute = routes.find((route) => route.id === deleteRouteId) ?? null;
  const selectedResource = selectableResources.find((resource) => resource.id === draft.transitResourceId) ?? selectableResources[0] ?? null;
  const selectedNode = activeNodes.find((node) => node.id === draft.landingNodeId) ?? activeNodes[0] ?? null;
  const createResource = selectableResources.find((resource) => resource.id === createForm.transitResourceId) ?? selectableResources[0] ?? null;
  const createNode = activeNodes.find((node) => node.id === createForm.landingNodeId) ?? activeNodes[0] ?? null;
  const plannedPort = parsePort(draft.plannedListenPort);
  const targetPort = targetPortForNode(selectedNode);
  const createListenPort = parsePort(createForm.listenPort);
  const createTargetPort = targetPortForNode(createNode);
  const createPortConflictRoute = findTransitPortConflictRoute(routes, createResource?.id, createListenPort);
  const createPortConflictMessage =
    createListenPort !== null && createPortConflictRoute
      ? duplicateTransitPortMessage(createForm.forwardingMethod, createListenPort, createPortConflictRoute)
      : "";
  const createReady =
    Boolean(createForm.routeName.trim()) &&
    Boolean(createResource) &&
    Boolean(createNode) &&
    createListenPort !== null &&
    createTargetPort > 0 &&
    createForm.firewallConfirmed &&
    !createPortConflictRoute &&
    createStep !== "preflight_create" &&
    createStep !== "preflight_running" &&
    createStep !== "command_create" &&
    createStep !== "command_running" &&
    createStep !== "refresh" &&
    createStep !== "export_link";

  const planningIssues = [
    !selectedResource ? "暂无可用于本地规划的中转服务器。" : null,
    !selectedNode ? "暂无 active 落地节点。" : null,
    plannedPort === null ? "计划监听端口必须是 1-65535 之间的整数。" : null,
    targetPort <= 0 ? "目标节点缺少目标端口。" : null,
    !healthConfirmed ? "请确认本地 health 和任务队列状态。" : null,
    !boundaryConfirmed ? "请确认本阶段不创建真实转发、不修改 nodes.share_link、不 cutover。" : null,
    !workerBoundaryConfirmed ? "请确认只通过 Worker allowlist 执行固定只读检查。" : null,
  ].filter(Boolean) as string[];

  const preflightReady = planningIssues.length === 0 && Boolean(readonlyPlan?.ready);

  async function loadData() {
    setLoading(true);
    let nextResources: TransitResourceData[] = resources;
    let nextNodes: NodeData[] = nodes;
    let nextRoutes: TransitRouteData[] = routes;
    const [resourceResult, nodeResult, routeResult] = await Promise.all([
      apiFetch<TransitResourceListResult>("/api/transit-resources?resource_type=server"),
      apiFetch<NodeListResult>("/api/nodes"),
      apiFetch<TransitRouteListResult>("/api/transit-routes"),
    ]);

    if (resourceResult.success) {
      nextResources = resourceResult.data.resources;
      setResources(nextResources);
    } else {
      setMessage(`${resourceResult.error_code}: ${resourceResult.message}`);
    }
    if (nodeResult.success) {
      nextNodes = nodeResult.data.nodes;
      setNodes(nextNodes);
    } else {
      setMessage(`${nodeResult.error_code}: ${nodeResult.message}`);
    }
    if (routeResult.success) {
      nextRoutes = routeResult.data.routes;
      setRoutes(nextRoutes);
    } else {
      setMessage(`${routeResult.error_code}: ${routeResult.message}`);
    }
    setLoading(false);
    return { resources: nextResources, nodes: nextNodes, routes: nextRoutes };
  }

  function scheduleRouteDataRefresh() {
    [1500, 4000].forEach((delay) => {
      window.setTimeout(() => {
        void loadData();
      }, delay);
    });
  }

  async function refreshWhenRouteCleanupCommandCompletes(command?: WorkerCommandData | null) {
    if (!command?.id) {
      return;
    }

    let latestCommand: WorkerCommandData | null = command;

    for (let attempt = 0; attempt < cleanupCommandMaxPolls; attempt += 1) {
      await sleep(cleanupCommandPollIntervalMs);
      const result = await getWorkerCommand(command.id);
      if (result.success) {
        latestCommand = result.data;
        if (cleanupCommandTerminalStatuses.has(result.data.status)) {
          await loadData();
          setMessage(
            result.data.status === "succeeded"
              ? "清理任务已完成，中转链路列表已自动刷新。"
              : `清理任务已进入终态：${displayStatusLabel(result.data.status)}。列表已自动刷新，请查看任务中心。`,
          );
          return;
        }
      }
    }

    await loadData();
    setMessage(
      latestCommand
        ? "清理任务仍在执行，中转链路列表已再次刷新；请稍后查看任务中心或再次刷新。"
        : "清理任务状态暂不可读，中转链路列表已再次刷新；请稍后查看任务中心。",
    );
  }

  useEffect(() => {
    void loadData();
  }, []);

  function routeTransitResource(route: TransitRouteData) {
    return resources.find((resource) => resource.id === route.transit_resource_id) ?? null;
  }

  function routeEntry(route: TransitRouteData) {
    const resource = routeTransitResource(route);
    const host = resource?.entry_host ?? route.transit_resource_name ?? route.transit_resource_id;
    return `${displayValue(host)}:${route.listen_port}`;
  }

  function routeCutoverStatusLabel(routeId: string) {
    if (candidateSummary?.route_id === routeId && candidateSummary.cutover_status !== "not_cutover") {
      return candidateSummary.cutover_status;
    }
    return "未切换";
  }

  function routeHasShareLink(route: TransitRouteData) {
    return Boolean(route.share_link);
  }

  function openCreateRouteModal() {
    setCreateForm({
      ...emptyRouteCreateForm,
      transitResourceId: selectedResource?.id ?? selectableResources[0]?.id ?? "",
      landingNodeId: selectedNode?.id ?? activeNodes[0]?.id ?? "",
    });
    setCreateStep("idle");
    setCreateCommand(null);
    setCreateExecuteResult(null);
    setCreatedRoute(null);
    setCreateExport(null);
    setCreateError("");
    setCreateCopyFallbackRequired(false);
    setCreateQrVisible(false);
    setCreateModalOpen(true);
  }

  async function closeCreateRouteModal(refresh = false) {
    setCreateModalOpen(false);
    setCreateForm(emptyRouteCreateForm);
    setCreateStep("idle");
    setCreateCommand(null);
    setCreateExecuteResult(null);
    setCreatedRoute(null);
    setCreateExport(null);
    setCreateError("");
    setCreateCopyFallbackRequired(false);
    setCreateQrVisible(false);
    if (refresh) {
      await loadData();
    }
  }

  function formatApiError(result: {
    error_code?: string | null;
    message?: string | null;
    error?: string | null;
    detail?: unknown;
  }) {
    const code = result.error_code || "REQUEST_FAILED";
    let detailText = "";
    if (typeof result.detail === "string") {
      detailText = result.detail;
    } else if (Array.isArray(result.detail) && result.detail.length > 0) {
      detailText = "请求参数不正确。";
    }
    const message = result.message || result.error || detailText || "请求失败，请稍后重试。";
    return `${code}: ${message}`;
  }

  function isWorkerCommandNotFound(result: {
    error_code?: string | null;
    message?: string | null;
    detail?: unknown;
  }) {
    const code = (result.error_code || "").toUpperCase();
    const message = `${result.message || ""} ${typeof result.detail === "string" ? result.detail : ""}`.toLowerCase();
    return (
      code === "WORKER_COMMAND_NOT_FOUND" ||
      code === "COMMAND_NOT_FOUND" ||
      code === "NOT_FOUND" ||
      message.includes("not found") ||
      message.includes("不存在")
    );
  }

  async function waitForTransitCommandCompletion(commandId: string, runningStep: TransitRouteCreateStep) {
    const notFoundRetryStartedAt = Date.now();
    for (let attempt = 0; attempt < 90; attempt += 1) {
      const result = await getWorkerCommand(commandId);
      if (!result.success) {
        if (isWorkerCommandNotFound(result) && Date.now() - notFoundRetryStartedAt < workerCommandNotFoundRetryMs) {
          setCreateStep(runningStep);
          await sleep(2000);
          continue;
        }
        if (isWorkerCommandNotFound(result)) {
          throw new Error(
            "WORKER_COMMAND_STATUS_UNAVAILABLE: Worker 命令状态暂不可读，请刷新后检查任务中心。",
          );
        }
        throw new Error(formatApiError(result));
      }
      setCreateCommand(result.data);
      if (transitCreateTerminalStatuses.has(result.data.status)) {
        return result.data;
      }
      setCreateStep(runningStep);
      await sleep(2000);
    }
    throw new Error("Worker 命令等待超时。请刷新列表查看最新状态。");
  }

  function findCreatedTransitRoute(routeList: TransitRouteData[]) {
    if (!createResource || !createNode || createListenPort === null) {
      return null;
    }
    return (
      routeList.find(
        (route) =>
          route.transit_resource_id === createResource.id &&
          route.node_id === createNode.id &&
          route.listen_port === createListenPort &&
          route.target_port === createTargetPort &&
          route.forwarding_method === createForm.forwardingMethod &&
          route.status === "active" &&
          !route.deleted_at,
      ) ?? null
    );
  }

  function friendlyTransitCreateError(error: unknown) {
    const raw = error instanceof Error ? error.message : String(error || "创建失败。");
    if (
      raw.includes("WORKER_COMMAND_STATUS_UNAVAILABLE") ||
      raw.includes("WORKER_COMMAND_NOT_FOUND") ||
      raw.includes("COMMAND_NOT_FOUND") ||
      raw.includes("NOT_FOUND") ||
      raw.includes("暂不可读") ||
      raw.includes("404")
    ) {
      return "Worker 命令状态暂不可读：请稍候刷新任务状态，或重新打开弹窗查看是否已完成。";
    }
    if (raw.includes("TRANSIT_PREFLIGHT_REQUIRED") || raw.includes("TRANSIT_PREFLIGHT_TARGET_MISMATCH")) {
      return "只读预检不匹配：请先用当前中转服务器、落地节点、监听端口和目标端口重新完成只读预检。";
    }
    if (raw.includes("READONLY_PREFLIGHT") || raw.includes("preflight") || raw.includes("预检")) {
      return "只读预检未通过：请确认 Worker 在线、监听端口未占用、落地目标端口可达。";
    }
    if (raw.includes("TRANSIT_PORT_ALREADY_EXISTS") || raw.includes("TRANSIT_PORT_ALREADY_PLANNED") || raw.includes("LISTEN") || raw.includes("listen") || raw.includes("端口")) {
      return "中转监听端口不可用：端口可能已存在链路、未放行，或 Worker 未检测到监听成功。";
    }
    if (raw.includes("TRANSIT_WORKER_INTERFACE_MISMATCH")) {
      return "中转 Worker 网卡与最近成功只读预检不一致：请确认选择的是同一台在线中转服务器，并重新执行只读预检。";
    }
    if (raw.includes("TRANSIT_WORKER") || raw.includes("WORKER") || raw.includes("Worker")) {
      return "中转 Worker 不在线或版本不满足，请检查中转服务器 Worker 状态。";
    }
    if (raw.includes("APPROVAL") || raw.includes("MISMATCH") || raw.includes("审批")) {
      return "受保护创建审批未通过：请确认中转服务器、落地节点、端口、只读预检结果和 Worker 绑定关系一致。";
    }
    if (raw.includes("share_link") || raw.includes("链接")) {
      return "客户端链接生成失败：请确认落地直连节点已经成功生成分享链接。";
    }
    return raw;
  }

  async function submitSimplifiedTransitRouteCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!createResource || !createNode || createListenPort === null || createTargetPort <= 0) {
      setCreateError("请先选择中转服务器、落地节点，并填写合法的中转监听端口。");
      return;
    }
    if (!createForm.firewallConfirmed) {
      setCreateError("请先确认中转监听端口已在云安全组、云防火墙和服务器本机防火墙放行。");
      return;
    }
    const conflictRoute = findTransitPortConflictRoute(routes, createResource.id, createListenPort);
    if (conflictRoute) {
      setCreateError(duplicateTransitPortMessage(createForm.forwardingMethod, createListenPort, conflictRoute));
      setMessage("检测到同一中转服务器已有相同监听端口的 active/creating 链路，已阻止创建流程。");
      return;
    }

    const routeName = createForm.routeName.trim() || defaultTransitRouteName(createForm.forwardingMethod, createForm.listenPort);

    setCreateStep("preflight_create");
    setCreateCommand(null);
    setCreateExecuteResult(null);
    setCreatedRoute(null);
    setCreateExport(null);
    setCreateError("");
    setCreateCopyFallbackRequired(false);
    setCreateQrVisible(false);
    setMessage(
      createForm.forwardingMethod === "haproxy_tcp"
        ? "正在自动执行 HAProxy TCP 审批、dry-run、最终确认和受保护创建流程。"
        : "正在自动执行中转只读预检和受保护创建流程。成功后才会临时生成客户端链接和二维码。",
    );

    try {
      const csrfToken = await ensureCsrfToken();

      if (createForm.forwardingMethod === "haproxy_tcp") {
        const landingTargetHost = landingHostForNode(createNode);

        const readinessResult = await requestTransitHaproxyReadinessApproval({
          transit_resource_id: createResource.id,
          landing_node_id: createNode.id,
          planned_listen_port: createListenPort,
          landing_target_port: createTargetPort,
          forwarding_method: "haproxy_tcp",
          purpose: "直播",
          firewall_security_group_confirmed: createForm.firewallConfirmed,
          cloud_firewall_confirmed: createForm.firewallConfirmed,
          server_firewall_confirmed: createForm.firewallConfirmed,
          no_cutover_confirmed: true,
          no_node_share_link_change_confirmed: true,
          no_full_client_link_confirmed: true,
        });
        if (!readinessResult.success) {
          throw new Error(`${readinessResult.error_code}: ${readinessResult.message}`);
        }
        if (!readinessResult.data.ready || readinessResult.data.blocked) {
          throw new Error(readinessResult.data.summary || "HAProxy TCP 创建审批包未通过。");
        }

        setCreateStep("command_create");
        const dryRunResult = await createTransitHaproxyRouteDryRun(
          {
            transit_resource_id: createResource.id,
            landing_node_id: createNode.id,
            planned_listen_port: createListenPort,
            landing_target_host: landingTargetHost,
            landing_target_port: createTargetPort,
            forwarding_method: "haproxy_tcp",
            purpose: "直播",
            route_name: routeName,
            approval_stage: "Stage 3.3.137-new-transit-haproxy-route-create-dry-run",
            readiness_approval_confirmed: true,
            dry_run: true,
            approval_required: true,
            firewall_security_group_confirmed: createForm.firewallConfirmed,
            cloud_firewall_confirmed: createForm.firewallConfirmed,
            server_firewall_confirmed: createForm.firewallConfirmed,
            no_cutover_confirmed: true,
            no_node_share_link_change_confirmed: true,
            no_full_client_link_confirmed: true,
          },
          csrfToken,
        );
        if (!dryRunResult.success) {
          throw new Error(`${dryRunResult.error_code}: ${dryRunResult.message}`);
        }
        setCreateCommand(dryRunResult.data.command);
        const dryRunCommand = await waitForTransitCommandCompletion(dryRunResult.data.command.id, "command_running");
        if (dryRunCommand.status !== "succeeded") {
          throw new Error(dryRunCommand.error_message || "HAProxy TCP dry-run 未通过。");
        }

        const finalApprovalResult = await requestTransitHaproxyRouteFinalApproval(
          {
            dry_run_command_id: dryRunResult.data.command.id,
            transit_resource_id: createResource.id,
            landing_node_id: createNode.id,
            planned_listen_port: createListenPort,
            landing_target_host: landingTargetHost,
            landing_target_port: createTargetPort,
            forwarding_method: "haproxy_tcp",
            route_name: routeName,
            planned_service_name: dryRunResult.data.planned_service_name,
            approval_stage: "Stage 3.3.138-new-transit-haproxy-route-create-final-approval",
            dry_run_verified: true,
            firewall_security_group_confirmed: createForm.firewallConfirmed,
            cloud_firewall_confirmed: createForm.firewallConfirmed,
            server_firewall_confirmed: createForm.firewallConfirmed,
            no_cutover_confirmed: true,
            no_node_share_link_change_confirmed: true,
            no_full_client_link_confirmed: true,
            final_approval_text: HAPROXY_FINAL_APPROVAL_TEXT,
          },
          csrfToken,
        );
        if (!finalApprovalResult.success) {
          throw new Error(`${finalApprovalResult.error_code}: ${finalApprovalResult.message}`);
        }
        if (!finalApprovalResult.data.ready_for_real_create || finalApprovalResult.data.blocked) {
          throw new Error(finalApprovalResult.data.summary || "HAProxy TCP 最终审批未通过。");
        }

        const realExecutionResult = await createTransitHaproxyRouteRealExecution(
          {
            dry_run_command_id: dryRunResult.data.command.id,
            transit_resource_id: createResource.id,
            landing_node_id: createNode.id,
            planned_listen_port: createListenPort,
            landing_target_host: landingTargetHost,
            landing_target_port: createTargetPort,
            forwarding_method: "haproxy_tcp",
            route_name: routeName,
            approval_stage: "Stage 3.3.139-new-transit-haproxy-route-create-real-execution",
            final_approval_text: HAPROXY_FINAL_APPROVAL_TEXT,
            real_execution_text: HAPROXY_REAL_EXECUTION_TEXT,
            firewall_security_group_confirmed: createForm.firewallConfirmed,
            cloud_firewall_confirmed: createForm.firewallConfirmed,
            server_firewall_confirmed: createForm.firewallConfirmed,
            no_cutover_confirmed: true,
            no_node_share_link_change_confirmed: true,
            no_full_client_link_confirmed: true,
          },
          csrfToken,
        );
        if (!realExecutionResult.success) {
          throw new Error(`${realExecutionResult.error_code}: ${realExecutionResult.message}`);
        }
        if (!realExecutionResult.data.command) {
          throw new Error("HAProxy TCP 真实创建命令未返回，请刷新任务中心检查。");
        }
        setCreateCommand(realExecutionResult.data.command);
        const realCreateCommand = await waitForTransitCommandCompletion(realExecutionResult.data.command.id, "command_running");
        if (realCreateCommand.status !== "succeeded") {
          throw new Error(realCreateCommand.error_message || "HAProxy TCP 真实创建命令执行失败。");
        }

        setCreateStep("refresh");
        const refreshed = await loadData();
        const route = findCreatedTransitRoute(refreshed.routes);
        if (!route) {
          throw new Error("HAProxy TCP 创建命令已成功，但列表刷新后未找到 active 链路。请刷新页面确认。");
        }
        setCreatedRoute(route);

        setCreateStep("export_link");
        const exportResult = await exportTransitRouteCandidate(
          route.id,
          {
            confirm_transient_export: true,
            confirm_no_database_write: true,
            confirm_no_share_link_mutation: true,
            confirm_no_cutover: true,
            reason: "haproxy_transit_route_create_success",
          },
          csrfToken,
        );
        if (!exportResult.success) {
          throw new Error(`${exportResult.error_code}: ${exportResult.message}`);
        }
        setCreateExport(exportResult.data);
        setCreateStep("complete");
        setMessage("HAProxy TCP 中转链路创建完成。可以复制客户端链接或临时显示二维码。");
        return;
      }

      const preflightResult = await createTransitReadonlyPreflightCommand(
        {
          transit_resource_id: createResource.id,
          landing_node_id: createNode.id,
          planned_listen_port: createListenPort,
          landing_target_port: createTargetPort,
          forwarding_method: createForm.forwardingMethod,
          purpose: "直播",
          readonly: true,
        },
        csrfToken,
      );
      if (!preflightResult.success) {
        throw new Error(`${preflightResult.error_code}: ${preflightResult.message}`);
      }
      setCreateCommand(preflightResult.data.command);
      const preflightCommand = await waitForTransitCommandCompletion(preflightResult.data.command.id, "preflight_running");
      if (preflightCommand.status !== "succeeded") {
        throw new Error(preflightCommand.error_message || "中转只读预检未通过。");
      }

      setCreateStep("command_create");
      const createResult = await createTransitRouteWorkerExecuteCommand(
        {
          transit_resource_id: createResource.id,
          landing_node_id: createNode.id,
          planned_listen_port: createListenPort,
          landing_target_host: landingHostForNode(createNode),
          landing_target_port: createTargetPort,
          forwarding_method: createForm.forwardingMethod,
          purpose: "直播",
          route_name: routeName,
          approval_stage: approvedTransitRealCreateStage,
          dry_run: false,
          approval_required: false,
          user_approved_real_execution: true,
          firewall_security_group_confirmed: createForm.firewallConfirmed,
          cloud_firewall_confirmed: createForm.firewallConfirmed,
          server_firewall_confirmed: createForm.firewallConfirmed,
          no_node_share_link_change_confirmed: true,
          no_full_client_link_confirmed: true,
          no_cutover_confirmed: true,
        },
        csrfToken,
      );
      if (!createResult.success) {
        throw new Error(`${createResult.error_code}: ${createResult.message}`);
      }
      setCreateExecuteResult(createResult.data);
      setCreateCommand(createResult.data.command);
      const createCommandResult = await waitForTransitCommandCompletion(createResult.data.command.id, "command_running");
      if (createCommandResult.status !== "succeeded") {
        throw new Error(createCommandResult.error_message || "中转链路创建命令执行失败。");
      }

      setCreateStep("refresh");
      const refreshed = await loadData();
      const route = findCreatedTransitRoute(refreshed.routes);
      if (!route) {
        throw new Error("中转链路创建命令已成功，但列表刷新后未找到 active 链路。请刷新页面确认。");
      }
      setCreatedRoute(route);

      setCreateStep("export_link");
      const exportResult = await exportTransitRouteCandidate(
        route.id,
        {
          confirm_transient_export: true,
          confirm_no_database_write: true,
          confirm_no_share_link_mutation: true,
          confirm_no_cutover: true,
          reason: "transit_route_create_success",
        },
        csrfToken,
      );
      if (!exportResult.success) {
        throw new Error(`${exportResult.error_code}: ${exportResult.message}`);
      }
      setCreateExport(exportResult.data);
      setCreateStep("complete");
      setMessage("中转链路创建完成。可以复制客户端链接或临时显示二维码。");
    } catch (error) {
      const friendly = friendlyTransitCreateError(error);
      setCreateStep("failed");
      setCreateError(friendly);
      setMessage(`${friendly} 失败时不会写入 transit_routes.share_link，不会 cutover，也不会显示完整客户端链接。`);
    }
  }

  function downloadCreateTransitQrCode() {
    const svg = createQrFrameRef.current?.querySelector("svg");
    if (!svg || !createExport) {
      setMessage("请先显示二维码。");
      return;
    }
    const source = new XMLSerializer().serializeToString(svg);
    const blob = new Blob([source], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${createExport.route_name || "liveline-transit"}-qr.svg`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setMessage("中转测试二维码已下载。请妥善保存，不要公开分享。");
  }

  function selectCandidateRoute(routeId: string) {
    const switchingRoute = candidateRouteId !== routeId;
    setCandidateRouteId(routeId);
    if (switchingRoute) {
      setCandidateSummary(null);
      setCandidateExport(null);
      setCandidateCopyFallbackRequired(false);
    }
  }

  function openCandidateExportModal(routeId: string) {
    setCandidateExportRouteId(routeId);
    setCandidateExportModalOpen(true);
    setCandidateExport(null);
    setCandidateCopyFallbackRequired(false);
    setCandidateMessage("临时导出客户端链接只用于复制测试；不会保存到数据库、覆盖原节点链接或切换正式线路。");
  }

  function openDeleteRoute(routeId: string) {
    const route = routes.find((item) => item.id === routeId);
    setDeleteRouteId(routeId);
    setDeleteRouteConfirmText("");
    setDeleteRouteMode("remote_cleanup");
    setMessage(
      isHaproxyForwardingMethod(route?.forwarding_method)
        ? `HAProxy 中转链路远程清理删除会停止远程服务并释放监听端口 ${route?.listen_port ?? ""}；离线本地移除只隐藏本地记录。`
        : "中转链路删除可创建受控远程清理任务；离线本地移除不会停止远程服务或释放监听端口。",
    );
  }

  function closeDeleteRouteModal() {
    setDeleteRouteId("");
    setDeleteRouteConfirmText("");
    setDeleteRouteMode("remote_cleanup");
  }

  async function submitDeleteRoute() {
    const requiredConfirmText = deleteRoute ? transitRouteDeleteConfirmText(deleteRoute, deleteRouteMode) : "";
    if (!deleteRoute || deleteRouteConfirmText !== requiredConfirmText) {
      return;
    }
    const backendConfirmText = requiredDeleteConfirmText(deleteRouteMode);
    setCandidateLoading(true);
    setMessage(
      deleteRouteMode === "offline_local_remove"
        ? "正在离线本地移除中转链路记录；不会创建 Worker command 或执行远程清理。"
        : "正在创建中转链路远程清理任务；清理成功后会停止远程服务并软删除系统记录。",
    );
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await remoteCleanupDeleteTransitRoute(deleteRoute.id, csrfToken, backendConfirmText);
      if (!result.success) {
        if (result.error_code === "REMOTE_CLEANUP_UNAVAILABLE" && isOfflineLocalRemoveOffer(result.data)) {
          setDeleteRouteMode("offline_local_remove");
          setDeleteRouteConfirmText("");
          setMessage(result.message);
          return;
        }
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setMessage(
        result.data.delete_mode === "offline_local_remove"
          ? "已离线本地移除记录。由于 Worker 离线，未执行远程清理；远程服务和监听端口可能仍然存在。"
          : `清理任务已创建：${result.data.command_id}。等待 Worker 执行；远程清理成功后将软删除系统记录。`,
      );
      closeDeleteRouteModal();
      setCandidateSummary(null);
      setCandidateExport(null);
      await loadData();
      scheduleRouteDataRefresh();
      void refreshWhenRouteCleanupCommandCompletes(result.data.command);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "删除中转链路失败。");
    } finally {
      setCandidateLoading(false);
    }
  }

  function closeCandidateExportModal() {
    setCandidateExportModalOpen(false);
    setCandidateExportRouteId("");
    setCandidateExport(null);
    setCandidateCopyFallbackRequired(false);
    setCandidateMessage("候选链路摘要尚未加载；不会自动导出完整测试配置。");
  }

  async function loadCandidateSummary(routeId = primaryActiveRoute?.id ?? "") {
    if (!routeId) {
      setCandidateMessage("暂无可读取摘要的 active 中转链路。");
      return;
    }
    selectCandidateRoute(routeId);
    setCandidateLoading(true);
    setCandidateMessage("正在读取候选链路安全摘要；不会读取或导出完整 nodes.share_link。");
    try {
      const result = await getTransitRouteCandidateSummary(routeId);
      if (!result.success) {
        setCandidateMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setCandidateSummary(result.data);
      setCandidateMessage("候选链路摘要已加载；未导出完整测试配置。");
    } catch (error) {
      setCandidateMessage(error instanceof Error ? error.message : "读取候选链路摘要失败。");
    } finally {
      setCandidateLoading(false);
    }
  }

  async function exportCandidateConfig(routeId = candidateExportRouteId) {
    if (!routeId) {
      setCandidateMessage("请先选择一条中转链路。");
      return;
    }
    setCandidateLoading(true);
    setCandidateMessage("正在临时生成客户端链接；不会写入数据库、修改 nodes.share_link 或执行 cutover。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await exportTransitRouteCandidate(
        routeId,
        {
          confirm_transient_export: true,
          confirm_no_database_write: true,
          confirm_no_share_link_mutation: true,
          confirm_no_cutover: true,
          reason: "client_candidate_test",
        },
        csrfToken,
      );
      if (!result.success) {
        setCandidateMessage(`${result.error_code}: ${result.message}。未生成临时链接，未修改任何线路配置。`);
        return;
      }
      const route = routes.find((item) => item.id === routeId) ?? primaryActiveRoute ?? null;
      setCandidateExport(result.data);
      setCandidateCopyFallbackRequired(false);
      setCandidateSummary((current) => current?.route_id === routeId ? current : {
        route_id: result.data.route_id,
        route_name: result.data.route_name,
        transit_resource_id: route?.transit_resource_id ?? "",
        transit_resource_name: null,
        entry_host: result.data.server,
        listen_port: result.data.port,
        target_host: route?.target_host ?? "",
        target_port: route?.target_port ?? 0,
        forwarding_method: route?.forwarding_method ?? "socat",
        service_name: route?.service_name ?? "",
        service_path: route?.service_path ?? "",
        status: route?.status ?? "active",
        landing_node_id: route?.node_id ?? "",
        landing_node_name: route?.node_name ?? null,
        landing_vps_ip: route?.landing_vps_ip ?? null,
        route_share_link_present: Boolean(route?.share_link),
        share_link_present: false,
        recommended_candidate: true,
        cutover_status: result.data.cutover_status,
        safety_boundary: result.data.safety_boundary,
      });
      setCandidateMessage("临时客户端链接已生成；完整链接仅保存在本次响应内，请只用于手动导入测试。");
    } catch (error) {
      const message = error instanceof Error ? error.message : "临时导出客户端链接失败。";
      setCandidateMessage(`${message} 未生成临时链接，未修改任何线路配置。`);
    } finally {
      setCandidateLoading(false);
    }
  }

  useEffect(() => {
    setDraft((current) => {
      const nextResourceId = current.transitResourceId || selectableResources[0]?.id || "";
      const nextNodeId = current.landingNodeId || activeNodes[0]?.id || "";
      return {
        ...current,
        transitResourceId: nextResourceId,
        landingNodeId: nextNodeId,
        plannedListenPort: current.plannedListenPort || "23843",
      };
    });
  }, [selectableResources, activeNodes]);

  useEffect(() => {
    setHaproxyReadiness(null);
    setHaproxyReadinessMessage("HAProxy TCP readiness 尚未生成。");
    setHaproxyDryRun(null);
    setHaproxyDryRunMessage("HAProxy route dry-run 尚未生成。");
    setHaproxyFinalApproval(null);
    setHaproxyFinalApprovalMessage("HAProxy route 最终审批包尚未生成。");
    setHaproxyFinalApprovalText("");
    setHaproxyRealExecution(null);
    setHaproxyRealExecutionMessage("HAProxy route 真实创建尚未授权。");
    setHaproxyRealExecutionText("");
  }, [
    selectedResource?.id,
    selectedNode?.id,
    draft.plannedListenPort,
    draft.forwardingMethod,
    targetPort,
    haproxyReadinessConfirmations,
  ]);

  function readonlyPayload(): ReadonlyPreflightPlanRequest {
    return {
      transit_resource_id: selectedResource?.id ?? null,
      transit_resource_name: selectedResource?.name ?? null,
      transit_host_hint: selectedResource?.entry_host ?? null,
      landing_node_id: selectedNode?.id ?? null,
      landing_node_name: selectedNode?.node_name ?? null,
      landing_host_hint: landingHostForNode(selectedNode),
      landing_target_port: targetPort ? String(targetPort) : "",
      planned_listen_port: draft.plannedListenPort,
      route_purpose: draft.purpose || null,
      firewall_security_group_confirmed: true,
      cloud_firewall_confirmed: true,
      server_firewall_confirmed: true,
      local_backup_confirmed: true,
      user_approved_readonly_preflight: true,
      workbuddy_authorized: true,
      no_cutover_confirmed: true,
      no_node_share_link_change_confirmed: true,
    };
  }

  async function generateReadonlyPlan() {
    setReadonlyPreflightLoading(true);
    setReadonlyPreflightApiMessage("正在生成本地 no-op 只读预检计划。");
    try {
      const result = await requestReadonlyPreflightPlan(readonlyPayload());
      if (!result.success) {
        setReadonlyPreflightApiMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setReadonlyPlan(result.data);
      setReadonlyPreflightApiMessage(result.data.summary);
    } catch (error) {
      setReadonlyPreflightApiMessage(error instanceof Error ? error.message : "生成只读预检计划失败。");
    } finally {
      setReadonlyPreflightLoading(false);
    }
  }

  async function runRemoteReadonlyPreflight() {
    if (!selectedResource || !selectedNode || plannedPort === null || targetPort <= 0) {
      setRemotePreflightMessage("计划参数不完整，不能创建远程只读预检命令。");
      return;
    }
    setRemotePreflightLoading(true);
    setRemotePreflightMessage("正在创建 transit_readonly_preflight Worker command。");
    try {
      const csrfToken = await ensureCsrfToken();
      const payload: TransitReadonlyPreflightCommandRequest = {
        transit_resource_id: selectedResource.id,
        landing_node_id: selectedNode.id,
        planned_listen_port: plannedPort,
        landing_target_port: targetPort,
        forwarding_method: draft.forwardingMethod,
        purpose: draft.purpose || null,
        readonly: true,
      };
      const result = await createTransitReadonlyPreflightCommand(payload, csrfToken);
      if (!result.success) {
        setRemotePreflightMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setRemotePreflightCommand(result.data.command);
      setRemotePreflightMessage(`只读预检命令已创建：${result.data.command.id}`);
    } catch (error) {
      setRemotePreflightMessage(error instanceof Error ? error.message : "创建远程只读预检命令失败。");
    } finally {
      setRemotePreflightLoading(false);
    }
  }

  function updateHaproxyReadinessConfirmation(key: keyof HaproxyReadinessConfirmations, value: boolean) {
    setHaproxyReadinessConfirmations((current) => ({ ...current, [key]: value }));
  }

  async function generateHaproxyReadinessApproval() {
    if (!selectedResource || !selectedNode || plannedPort === null || targetPort <= 0) {
      setHaproxyReadinessMessage("计划参数不完整，不能生成 HAProxy readiness。");
      return;
    }
    if (draft.forwardingMethod !== "haproxy_tcp") {
      setHaproxyReadinessMessage("请先把转发方式切换为 HAProxy TCP mode。");
      return;
    }
    setHaproxyReadinessLoading(true);
    setHaproxyReadinessMessage("正在生成只读 HAProxy TCP route 创建审批包；不会创建 Worker command。");
    try {
      const result = await requestTransitHaproxyReadinessApproval({
        transit_resource_id: selectedResource.id,
        landing_node_id: selectedNode.id,
        planned_listen_port: plannedPort,
        landing_target_port: targetPort,
        forwarding_method: "haproxy_tcp",
        purpose: draft.purpose || null,
        firewall_security_group_confirmed: haproxyReadinessConfirmations.securityGroup,
        cloud_firewall_confirmed: haproxyReadinessConfirmations.cloudFirewall,
        server_firewall_confirmed: haproxyReadinessConfirmations.serverFirewall,
        no_cutover_confirmed: haproxyReadinessConfirmations.noCutover,
        no_node_share_link_change_confirmed: haproxyReadinessConfirmations.noShareLinkMutation,
        no_full_client_link_confirmed: haproxyReadinessConfirmations.noFullClientLink,
      });
      if (!result.success) {
        setHaproxyReadinessMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setHaproxyReadiness(result.data);
      setHaproxyReadinessMessage(result.data.summary);
    } catch (error) {
      setHaproxyReadinessMessage(error instanceof Error ? error.message : "生成 HAProxy readiness 失败。");
    } finally {
      setHaproxyReadinessLoading(false);
    }
  }

  async function createHaproxyRouteDryRun() {
    if (!selectedResource || !selectedNode || plannedPort === null || targetPort <= 0) {
      setHaproxyDryRunMessage("计划参数不完整，不能生成 HAProxy route dry-run。");
      return;
    }
    if (draft.forwardingMethod !== "haproxy_tcp") {
      setHaproxyDryRunMessage("请先把转发方式切换为 HAProxy TCP mode。");
      return;
    }
    if (!haproxyReadiness?.ready) {
      setHaproxyDryRunMessage("请先生成并通过 HAProxy TCP readiness 审批包。");
      return;
    }

    setHaproxyDryRunLoading(true);
    setHaproxyDryRunMessage("正在创建 HAProxy route dry-run Worker command；不会创建真实 HAProxy route。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await createTransitHaproxyRouteDryRun(
        {
          transit_resource_id: selectedResource.id,
          landing_node_id: selectedNode.id,
          planned_listen_port: plannedPort,
          landing_target_host: landingHostForNode(selectedNode),
          landing_target_port: targetPort,
          forwarding_method: "haproxy_tcp",
          purpose: draft.purpose || null,
          route_name: haproxyReadiness.planned_route.route_name || `haproxy-tcp-${plannedPort}`,
          approval_stage: "Stage 3.3.137-new-transit-haproxy-route-create-dry-run",
          readiness_approval_confirmed: true,
          dry_run: true,
          approval_required: true,
          firewall_security_group_confirmed: haproxyReadinessConfirmations.securityGroup,
          cloud_firewall_confirmed: haproxyReadinessConfirmations.cloudFirewall,
          server_firewall_confirmed: haproxyReadinessConfirmations.serverFirewall,
          no_cutover_confirmed: haproxyReadinessConfirmations.noCutover,
          no_node_share_link_change_confirmed: haproxyReadinessConfirmations.noShareLinkMutation,
          no_full_client_link_confirmed: haproxyReadinessConfirmations.noFullClientLink,
        },
        csrfToken,
      );
      if (!result.success) {
        setHaproxyDryRunMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setHaproxyDryRun(result.data);
      setHaproxyFinalApproval(null);
      setHaproxyFinalApprovalText("");
      setHaproxyFinalApprovalMessage("HAProxy route 最终审批包尚未生成。");
      setHaproxyRealExecution(null);
      setHaproxyRealExecutionText("");
      setHaproxyRealExecutionMessage("HAProxy route 真实创建尚未授权。");
      setHaproxyDryRunMessage(`HAProxy route dry-run command 已创建：${result.data.command.id}。未创建真实监听。`);
    } catch (error) {
      setHaproxyDryRunMessage(error instanceof Error ? error.message : "创建 HAProxy route dry-run 失败。");
    } finally {
      setHaproxyDryRunLoading(false);
    }
  }

  async function generateHaproxyFinalApproval() {
    if (!selectedResource || !selectedNode || !haproxyDryRun) {
      setHaproxyFinalApprovalMessage("缺少 dry-run 结果，不能生成最终审批包。");
      return;
    }
    if (haproxyFinalApprovalText.trim() !== HAPROXY_FINAL_APPROVAL_TEXT) {
      setHaproxyFinalApprovalMessage(`请先输入最终确认文本：${HAPROXY_FINAL_APPROVAL_TEXT}`);
      return;
    }

    setHaproxyFinalApprovalLoading(true);
    setHaproxyFinalApprovalMessage("正在生成 HAProxy route 最终审批包；不会创建 Worker command。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await requestTransitHaproxyRouteFinalApproval(
        {
          dry_run_command_id: haproxyDryRun.command.id,
          transit_resource_id: selectedResource.id,
          landing_node_id: selectedNode.id,
          planned_listen_port: haproxyDryRun.planned_listen_port,
          landing_target_host: haproxyDryRun.landing_target_host,
          landing_target_port: haproxyDryRun.landing_target_port,
          forwarding_method: "haproxy_tcp",
          route_name: haproxyDryRun.route_name,
          planned_service_name: haproxyDryRun.planned_service_name,
          approval_stage: "Stage 3.3.138-new-transit-haproxy-route-create-final-approval",
          dry_run_verified: true,
          firewall_security_group_confirmed: haproxyReadinessConfirmations.securityGroup,
          cloud_firewall_confirmed: haproxyReadinessConfirmations.cloudFirewall,
          server_firewall_confirmed: haproxyReadinessConfirmations.serverFirewall,
          no_cutover_confirmed: haproxyReadinessConfirmations.noCutover,
          no_node_share_link_change_confirmed: haproxyReadinessConfirmations.noShareLinkMutation,
          no_full_client_link_confirmed: haproxyReadinessConfirmations.noFullClientLink,
          final_approval_text: haproxyFinalApprovalText.trim(),
        },
        csrfToken,
      );
      if (!result.success) {
        setHaproxyFinalApprovalMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setHaproxyFinalApproval(result.data);
      setHaproxyRealExecution(null);
      setHaproxyRealExecutionText("");
      setHaproxyRealExecutionMessage("HAProxy route 真实创建尚未授权。");
      setHaproxyFinalApprovalMessage(result.data.summary);
    } catch (error) {
      setHaproxyFinalApprovalMessage(error instanceof Error ? error.message : "生成 HAProxy route 最终审批包失败。");
    } finally {
      setHaproxyFinalApprovalLoading(false);
    }
  }

  async function createHaproxyRealExecutionCommand() {
    if (!selectedResource || !selectedNode || !haproxyDryRun || !haproxyFinalApproval?.ready_for_real_create) {
      setHaproxyRealExecutionMessage("缺少已通过的 dry-run / final approval，不能创建真实执行命令。");
      return;
    }
    if (haproxyRealExecutionText.trim() !== HAPROXY_REAL_EXECUTION_TEXT) {
      setHaproxyRealExecutionMessage(`请先输入真实执行确认文本：${HAPROXY_REAL_EXECUTION_TEXT}`);
      return;
    }

    setHaproxyRealExecutionLoading(true);
    setHaproxyRealExecutionMessage("正在创建受控 HAProxy TCP route 真实执行 Worker command。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await createTransitHaproxyRouteRealExecution(
        {
          dry_run_command_id: haproxyDryRun.command.id,
          transit_resource_id: selectedResource.id,
          landing_node_id: selectedNode.id,
          planned_listen_port: haproxyFinalApproval.planned_listen_port,
          landing_target_host: haproxyFinalApproval.landing_target_host,
          landing_target_port: haproxyFinalApproval.landing_target_port,
          forwarding_method: "haproxy_tcp",
          route_name: haproxyFinalApproval.route_name,
          approval_stage: "Stage 3.3.139-new-transit-haproxy-route-create-real-execution",
          firewall_security_group_confirmed: haproxyReadinessConfirmations.securityGroup,
          cloud_firewall_confirmed: haproxyReadinessConfirmations.cloudFirewall,
          server_firewall_confirmed: haproxyReadinessConfirmations.serverFirewall,
          no_cutover_confirmed: haproxyReadinessConfirmations.noCutover,
          no_node_share_link_change_confirmed: haproxyReadinessConfirmations.noShareLinkMutation,
          no_full_client_link_confirmed: haproxyReadinessConfirmations.noFullClientLink,
          final_approval_text: haproxyFinalApprovalText.trim(),
          real_execution_text: haproxyRealExecutionText.trim(),
        },
        csrfToken,
      );
      if (!result.success) {
        setHaproxyRealExecutionMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setHaproxyRealExecution(result.data);
      setHaproxyRealExecutionMessage(result.data.summary);
    } catch (error) {
      setHaproxyRealExecutionMessage(error instanceof Error ? error.message : "创建 HAProxy route 真实执行命令失败。");
    } finally {
      setHaproxyRealExecutionLoading(false);
    }
  }

  async function refreshRemoteCommand() {
    if (!remotePreflightCommand) {
      return;
    }
    const result = await getWorkerCommand(remotePreflightCommand.id);
    if (!result.success) {
      setRemotePreflightMessage(formatApiError(result));
      return;
    }
    setRemotePreflightCommand(result.data);
    setRemotePreflightMessage(`命令状态已刷新：${displayStatusLabel(result.data.status)}`);
  }

  async function copyPreflightSummary() {
    const summary = [
      `中转服务器：${selectedResource?.name ?? "-"}`,
      `落地节点：${selectedNode?.node_name ?? "-"}`,
      `计划监听端口：${draft.plannedListenPort}`,
      `目标端口：${targetPort || "-"}`,
      `只读预检：${remotePreflightCommand?.status ?? "未执行"}`,
      "安全边界：未创建真实转发，未新增监听端口，未修改防火墙、Xray 或 nodes.share_link。",
    ].join("\n");
    try {
      await copyText(summary);
      setPreflightSummaryCopied(true);
    } catch {
      setReadonlyPreflightApiMessage("当前 HTTP 环境可能不支持自动复制，请手动复制只读预检摘要。");
    }
  }

  async function createWorkerDryRunPlan() {
    if (!selectedResource || !selectedNode || plannedPort === null || targetPort <= 0) {
      setMessage("计划参数不完整，不能创建 Worker dry-run 计划。");
      return;
    }
    setWorkerCreateLoading(true);
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await apiFetch<TransitRouteWorkerCreatePlanResult>("/api/transit-routes/worker-create-plan", {
        method: "POST",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify({
          transit_resource_id: selectedResource.id,
          landing_node_id: selectedNode.id,
          planned_listen_port: plannedPort,
          landing_target_host: landingHostForNode(selectedNode),
          landing_target_port: targetPort,
          forwarding_method: draft.forwardingMethod,
          purpose: draft.purpose || null,
          dry_run: true,
          approval_required: true,
          user_approved_execution_boundary: true,
          no_node_share_link_change_confirmed: true,
          no_cutover_confirmed: true,
        }),
      });
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setWorkerCreatePlan(result.data);
      setMessage(`Worker create path dry-run command 已创建：${result.data.command.id}。未创建真实监听。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "创建 Worker dry-run 计划失败。");
    } finally {
      setWorkerCreateLoading(false);
    }
  }

  return (
    <section className="panel wide">
      <div className="status-row">
        <div>
          <h2>中转链路</h2>
        </div>
        <div className="server-actions">
          <button type="button" onClick={openCreateRouteModal}>
            新增中转链路
          </button>
          <button className="secondary" type="button" onClick={() => void loadData()}>
            刷新
          </button>
        </div>
      </div>

      {primaryActiveRoute ? (
        <div className="candidate-summary-grid transit-route-inline-panel">
          <span>当前 active 链路</span>
          <strong>{primaryActiveRoute.name}</strong>
          <span>入口</span>
          <strong>{routeEntry(primaryActiveRoute)}</strong>
          <span>转发方式</span>
          <strong>{forwardingMethodLabel(primaryActiveRoute.forwarding_method)}</strong>
          <span>监听端口</span>
          <strong>{primaryActiveRoute.listen_port}</strong>
          <span>SHARE_LINK</span>
          <strong>{routeHasShareLink(primaryActiveRoute) ? "已写入" : "未写入"}</strong>
          <span>CUTOVER</span>
          <strong>{routeCutoverStatusLabel(primaryActiveRoute.id)}</strong>
        </div>
      ) : (
        <div className="transit-route-inline-panel">
          <p className="message">暂无 active 中转链路。新增链路弹窗只在本地生成配置预览，真实创建仍需受保护流程。</p>
        </div>
      )}

      <div className="transit-route-table-scroll">
        <div className="server-table transit-route-table" aria-label="中转链路列表">
          <div className="server-table-row server-table-head transit-route-table-row">
            <span>名称</span>
            <span>入口</span>
            <span>目标</span>
            <span>转发方式</span>
            <span>状态</span>
            <span>操作</span>
          </div>
          {loading ? <div className="server-table-empty">正在加载中转链路。</div> : null}
          {!loading && routes.length === 0 ? <div className="server-table-empty">暂无中转链路记录。</div> : null}
          {!loading
            ? routes.map((route) => {
              const routeSelected = candidateRouteId === route.id;
              const routeSummaryVisible = candidateSummary?.route_id === route.id;
              const entryLabel = routeEntry(route);
              const targetLabel = `${route.target_host}:${route.target_port}`;
              const serviceLabel = route.service_name || "-";
              const shareLinkLabel = routeHasShareLink(route) ? "已写入" : "未写入";
              const cutoverLabel = routeCutoverStatusLabel(route.id);

              return (
                <div className="server-table-group transit-route-table-group" key={route.id}>
                  <div className="server-table-row transit-route-table-row transit-route-main-row">
                    <strong className="table-ellipsis" title={route.name}>
                      {route.name}
                    </strong>
                    <span className="table-ellipsis" title={entryLabel}>
                      {entryLabel}
                    </span>
                    <span className="table-ellipsis" title={targetLabel}>
                      {targetLabel}
                    </span>
                    <span>{forwardingMethodLabel(route.forwarding_method)}</span>
                    <span title={route.status}>
                      <span className={`pill ${statusClass(route.status)}`}>{displayStatusLabel(route.status)}</span>
                    </span>
                    <div className="server-actions transit-route-row-actions">
                      <button className="secondary compact" disabled={candidateLoading} type="button" onClick={() => void loadCandidateSummary(route.id)}>
                        查看摘要
                      </button>
                      <button className="secondary compact" disabled={candidateLoading} type="button" onClick={() => openCandidateExportModal(route.id)}>
                        临时导出客户端链接
                      </button>
                      <button
                        className="secondary compact ghost-action"
                        type="button"
                        onClick={() => {
                          selectCandidateRoute(route.id);
                          setCandidateMessage(`链路详情：服务 ${serviceLabel}；SHARE_LINK ${shareLinkLabel}；CUTOVER ${cutoverLabel}。`);
                        }}
                      >
                        详情
                      </button>
                      <button className="danger compact" disabled={candidateLoading} type="button" onClick={() => openDeleteRoute(route.id)}>
                        远程清理删除
                      </button>
                    </div>
                  </div>

                  <div className="server-row-worker transit-route-detail-row">
                    <span className="transit-route-detail-text" title={`服务：${serviceLabel}；SHARE_LINK：${shareLinkLabel}；CUTOVER：${cutoverLabel}`}>
                      服务：{serviceLabel}；SHARE_LINK：{shareLinkLabel}；CUTOVER：{cutoverLabel}
                    </span>
                  </div>

                  {routeSummaryVisible ? (
                    <div className="candidate-summary-grid transit-route-inline-panel">
                      <span>候选名称</span>
                      <strong>{candidateSummary.route_name}</strong>
                      <span>入口</span>
                      <strong>{candidateSummary.entry_host}:{candidateSummary.listen_port}</strong>
                      <span>目标</span>
                      <strong>{candidateSummary.target_host}:{candidateSummary.target_port}</strong>
                      <span>服务</span>
                      <strong>{candidateSummary.service_name}</strong>
                      <span>share_link</span>
                      <strong>{candidateSummary.route_share_link_present ? "已写入" : "NULL / 未写入"}</strong>
                      <span>cutover</span>
                      <strong>{candidateSummary.cutover_status === "not_cutover" ? "未切换" : candidateSummary.cutover_status}</strong>
                    </div>
                  ) : null}

                  {routeSelected ? <p className="message transit-route-inline-message">{candidateMessage}</p> : null}
                </div>
              );
            })
            : null}
        </div>
      </div>

      <details
        className="advanced-section transit-advanced-section hidden"
        style={{ display: "none" }}
        open={advancedTransitOpsOpen}
        onToggle={(event) => setAdvancedTransitOpsOpen(event.currentTarget.open)}
      >
        <summary className="advanced-section-toggle">
          <div>
            <span className="page-eyebrow">高级操作（默认折叠）</span>
            <strong>高级调试与审批操作</strong>
            <p>
              这些功能主要用于开发、审批或故障排查。日常搭建网络时一般不需要展开。展开前请确认不会误触发 Worker command
              或远程操作。
            </p>
          </div>
          <span className="notice-toggle-text">
            <span className="when-closed">展开高级调试</span>
            <span className="when-open">收起高级调试</span>
          </span>
        </summary>
        <div className="advanced-section-body">
          <div className="advanced-section-warning">
            <strong>高级区安全提示</strong>
            <span>本区域包含本地规划、只读预检、Worker allowlist 和 dry-run 创建路径入口；按钮不会自动触发，但点击后可能创建 Worker command。</span>
            <span>不需要调试或重新审批时，请保持折叠，只使用上方候选摘要、临时导出和下方中转链路列表。</span>
          </div>

          <div className="form route-form">
            <label>
              中转服务器
              <select
                value={selectedResource?.id ?? ""}
                onChange={(event) => setDraft({ ...draft, transitResourceId: event.target.value })}
              >
                {selectableResources.length === 0 ? <option value="">暂无可用于本地规划的中转服务器</option> : null}
                {selectableResources.map((resource) => (
                  <option key={resource.id} value={resource.id}>
                    {resource.name} / {displayValue(resource.entry_host)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              落地节点
              <select
                value={selectedNode?.id ?? ""}
                onChange={(event) => {
                  setDraft({
                    ...draft,
                    landingNodeId: event.target.value,
                  });
                }}
              >
                {activeNodes.length === 0 ? <option value="">暂无 active 落地节点</option> : null}
                {activeNodes.map((node) => (
                  <option key={node.id} value={node.id}>
                    {node.node_name} / {displayValue(node.vps_ip)}:{displayValue(node.port)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              监听端口
              <input value={draft.plannedListenPort} onChange={(event) => setDraft({ ...draft, plannedListenPort: event.target.value })} />
            </label>
            <label>
              转发方式
              <select
                value={draft.forwardingMethod}
                onChange={(event) => setDraft({ ...draft, forwardingMethod: event.target.value as TransitForwardingMethod })}
              >
                <option value="socat">socat</option>
                <option value="haproxy_tcp">HAProxy TCP mode</option>
                <option value="gost">gost</option>
              </select>
            </label>
            <label>
              用途
              <input value={draft.purpose} onChange={(event) => setDraft({ ...draft, purpose: event.target.value })} />
            </label>
            <div className="warning-box wide-field">
              <strong>端口放行提醒</strong>
              <span>新增或变更监听端口后，必须同步检查云服务器安全组 / 云防火墙 / 服务器防火墙是否放行对应 TCP 端口。</span>
              <span>当前面板不会创建真实转发，也不会绑定端口或修改防火墙。</span>
            </div>
          </div>

          <TransitReadonlyPreflightSimplePanel
            ready={preflightReady}
            statusLabel={planningIssues.length === 0 ? "可预检" : "待确认"}
            resourceName={selectedResource?.name ?? ""}
            nodeName={selectedNode?.node_name ?? ""}
            plannedListenPort={draft.plannedListenPort}
            targetPort={targetPort ? String(targetPort) : ""}
            issues={planningIssues}
            healthConfirmed={healthConfirmed}
            boundaryConfirmed={boundaryConfirmed}
            workerBoundaryConfirmed={workerBoundaryConfirmed}
            readonlyPreflightLoading={readonlyPreflightLoading}
            remotePreflightLoading={remotePreflightLoading}
            readonlyPreflightApiMessage={readonlyPreflightApiMessage}
            remotePreflightMessage={remotePreflightMessage}
            readonlyPreflightPlan={readonlyPlan}
            remotePreflightCommand={remotePreflightCommand}
            preflightSummaryCopied={preflightSummaryCopied}
            onHealthConfirmedChange={setHealthConfirmed}
            onBoundaryConfirmedChange={setBoundaryConfirmed}
            onWorkerBoundaryConfirmedChange={setWorkerBoundaryConfirmed}
            onGeneratePlan={() => void generateReadonlyPlan()}
            onRunCommand={() => void runRemoteReadonlyPreflight()}
            onRefreshCommand={() => void refreshRemoteCommand()}
            onCopySummary={() => void copyPreflightSummary()}
          />

          <div className="haproxy-readiness-panel">
            <div className="status-row">
              <div>
                <h3>HAProxy TCP route 创建审批包</h3>
                <p className="message">
                  只读生成 HAProxy TCP readiness/approval，不创建 Worker command、不安装 HAProxy、不创建监听端口、不导出完整客户端链接。
                </p>
              </div>
              <button className="secondary" disabled={haproxyReadinessLoading} type="button" onClick={() => void generateHaproxyReadinessApproval()}>
                {haproxyReadinessLoading ? "生成中" : "生成 HAProxy route 创建审批包"}
              </button>
            </div>

            <div className="haproxy-readiness-grid">
              <span>中转资源</span>
              <strong>{selectedResource ? `${selectedResource.name} / ${displayValue(selectedResource.entry_host)}` : "未选择"}</strong>
              <span>Worker</span>
              <strong>
                {displayStatusLabel(selectedResource?.worker_display_status ?? selectedResource?.worker_status)} / {displayValue(selectedResource?.worker_version)}
              </strong>
              <span>网卡</span>
              <strong>{displayValue(selectedResource?.worker_interface_name)}</strong>
              <span>落地节点</span>
              <strong>{selectedNode ? `${selectedNode.node_name} / ${landingHostForNode(selectedNode)}:${targetPort || "-"}` : "未选择"}</strong>
              <span>计划监听</span>
              <strong>{draft.plannedListenPort || "-"}</strong>
              <span>转发方式</span>
              <strong>{draft.forwardingMethod === "haproxy_tcp" ? "HAProxy TCP mode" : "请切换到 HAProxy TCP mode"}</strong>
            </div>

            <div className="haproxy-readiness-warning">
              <strong>端口放行人工确认</strong>
              <span>真实创建前必须人工确认监听端口已在云安全组、云防火墙、服务器本机防火墙同时放行。</span>
              <span>本阶段只生成审批包，不远程检查、不修改防火墙、不创建 HAProxy service。</span>
            </div>

            <div className="haproxy-confirm-list">
              <label className="haproxy-confirm-row">
                <input
                  type="checkbox"
                  checked={haproxyReadinessConfirmations.securityGroup}
                  onChange={(event) => updateHaproxyReadinessConfirmation("securityGroup", event.target.checked)}
                />
                <span>我确认云安全组已放行该 HAProxy TCP 监听端口。</span>
              </label>
              <label className="haproxy-confirm-row">
                <input
                  type="checkbox"
                  checked={haproxyReadinessConfirmations.cloudFirewall}
                  onChange={(event) => updateHaproxyReadinessConfirmation("cloudFirewall", event.target.checked)}
                />
                <span>我确认云防火墙已放行该 HAProxy TCP 监听端口。</span>
              </label>
              <label className="haproxy-confirm-row">
                <input
                  type="checkbox"
                  checked={haproxyReadinessConfirmations.serverFirewall}
                  onChange={(event) => updateHaproxyReadinessConfirmation("serverFirewall", event.target.checked)}
                />
                <span>我确认服务器本机防火墙已放行该 HAProxy TCP 监听端口。</span>
              </label>
              <label className="haproxy-confirm-row">
                <input
                  type="checkbox"
                  checked={haproxyReadinessConfirmations.noCutover}
                  onChange={(event) => updateHaproxyReadinessConfirmation("noCutover", event.target.checked)}
                />
                <span>我确认本阶段不 cutover。</span>
              </label>
              <label className="haproxy-confirm-row">
                <input
                  type="checkbox"
                  checked={haproxyReadinessConfirmations.noShareLinkMutation}
                  onChange={(event) => updateHaproxyReadinessConfirmation("noShareLinkMutation", event.target.checked)}
                />
                <span>我确认本阶段不读取或修改 nodes.share_link，也不写 transit_routes.share_link。</span>
              </label>
              <label className="haproxy-confirm-row">
                <input
                  type="checkbox"
                  checked={haproxyReadinessConfirmations.noFullClientLink}
                  onChange={(event) => updateHaproxyReadinessConfirmation("noFullClientLink", event.target.checked)}
                />
                <span>我确认本阶段不生成、不展示、不记录完整客户端链接。</span>
              </label>
            </div>

            <div className="haproxy-disabled-actions">
              <strong>后续阶段入口</strong>
              <span>本阶段只允许创建 dry-run Worker command；真实创建 HAProxy route、安装 HAProxy、绑定监听和生成客户端链接均未接入。</span>
              <button className="secondary compact" disabled type="button">
                下一阶段才允许创建 HAProxy route
              </button>
            </div>

            {haproxyReadiness ? (
              <div className={`haproxy-readiness-result ${haproxyReadiness.ready ? "ready" : "blocked"}`}>
                <strong>{haproxyReadiness.ready ? "ready" : "blocked"}：{haproxyReadiness.summary}</strong>
                <span>{haproxyReadiness.next_action}</span>
                <div className="haproxy-readiness-grid">
                  <span>计划 service</span>
                  <strong>{haproxyReadiness.planned_route.service_name}</strong>
                  <span>入口</span>
                  <strong>{displayValue(haproxyReadiness.transit_resource.entry_host)}:{haproxyReadiness.planned_route.planned_listen_port}</strong>
                  <span>目标</span>
                  <strong>{displayValue(haproxyReadiness.planned_route.landing_target_host)}:{haproxyReadiness.planned_route.landing_target_port}</strong>
                  <span>Worker 最低版本</span>
                  <strong>{haproxyReadiness.transit_worker.minimum_supported_worker_version}</strong>
                </div>
                <div className="haproxy-readiness-checks">
                  {haproxyReadiness.checks.map((check) => (
                    <div className="haproxy-readiness-check" key={check.id}>
                      <span className={`pill ${check.passed ? "ok" : "warn"}`}>{check.passed ? "通过" : "阻塞"}</span>
                      <strong>{check.label}</strong>
                      <span>{check.message}</span>
                      {!check.passed ? <small>{check.next_action}</small> : null}
                    </div>
                  ))}
                </div>
                <details className="node-create-safety-details">
                  <summary>本审批包安全边界</summary>
                  <div className="node-create-safety-body">
                    {haproxyReadiness.safety_boundary.map((item) => (
                      <span key={item}>{item}</span>
                    ))}
                  </div>
                </details>
              </div>
            ) : null}

            <div className="haproxy-dry-run-panel">
              <div className="status-row">
                <div>
                  <h3>HAProxy route 创建 dry-run</h3>
                  <p className="message">
                    只创建 dry-run Worker command，用于记录计划 service、监听端口、目标端口和安全边界；不会创建真实 HAProxy route。
                  </p>
                </div>
                <button
                  className="secondary"
                  disabled={haproxyDryRunLoading || !haproxyReadiness?.ready}
                  type="button"
                  onClick={() => void createHaproxyRouteDryRun()}
                >
                  {haproxyDryRunLoading ? "生成中" : "生成 HAProxy route dry-run 创建计划"}
                </button>
              </div>

              <div className="haproxy-readiness-grid">
                <span>计划 service</span>
                <strong>{haproxyReadiness?.planned_route.service_name ?? `liveline-haproxy-${draft.plannedListenPort || "-"}.service`}</strong>
                <span>计划监听</span>
                <strong>{draft.plannedListenPort || "-"}</strong>
                <span>目标</span>
                <strong>{selectedNode ? `${landingHostForNode(selectedNode)}:${targetPort || "-"}` : "未选择"}</strong>
                <span>转发方式</span>
                <strong>haproxy_tcp</strong>
                <span>下一阶段</span>
                <strong>Stage 3.3.138 final approval</strong>
              </div>

              {haproxyDryRun ? (
                <div className="haproxy-readiness-result ready">
                  <strong>dry-run command 已创建：{haproxyDryRun.command.id}</strong>
                  <div className="haproxy-readiness-grid">
                    <span>planned service</span>
                    <strong>{haproxyDryRun.planned_service_name}</strong>
                    <span>planned listen</span>
                    <strong>{haproxyDryRun.planned_listen_port}</strong>
                    <span>target</span>
                    <strong>{haproxyDryRun.landing_target_host}:{haproxyDryRun.landing_target_port}</strong>
                    <span>dry_run</span>
                    <strong>{String(haproxyDryRun.dry_run)}</strong>
                    <span>route_created</span>
                    <strong>{String(haproxyDryRun.route_created)}</strong>
                    <span>listener_bound</span>
                    <strong>{String(haproxyDryRun.listener_bound)}</strong>
                    <span>next stage</span>
                    <strong>{haproxyDryRun.next_stage}</strong>
                  </div>
                  <details className="node-create-safety-details">
                    <summary>dry-run 安全边界</summary>
                    <div className="node-create-safety-body">
                      {haproxyDryRun.safety_boundary.map((item) => (
                        <span key={item}>{item}</span>
                      ))}
                    </div>
                  </details>
                </div>
              ) : null}

              {haproxyDryRun ? (
                <div className="haproxy-final-approval-panel">
                  <div className="status-row">
                    <div>
                      <h3>HAProxy route 创建最终审批</h3>
                      <p className="message">
                        只生成最终审批包和 Go / No-Go 检查；不会创建 Worker command、HAProxy route、监听端口或客户端链接。
                      </p>
                    </div>
                    <button
                      className="secondary"
                      disabled={haproxyFinalApprovalLoading || haproxyFinalApprovalText.trim() !== HAPROXY_FINAL_APPROVAL_TEXT}
                      type="button"
                      onClick={() => void generateHaproxyFinalApproval()}
                    >
                      {haproxyFinalApprovalLoading ? "生成中" : "生成 HAProxy route 最终审批包"}
                    </button>
                  </div>

                  <div className="haproxy-readiness-grid">
                    <span>dry-run command</span>
                    <strong>{haproxyDryRun.command.id}</strong>
                    <span>planned service</span>
                    <strong>{haproxyDryRun.planned_service_name}</strong>
                    <span>planned listen</span>
                    <strong>{haproxyDryRun.planned_listen_port}</strong>
                    <span>target</span>
                    <strong>{haproxyDryRun.landing_target_host}:{haproxyDryRun.landing_target_port}</strong>
                    <span>route name</span>
                    <strong>{haproxyDryRun.route_name}</strong>
                    <span>Worker</span>
                    <strong>
                      {displayStatusLabel(selectedResource?.worker_display_status ?? selectedResource?.worker_status)} / {displayValue(selectedResource?.worker_version)} / {displayValue(selectedResource?.worker_interface_name)}
                    </strong>
                  </div>

                  <label className="wide-field">
                    最终审批确认文本
                    <input
                      placeholder={HAPROXY_FINAL_APPROVAL_TEXT}
                      value={haproxyFinalApprovalText}
                      onChange={(event) => setHaproxyFinalApprovalText(event.target.value)}
                    />
                    <span className="field-hint">
                      请输入 {HAPROXY_FINAL_APPROVAL_TEXT}。这只生成审批包，不执行真实创建。
                    </span>
                  </label>

                  {haproxyFinalApproval ? (
                    <div className={`haproxy-readiness-result ${haproxyFinalApproval.ready_for_real_create ? "ready" : "blocked"}`}>
                      <strong>
                        ready_for_real_create: {String(haproxyFinalApproval.ready_for_real_create)} / blocked: {String(haproxyFinalApproval.blocked)}
                      </strong>
                      <span>{haproxyFinalApproval.next_action}</span>
                      <div className="haproxy-readiness-grid">
                        <span>next stage</span>
                        <strong>{haproxyFinalApproval.next_stage}</strong>
                        <span>Worker command</span>
                        <strong>{String(haproxyFinalApproval.worker_command_created)}</strong>
                        <span>route_created</span>
                        <strong>{String(haproxyFinalApproval.route_created)}</strong>
                        <span>listener_bound</span>
                        <strong>{String(haproxyFinalApproval.listener_bound)}</strong>
                        <span>cutover</span>
                        <strong>{String(haproxyFinalApproval.cutover)}</strong>
                      </div>
                      <div className="haproxy-readiness-checks">
                        {haproxyFinalApproval.checks.map((check) => (
                          <div className="haproxy-readiness-check" key={check.id}>
                            <span className={`pill ${check.passed ? "ok" : "warn"}`}>{check.passed ? "通过" : "阻塞"}</span>
                            <strong>{check.label}</strong>
                            <span>{check.message}</span>
                            {!check.passed ? <small>{check.next_action}</small> : null}
                          </div>
                        ))}
                      </div>
                      <details className="node-create-safety-details">
                        <summary>最终审批安全边界</summary>
                        <div className="node-create-safety-body">
                          {haproxyFinalApproval.safety_boundary.map((item) => (
                            <span key={item}>{item}</span>
                          ))}
                        </div>
                      </details>
                    </div>
                  ) : null}

                  {haproxyFinalApproval?.ready_for_real_create ? (
                    <div className="haproxy-final-approval-panel">
                      <div className="status-row">
                        <div>
                          <h3>Stage 3.3.139：真实创建 HAProxy TCP route</h3>
                          <p className="message">
                            最终确认后只创建一个受控 Worker command；Worker 成功回传后才会写入 TransitRoute。不会生成客户端链接、不会 cutover、不会修改 share_link。
                          </p>
                        </div>
                        <button
                          className="danger"
                          disabled={haproxyRealExecutionLoading || haproxyRealExecutionText.trim() !== HAPROXY_REAL_EXECUTION_TEXT}
                          type="button"
                          onClick={() => void createHaproxyRealExecutionCommand()}
                        >
                          {haproxyRealExecutionLoading ? "创建中" : "创建真实 HAProxy TCP route"}
                        </button>
                      </div>

                      <div className="haproxy-readiness-grid">
                        <span>dry-run command</span>
                        <strong>{haproxyFinalApproval.dry_run_command_id}</strong>
                        <span>planned service</span>
                        <strong>{haproxyFinalApproval.planned_service_name}</strong>
                        <span>listen</span>
                        <strong>{displayValue(selectedResource?.entry_host)}:{haproxyFinalApproval.planned_listen_port}</strong>
                        <span>target</span>
                        <strong>{haproxyFinalApproval.landing_target_host}:{haproxyFinalApproval.landing_target_port}</strong>
                        <span>worker version</span>
                        <strong>{displayValue(haproxyFinalApproval.target_worker_version)}</strong>
                      </div>

                      <div className="haproxy-readiness-warning">
                        <strong>真实执行前确认</strong>
                        <span>已人工确认云安全组、云防火墙、服务器本机防火墙均放行监听 TCP 端口。</span>
                        <span>本阶段不读取 / 输出完整 nodes.share_link，不写 transit_routes.share_link，不生成完整客户端链接，不 cutover。</span>
                      </div>

                      <label className="wide-field">
                        真实执行确认文本
                        <input
                          placeholder={HAPROXY_REAL_EXECUTION_TEXT}
                          value={haproxyRealExecutionText}
                          onChange={(event) => setHaproxyRealExecutionText(event.target.value)}
                        />
                        <span className="field-hint">
                          请输入 {HAPROXY_REAL_EXECUTION_TEXT}。这会创建一个真实执行 Worker command，但本页面不会直接执行远程命令。
                        </span>
                      </label>

                      {haproxyRealExecution ? (
                        <div className={`haproxy-readiness-result ${haproxyRealExecution.blocked ? "blocked" : "ready"}`}>
                          <strong>
                            worker_command_created: {String(haproxyRealExecution.worker_command_created)} / blocked: {String(haproxyRealExecution.blocked)}
                          </strong>
                          <span>{haproxyRealExecution.next_action}</span>
                          <div className="haproxy-readiness-grid">
                            <span>command</span>
                            <strong>{haproxyRealExecution.command?.id ?? "not_created"}</strong>
                            <span>route_created</span>
                            <strong>{String(haproxyRealExecution.route_created)}</strong>
                            <span>listener_bound</span>
                            <strong>{String(haproxyRealExecution.listener_bound)}</strong>
                            <span>cutover</span>
                            <strong>{String(haproxyRealExecution.cutover)}</strong>
                          </div>
                          <div className="haproxy-readiness-checks">
                            {haproxyRealExecution.checks.map((check) => (
                              <div className="haproxy-readiness-check" key={check.id}>
                                <span className={`pill ${check.passed ? "ok" : "warn"}`}>{check.passed ? "通过" : "阻塞"}</span>
                                <strong>{check.label}</strong>
                                <span>{check.message}</span>
                                {!check.passed ? <small>{check.next_action}</small> : null}
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : null}

                      <p className="message">{haproxyRealExecutionMessage}</p>
                    </div>
                  ) : (
                    <div className="haproxy-disabled-actions">
                      <strong>Stage 3.3.139 真实创建未就绪</strong>
                      <span>只有 final approval 返回 ready_for_real_create=true 后，才允许创建真实执行 Worker command。</span>
                      <button className="secondary compact" disabled type="button">
                        等待 final approval 通过
                      </button>
                    </div>
                  )}

                  <p className="message">{haproxyFinalApprovalMessage}</p>
                </div>
              ) : null}

              {!haproxyFinalApproval?.ready_for_real_create ? (
                <div className="haproxy-disabled-actions">
                  <strong>真实执行未启用</strong>
                  <span>需要先完成 Stage 3.3.137 dry-run 和 Stage 3.3.138 final approval。</span>
                  <button className="secondary compact" disabled type="button">
                    Stage 3.3.138 final approval 后再启用
                  </button>
                </div>
              ) : null}

              <p className="message">{haproxyDryRunMessage}</p>
            </div>

            <p className="message">{haproxyReadinessMessage}</p>
          </div>

          <div className="status-row">
            <div>
              <h3>Worker 创建路径 dry-run</h3>
              <p className="message">仅创建 approval-required 的 dry-run Worker command；不会创建 systemd service、不会监听端口。</p>
            </div>
            <button className="secondary" disabled={workerCreateLoading} type="button" onClick={() => void createWorkerDryRunPlan()}>
              {workerCreateLoading ? "创建中" : "生成 dry-run 创建计划"}
            </button>
          </div>
          {workerCreatePlan ? (
            <div className="warning-box">
              <strong>dry-run 已创建</strong>
              <span>command：{workerCreatePlan.command.id}</span>
              <span>planned service：{workerCreatePlan.planned_service_name}</span>
              <span>listen：{workerCreatePlan.planned_listen_port}</span>
              <span>target：{workerCreatePlan.landing_target_host}:{workerCreatePlan.landing_target_port}</span>
              <span>dry_run：{String(workerCreatePlan.dry_run)}</span>
            </div>
          ) : null}
        </div>
      </details>

      <p className="message">{message}</p>

      {deleteRoute ? (
        <SafeDeleteModal
          title="远程清理删除中转链路"
          targetLabel={`${deleteRoute.name} / ${routeEntry(deleteRoute)} -> ${deleteRoute.target_host}:${deleteRoute.target_port}`}
          mode={deleteRouteMode}
          confirmText={deleteRouteConfirmText}
          requiredConfirmTextOverride={transitRouteDeleteConfirmText(deleteRoute, deleteRouteMode)}
          remoteConfirmButtonLabel="确认远程清理删除"
          offlineConfirmButtonLabel="确认离线本地移除"
          submitting={candidateLoading}
          onCancel={closeDeleteRouteModal}
          onConfirmTextChange={setDeleteRouteConfirmText}
          onConfirm={() => void submitDeleteRoute()}
          description={
            isHaproxyForwardingMethod(deleteRoute.forwarding_method) ? (
              <>
                这是远程清理删除，会影响当前中转入口 {routeEntry(deleteRoute)}。成功后 {deleteRoute.listen_port} 将不再监听，
                当前经中转访问的客户端链接会失效。系统会创建受控 Worker cleanup command，停止远程 HAProxy service，删除 systemd unit 和 HAProxy route config。
                清理成功后，中转链路记录会被软删除。不会修改防火墙、云安全组、云防火墙，也不会 cutover。
              </>
            ) : (
              <>
                这是远程清理删除，会影响当前中转入口 {routeEntry(deleteRoute)}。成功后 {deleteRoute.listen_port} 将不再监听。
                系统会创建受控 Worker cleanup command，远程清理该中转链路对应的中转服务。清理成功后，中转链路记录会被软删除。
                不会修改防火墙、云安全组、云防火墙，也不会 cutover。
              </>
            )
          }
          offlineDescription={
            isHaproxyForwardingMethod(deleteRoute.forwarding_method) ? (
              <>
                <span>当前资源对应的 Worker 离线，系统无法远程清理该服务器上的 HAProxy service 或配置文件。</span>
                <span>离线本地移除只修改本地数据库记录，不会连接远程服务器，不会停止远程 HAProxy service，不会删除 HAProxy 配置，也不会释放监听端口。</span>
                <span>如果远程服务仍在运行，本地移除后页面将看不到这条链路，但远程 {deleteRoute.listen_port} 可能仍然在监听。之后不能盲目重新创建同端口，必须先做远程只读核对。</span>
              </>
            ) : (
              <>
                <span>当前资源对应的 Worker 离线，系统无法远程清理该服务器上的中转服务。</span>
                <span>离线本地移除只修改本地数据库记录，不会连接远程服务器，不会停止远程服务，不会释放监听端口，不会修改防火墙，不会 cutover。</span>
                <span>如果远程服务仍在运行，本地移除后页面将看不到这条链路，但远程端口可能仍然在监听。之后不能盲目重新创建同端口，必须先做远程只读核对。</span>
              </>
            )
          }
        />
      ) : null}

      {candidateExportModalOpen ? (
        <div className="modal-backdrop">
          <div className="modal-card transit-route-export-modal transit-export-modal">
            <div className="modal-header">
              <div>
                <h3>临时导出客户端链接</h3>
                <p className="message">基于当前落地节点配置临时生成经中转访问的客户端链接。此操作不会保存到数据库，不会覆盖原节点链接，也不会切换正式线路。</p>
              </div>
              <button className="secondary" type="button" onClick={closeCandidateExportModal}>
                关闭
              </button>
            </div>

            {candidateExportRoute ? (
              <div className="transit-export-route-context">
                <span>链路</span>
                <strong>{candidateExportRoute.name}</strong>
                <span>入口</span>
                <strong>{routeEntry(candidateExportRoute)}</strong>
                <span>目标</span>
                <strong>{candidateExportRoute.target_host}:{candidateExportRoute.target_port}</strong>
              </div>
            ) : (
              <p className="message">未选择中转链路。</p>
            )}

            <div className="transit-export-safety-notice">
              <strong>安全说明</strong>
              <span>这是临时链接，仅用于复制测试；刷新页面后不会作为正式 share_link 保存。</span>
              <span>不会写入 `transit_routes.share_link`。</span>
              <span>不会修改或覆盖 `nodes.share_link`。</span>
              <span>不会创建、删除或修改中转链路。</span>
              <span>不会触发 Worker command，不会 cutover。</span>
              <span>原直连节点仍保留。</span>
            </div>

            {candidateExport ? (
              <div className="candidate-export-result transit-export-result">
                <strong>临时客户端链接已生成</strong>
                <span>名称：{candidateExport.candidate_name}</span>
                <span>服务器：{candidateExport.server}</span>
                <span>端口：{candidateExport.port}</span>
                <span>协议：{candidateExport.protocol} / {candidateExport.security} / {candidateExport.network}</span>
                <span>保存状态：未写入数据库 / 未切换正式线路</span>
                <span>masked link：{candidateExport.masked_candidate_link}</span>
                <button
                  className="secondary"
                  type="button"
                  onClick={async () => {
                    try {
                      await copyText(candidateExport.candidate_link);
                      setCandidateCopyFallbackRequired(false);
                      setCandidateMessage("临时链接已复制。请妥善保存，仅用于手动导入测试，不要公开分享。");
                    } catch {
                      setCandidateCopyFallbackRequired(true);
                      setCandidateMessage("当前 HTTP 环境不支持自动复制，请使用下方文本框手动复制。");
                    }
                  }}
                >
                  复制临时链接
                </button>
                {candidateCopyFallbackRequired ? (
                  <label className="candidate-manual-copy transit-export-manual-copy">
                    手动复制临时链接
                    <textarea
                      readOnly
                      value={candidateExport.candidate_link}
                      onClick={(event) => event.currentTarget.select()}
                      onFocus={(event) => event.currentTarget.select()}
                    />
                  </label>
                ) : null}
                <p className="message">只用于手动导入测试；没有写入 `transit_routes.share_link`，没有覆盖 `nodes.share_link`，也没有 cutover。</p>
              </div>
            ) : null}

            <p className="message">{candidateMessage}</p>

            <div className="modal-actions">
              <button className="secondary" type="button" onClick={closeCandidateExportModal}>
                {candidateExport ? "关闭" : "取消"}
              </button>
              <button disabled={candidateLoading || !candidateExportRoute} type="button" onClick={() => void exportCandidateConfig(candidateExportRouteId)}>
                {candidateLoading ? "生成中" : candidateExport ? "重新生成" : "生成临时链接"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {createModalOpen ? (
        <div className="modal-backdrop">
          <div className="modal-card node-create-modal transit-route-create-modal">
            <div className="modal-header node-create-modal-header">
              <div>
                <h3>创建中转链路</h3>
                <p className="message">
                  填写必要信息后点击创建。系统会自动预检、创建中转转发服务、检查监听和落地连通性，成功后生成可用 V2Ray
                  链接和二维码。
                </p>
              </div>
              <button className="ghost-button" type="button" aria-label="关闭创建中转链路弹窗" onClick={() => void closeCreateRouteModal(false)}>
                ×
              </button>
            </div>

            <div className="node-create-modal-body">
              <form
                className="form server-modal-form node-create-form transit-route-create-form"
                id="transit-route-create-form"
                onSubmit={(event) => void submitSimplifiedTransitRouteCreate(event)}
              >
                <div className="worker-bootstrap-intro wide-field">
                  <strong>创建中转链路</strong>
                  <span>
                    中转客户端链接基于落地直连节点链接生成，只替换服务器地址和端口；不会修改 nodes.share_link，不会写入
                    transit_routes.share_link，不会 cutover。
                  </span>
                  <span>当前真实创建仍走后端受保护审批校验；参数不匹配时会被后端拒绝。</span>
                </div>

                <label>
                  链路名称
                  <input
                    value={createForm.routeName}
                    onChange={(event) => setCreateForm({ ...createForm, routeName: event.target.value })}
                    placeholder={approvedTransitRouteName}
                  />
                </label>
                <label>
                  中转服务器
                  <select value={createResource?.id ?? ""} onChange={(event) => setCreateForm({ ...createForm, transitResourceId: event.target.value })}>
                    {selectableResources.length === 0 ? <option value="">暂无可用中转服务器</option> : null}
                    {selectableResources.map((resource) => (
                      <option key={resource.id} value={resource.id}>
                        {resource.name} / {displayValue(resource.entry_host)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  落地节点 / 落地服务器
                  <select value={createNode?.id ?? ""} onChange={(event) => setCreateForm({ ...createForm, landingNodeId: event.target.value })}>
                    {activeNodes.length === 0 ? <option value="">暂无 active 落地节点</option> : null}
                    {activeNodes.map((node) => (
                      <option key={node.id} value={node.id}>
                        {node.node_name} / {displayValue(node.vps_ip)}:{displayValue(node.port)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  中转监听端口
                  <input
                    inputMode="numeric"
                    value={createForm.listenPort}
                    onChange={(event) => {
                      const nextListenPort = event.target.value;
                      setCreateForm((current) => {
                        const previousDefaultName = defaultTransitRouteName(current.forwardingMethod, current.listenPort);
                        const nextDefaultName = defaultTransitRouteName(current.forwardingMethod, nextListenPort);
                        return {
                          ...current,
                          listenPort: nextListenPort,
                          routeName: current.routeName === previousDefaultName ? nextDefaultName : current.routeName,
                        };
                      });
                    }}
                    placeholder={String(approvedTransitListenPort)}
                  />
                  <small>新增或变更中转监听端口时，必须自行确认云安全组 / 云防火墙 / 服务器本机防火墙已放行对应 TCP 端口。</small>
                  {createPortConflictMessage ? <small className="form-field-error">{createPortConflictMessage}</small> : null}
                </label>
                <label>
                  转发方式
                  <select
                    value={createForm.forwardingMethod}
                    onChange={(event) => {
                      const nextMethod = event.target.value as TransitCreateForwardingMethod;
                      setCreateForm((current) => ({
                        ...current,
                        forwardingMethod: nextMethod,
                        routeName: defaultTransitRouteName(nextMethod, current.listenPort),
                      }));
                    }}
                  >
                    <option value="socat">socat</option>
                    <option value="haproxy_tcp">HAProxy TCP mode</option>
                  </select>
                </label>

                {createForm.forwardingMethod === "haproxy_tcp" ? (
                  <div className="warning-box wide-field">
                    <strong>HAProxy TCP mode 安全提醒</strong>
                    <span>中转 VPS 必须已安装 HAProxy。</span>
                    <span>HAProxy TCP mode 会创建 liveline-haproxy-&lt;port&gt;.service。</span>
                    <span>新监听端口必须已在云安全组、云防火墙、服务器本机防火墙放行。</span>
                    <span>当前页面不会自动安装 HAProxy，不会修改防火墙，不会 cutover。</span>
                  </div>
                ) : null}

                <label className="node-create-confirm wide-field">
                  <input
                    type="checkbox"
                    checked={createForm.firewallConfirmed}
                    onChange={(event) => setCreateForm({ ...createForm, firewallConfirmed: event.target.checked })}
                  />
                  <span>
                    我已确认该中转监听 TCP 端口已在云安全组、云防火墙和服务器本机防火墙放行，并理解创建成功后会生成可用客户端链接。
                  </span>
                </label>

                <details className="node-create-safety-details wide-field">
                  <summary>高级安全说明</summary>
                  <div className="node-create-safety-body">
                    <span>创建命令只通过 transit Worker allowlist 执行固定 LiveLine-owned service 模板，不接受任意 shell 或任意 systemd unit。</span>
                    <span>成功条件包括 systemd service active、监听端口 LISTEN、以及中转服务器到落地目标端口连通。</span>
                    <span>失败时不会生成完整客户端链接，不写 transit_routes.share_link，不修改落地节点，不 cutover。</span>
                    <span>本页面不会自动修改防火墙、云安全组或云防火墙；端口放行仍由用户自行确认。</span>
                  </div>
                </details>

                {createStep !== "idle" ? (
                  <div className="landing-plan-result node-create-result wide-field">
                    <div className={`plan-status-card ${createStep === "failed" ? "blocked" : createStep === "complete" ? "ready" : ""}`}>
                      <strong>{transitRouteCreateProgressLabel(createStep, createForm.forwardingMethod)}</strong>
                      <span>系统会先做只读预检，再创建中转命令。只有创建、监听和连通性检查成功后，才会临时导出客户端链接。</span>
                    </div>

                    {createStep !== "failed" ? (
                      <div className="node-create-progress" aria-label="中转链路创建进度">
                        {(["preflight_create", "preflight_running", "command_create", "command_running", "refresh", "export_link", "complete"] as TransitRouteCreateStep[]).map(
                          (step, index, steps) => {
                            const currentIndex = steps.indexOf(createStep);
                            return (
                              <span className={index < currentIndex ? "done" : index === currentIndex ? "current" : ""} key={step}>
                                {transitRouteCreateProgressLabel(step, createForm.forwardingMethod)}
                              </span>
                            );
                          },
                        )}
                      </div>
                    ) : null}

                    {createCommand ? (
                      <div className="worker-command-panel">
                        <strong>当前 Worker 命令</strong>
                        <span>命令 ID：{createCommand.id}</span>
                        <span>类型：{createCommand.command_type}</span>
                        <span>状态：{displayStatusLabel(createCommand.status)}</span>
                        {createCommand.result_summary ? <span>{createCommand.result_summary}</span> : null}
                        {createCommand.error_message ? <span>{createCommand.error_message}</span> : null}
                      </div>
                    ) : null}

                    {createExecuteResult ? (
                      <div className="worker-command-panel">
                        <strong>创建命令已提交</strong>
                        <span>目标 Worker：{createExecuteResult.target_worker_id}</span>
                        <span>Worker 版本：{createExecuteResult.target_worker_version || "未返回"}</span>
                        <span>执行模式：{createExecuteResult.execution_mode}</span>
                      </div>
                    ) : null}

                    {createError ? (
                      <div className="failure-box">
                        <strong>创建未完成</strong>
                        <span>{createError}</span>
                        <span>请检查中转端口放行、Worker 在线状态、落地端口连通性，或确认本次参数仍匹配受保护审批记录。</span>
                        <span>失败时不会写入 transit_routes.share_link，不会 cutover，也不会显示完整客户端链接。</span>
                      </div>
                    ) : null}

                    {createdRoute && createExport ? (
                      <div className="node-create-success-card">
                        <strong>中转链路已创建，可导入客户端</strong>
                        <div className="landing-plan-grid">
                          <span>链路名称</span>
                          <strong>{createdRoute.name}</strong>
                          <span>中转入口</span>
                          <strong>{createExport.server}:{createExport.port}</strong>
                          <span>目标落地</span>
                          <strong>{createdRoute.target_host}:{createdRoute.target_port}</strong>
                          <span>协议</span>
                          <strong>{createExport.protocol} / {createExport.security} / {createExport.network}</strong>
                        </div>
                        <div className="modal-actions">
                          <button
                            className="secondary"
                            type="button"
                            onClick={async () => {
                              try {
                                await copyText(createExport.candidate_link);
                                setCreateCopyFallbackRequired(false);
                                setMessage("中转客户端链接已复制。请妥善保存，仅自己使用。");
                              } catch {
                                setCreateCopyFallbackRequired(true);
                                setMessage("当前 HTTP 环境不支持自动复制，请使用下方文本框手动复制。");
                              }
                            }}
                          >
                            复制客户端链接
                          </button>
                          <button className="secondary" type="button" onClick={() => setCreateQrVisible(true)}>
                            临时二维码
                          </button>
                          {createQrVisible ? (
                            <button className="secondary" type="button" onClick={downloadCreateTransitQrCode}>
                              下载二维码
                            </button>
                          ) : null}
                        </div>
                        {createCopyFallbackRequired ? (
                          <label className="candidate-manual-copy transit-export-manual-copy">
                            手动复制完整客户端链接
                            <textarea
                              readOnly
                              value={createExport.candidate_link}
                              onClick={(event) => event.currentTarget.select()}
                              onFocus={(event) => event.currentTarget.select()}
                            />
                          </label>
                        ) : null}
                        {createQrVisible ? (
                          <div className="qr-panel">
                            <div className="qr-frame" ref={createQrFrameRef} aria-label="中转客户端链接二维码">
                              <QRCode value={createExport.candidate_link} size={220} />
                            </div>
                            <small>二维码等同完整客户端链接，仅自己使用，不要写入聊天、日志、README、PR 或文档。</small>
                          </div>
                        ) : null}
                        <small>Shadowrocket / V2RayN / V2RayNG 可通过完整链接或二维码导入。不会写入 nodes.share_link 或 transit_routes.share_link。</small>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </form>
            </div>

            {createStep === "complete" ? (
              <div className="modal-actions node-create-modal-footer">
                <button className="success-button" type="button" onClick={() => void closeCreateRouteModal(true)}>
                  完成并关闭
                </button>
              </div>
            ) : createStep === "failed" ? (
              <div className="modal-actions node-create-modal-footer">
                <button className="secondary" type="button" onClick={() => void closeCreateRouteModal(false)}>
                  关闭
                </button>
                <button disabled={!createReady} form="transit-route-create-form" type="submit">
                  重新尝试
                </button>
              </div>
            ) : (
              <div className="modal-actions node-create-modal-footer">
                <button className="secondary" type="button" onClick={() => void closeCreateRouteModal(false)}>
                  取消
                </button>
                <button disabled={!createReady} form="transit-route-create-form" type="submit">
                  {createStep === "idle" ? "创建中转链路" : "创建中..."}
                </button>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}
