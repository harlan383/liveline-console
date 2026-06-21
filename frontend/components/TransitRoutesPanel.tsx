"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import QRCode from "react-qr-code";

import { TransitReadonlyPreflightSimplePanel } from "@/components/TransitReadonlyPreflightSimplePanel";
import {
  apiFetch,
  createTransitRouteWorkerExecuteCommand,
  createTransitReadonlyPreflightCommand,
  createTransitWorkerBootstrap,
  createWorkerCommand,
  exportTransitRouteCandidate,
  getWorkerCommand,
  getTransitRouteCandidateSummary,
  listWorkerCommands,
  regenerateTransitWorkerBootstrap,
  remoteCleanupDeleteTransitResource,
  remoteCleanupDeleteTransitRoute,
  requestReadonlyPreflightPlan,
  type CsrfResult,
  type NodeData,
  type NodeListResult,
  type ReadonlyPreflightPlanRequest,
  type ReadonlyPreflightPlanResponse,
  type TransitRouteCandidateExportResult,
  type TransitRouteCandidateSummary,
  type TransitReadonlyPreflightCommandRequest,
  type TransitResourceData,
  type TransitResourceListResult,
  type TransitRouteWorkerCreateExecuteResponse,
  type TransitRouteData,
  type TransitRouteListResult,
  type WorkerCommandData,
  type WorkerTokenCreateResult,
} from "@/lib/api";

type ForwardingMethod = "socat" | "gost";

type TransitWorkerBootstrapFormState = {
  name: string;
  ip: string;
  expiresInMinutes: string;
};

type TransitRouteDraftState = {
  transitResourceId: string;
  landingNodeId: string;
  plannedListenPort: string;
  forwardingMethod: ForwardingMethod;
  purpose: string;
};

type TransitRouteCreateFormState = {
  routeName: string;
  transitResourceId: string;
  landingNodeId: string;
  listenPort: string;
  forwardingMethod: "socat";
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

function SafeDeleteModal({
  title,
  description,
  targetLabel,
  confirmText,
  submitting,
  onCancel,
  onConfirmTextChange,
  onConfirm,
}: {
  title: string;
  description: ReactNode;
  targetLabel: string;
  confirmText: string;
  submitting: boolean;
  onCancel: () => void;
  onConfirmTextChange: (value: string) => void;
  onConfirm: () => void;
}) {
  return (
    <div className="modal-backdrop" role="presentation">
      <div className="modal-card safe-delete-modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button className="ghost-button" type="button" onClick={onCancel}>
            取消
          </button>
        </div>
        <div className="failure-box safe-delete-warning">
          <strong>真实远程清理</strong>
          <span>{description}</span>
        </div>
        <div className="server-delete-target">{targetLabel}</div>
        <label className="safe-delete-input">
          输入 CONFIRM_REMOTE_DELETE 后才能创建远程清理任务
          <input value={confirmText} onChange={(event) => onConfirmTextChange(event.target.value)} placeholder="CONFIRM_REMOTE_DELETE" />
        </label>
        <div className="modal-actions">
          <button className="secondary" type="button" onClick={onCancel}>
            取消
          </button>
          <button className="danger" disabled={submitting || confirmText !== "CONFIRM_REMOTE_DELETE"} type="button" onClick={onConfirm}>
            确认远程清理并删除
          </button>
        </div>
      </div>
    </div>
  );
}

const emptyBootstrapForm: TransitWorkerBootstrapFormState = {
  name: "",
  ip: "",
  expiresInMinutes: "60",
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

const emptyRouteCreateForm: TransitRouteCreateFormState = {
  routeName: approvedTransitRouteName,
  transitResourceId: "",
  landingNodeId: "",
  listenPort: String(approvedTransitListenPort),
  forwardingMethod: "socat",
  firewallConfirmed: false,
};

const approvedCandidateRouteId = "d10d3dcc-679f-4f85-ae37-9e5dfa37e6af";

function statusClass(status: string) {
  if (["active", "online", "worker_online", "succeeded", "success", "passed"].includes(status)) {
    return "ok";
  }
  if (["failed", "error", "deleted", "offline"].includes(status)) {
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
    offline: "离线",
    unchecked: "未检测",
    creating: "创建中",
    error: "异常",
    deleted: "已删除",
    succeeded: "成功",
    failed: "失败",
    running: "执行中",
    pending: "等待中",
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
  const [message, setMessage] = useState("中转服务器页面只管理 Worker 接入资源；不会执行旧 SSH/RQ 检测或安装。");
  const [modalMode, setModalMode] = useState<"add" | "edit" | "install" | "delete" | null>(null);
  const [selectedResource, setSelectedResource] = useState<TransitResourceData | null>(null);
  const [bootstrapForm, setBootstrapForm] = useState<TransitWorkerBootstrapFormState>(emptyBootstrapForm);
  const [workerTokenResult, setWorkerTokenResult] = useState<WorkerTokenCreateResult | null>(null);
  const [workerCommandsByWorkerId, setWorkerCommandsByWorkerId] = useState<Record<string, WorkerCommandData[]>>({});
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
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

  useEffect(() => {
    void loadResources();
  }, []);

  function closeModal() {
    setModalMode(null);
    setSelectedResource(null);
    setBootstrapForm(emptyBootstrapForm);
    setWorkerTokenResult(null);
    setDeleteConfirmText("");
  }

  function openAdd() {
    setSelectedResource(null);
    setBootstrapForm(emptyBootstrapForm);
    setWorkerTokenResult(null);
    setModalMode("add");
  }

  function openEdit(resource: TransitResourceData) {
    setSelectedResource(resource);
    setBootstrapForm({
      name: resource.name,
      ip: resource.entry_host ?? "",
      expiresInMinutes: "60",
    });
    setModalMode("edit");
  }

  function openInstallCommand(resource: TransitResourceData) {
    setSelectedResource(resource);
    setBootstrapForm({
      name: resource.name,
      ip: resource.entry_host ?? "",
      expiresInMinutes: "60",
    });
    setWorkerTokenResult(null);
    setModalMode("install");
  }

  function openDeleteResource(resource: TransitResourceData) {
    setSelectedResource(resource);
    setDeleteConfirmText("");
    setModalMode("delete");
  }

  async function submitWorkerBootstrap(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = bootstrapForm.name.trim();
    const ip = bootstrapForm.ip.trim();
    const expiresInMinutes = Number(bootstrapForm.expiresInMinutes);
    if (!name || !ip) {
      setMessage("请填写中转服务器名称和 IP。");
      return;
    }
    if (!Number.isInteger(expiresInMinutes) || expiresInMinutes < 1 || expiresInMinutes > 10080) {
      setMessage("过期时间必须是 1 到 10080 分钟。");
      return;
    }

    setSubmitting(true);
    try {
      const csrfToken = await ensureCsrfToken();
      const result =
        modalMode === "install" && selectedResource
          ? await regenerateTransitWorkerBootstrap(selectedResource.id, { expires_in_minutes: expiresInMinutes }, csrfToken)
          : await createTransitWorkerBootstrap({ name, ip, expires_in_minutes: expiresInMinutes }, csrfToken);
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setWorkerTokenResult(result.data.token);
      setMessage("一次性 Worker 安装命令已生成。命令只显示一次，请立即复制并妥善保存。");
      await loadResources();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "生成 Worker 安装命令失败。");
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
      const result = await apiFetch<TransitResourceData>(`/api/transit-resources/${selectedResource.id}`, {
        method: "PATCH",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify({
          name: bootstrapForm.name,
          entry_host: bootstrapForm.ip,
          entry_port: selectedResource.entry_port,
          resource_type: "server",
          protocol_hint: "tcp",
          has_ssh: false,
          ssh_host: null,
          ssh_port: null,
          ssh_username: null,
          status: selectedResource.status,
        }),
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
    if (!selectedResource || deleteConfirmText !== "CONFIRM_REMOTE_DELETE") {
      return;
    }
    setSubmitting(true);
    setMessage("正在创建中转服务器远程清理任务；清理成功后才会软删除系统记录。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await remoteCleanupDeleteTransitResource(selectedResource.id, csrfToken);
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setMessage(`清理任务已创建：${result.data.command_id}。等待 Worker 执行；远程清理成功后将软删除系统记录。`);
      closeModal();
      await loadResources();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "删除中转服务器失败。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel wide">
      <div className="status-row">
        <div>
          <h2>中转服务器</h2>
          <p className="message">管理中转服务器及其 Worker 接入状态；资源记录不等于真实线路。</p>
        </div>
        <button type="button" onClick={openAdd}>
          添加中转服务器
        </button>
      </div>

      <details className="warning-box collapsible-notice">
        <summary className="collapsible-summary">
          <strong>查看中转服务器安全说明</strong>
          <span className="notice-toggle-text">
            <span className="when-closed">查看说明</span>
            <span className="when-open">收起说明</span>
          </span>
        </summary>
        <div className="route-safety-body">
          <ul className="route-safety-list">
            <li>本页只保留 Worker 接入、心跳、状态检查和本地资源记录。</li>
            <li>旧 SSH/RQ 读取、安装 gost、安装 socat 入口已经下线。</li>
            <li>添加或重新生成安装命令不会自动安装 Worker；真实安装仍需用户手动在目标服务器执行。</li>
            <li>不会创建中转链路、不会新增监听端口、不会修改防火墙或 cutover。</li>
          </ul>
        </div>
      </details>

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
              const canRegenerate = resource.status === "pending_worker" && !resource.worker_online;
              return (
                <div className="server-table-group" key={resource.id}>
                  <div className="server-table-row">
                    <strong>{resource.name}</strong>
                    <span>{resource.entry_host ?? "-"}</span>
                    <span>Worker 接入</span>
                    <span className={`pill ${statusClass(resource.display_status)}`}>
                      {displayStatusLabel(resource.display_status)}
                    </span>
                    <div className="server-actions">
                      {canRegenerate ? (
                        <button className="secondary" type="button" onClick={() => openInstallCommand(resource)}>
                          重新生成安装命令
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
                    Worker：{resource.worker_status ? displayStatusLabel(resource.worker_status) : "未注册"}；主机名：
                    {resource.worker_hostname || "暂无"}；网卡：{resource.worker_interface_name || "暂无"}；版本：
                    {resource.worker_version || "暂无"}；最后心跳：{formatTime(resource.worker_last_heartbeat_at)}
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
          confirmText={deleteConfirmText}
          submitting={submitting}
          onCancel={closeModal}
          onConfirmTextChange={setDeleteConfirmText}
          onConfirm={() => void submitDeleteResource()}
          description={
            <>
              这会真实清理该中转服务器下所有中转链路的 socat 服务，并清理 transit Worker。该中转服务器将不再被 LiveLine Console 纳管。
              清理成功后，中转链路记录和中转服务器记录会被软删除。不会修改防火墙、云安全组或云防火墙。
            </>
          }
        />
      ) : null}

      {modalMode && modalMode !== "delete" ? (
        <div className="modal-backdrop" role="presentation">
          <div className="modal-card" role="dialog" aria-modal="true" aria-label="中转服务器操作">
            <div className="modal-header">
              <h3>{modalMode === "edit" ? "编辑中转服务器" : "添加中转服务器"}</h3>
              <button className="ghost-button" type="button" onClick={closeModal}>
                取消
              </button>
            </div>
            {modalMode === "edit" ? (
              <form className="form server-modal-form" onSubmit={(event) => void submitEdit(event)}>
                <label>
                  中转服务器名称
                  <input value={bootstrapForm.name} onChange={(event) => setBootstrapForm({ ...bootstrapForm, name: event.target.value })} />
                </label>
                <label>
                  中转服务器 IP
                  <input value={bootstrapForm.ip} onChange={(event) => setBootstrapForm({ ...bootstrapForm, ip: event.target.value })} />
                </label>
                <p className="message wide-field">编辑只更新本地资源记录；不会执行远程命令。</p>
                <div className="modal-actions wide-field">
                  <button disabled={submitting} type="submit">
                    保存
                  </button>
                  <button className="secondary" type="button" onClick={closeModal}>
                    取消
                  </button>
                </div>
              </form>
            ) : (
              <form className="form server-modal-form worker-bootstrap-form" onSubmit={(event) => void submitWorkerBootstrap(event)}>
                <div className="worker-bootstrap-intro wide-field">
                  <strong>接入方式：Worker 安装命令</strong>
                  <span>中转服务器使用 role = transit。当前不会执行远程安装，只生成一次性安装命令。</span>
                </div>
                <label>
                  中转服务器名称
                  <input value={bootstrapForm.name} onChange={(event) => setBootstrapForm({ ...bootstrapForm, name: event.target.value })} />
                </label>
                <label>
                  中转服务器 IP
                  <input value={bootstrapForm.ip} onChange={(event) => setBootstrapForm({ ...bootstrapForm, ip: event.target.value })} />
                </label>
                <label>
                  过期时间（分钟）
                  <input
                    inputMode="numeric"
                    value={bootstrapForm.expiresInMinutes}
                    onChange={(event) => setBootstrapForm({ ...bootstrapForm, expiresInMinutes: event.target.value })}
                  />
                </label>
                <div className="modal-actions wide-field">
                  <button disabled={submitting} type="submit">
                    生成安装命令
                  </button>
                  <button className="secondary" type="button" onClick={closeModal}>
                    取消
                  </button>
                </div>
                {workerTokenResult?.install_command ? (
                  <div className="wide-field">
                    <label>
                      安装命令
                      <textarea readOnly value={workerTokenResult.install_command} />
                    </label>
                    <button
                      className="secondary"
                      type="button"
                      onClick={() => {
                        void copyText(workerTokenResult.install_command)
                          .then(() => setMessage("安装命令已复制。请勿写入聊天、Git、README、PR 或日志。"))
                          .catch(() => setMessage("当前 HTTP 环境可能不支持自动复制，请手动复制上方安装命令。"));
                      }}
                    >
                      复制命令
                    </button>
                    <p className="message">命令只显示一次，关闭后无法再次查看；请在目标服务器上先确认能访问主控地址。</p>
                  </div>
                ) : null}
              </form>
            )}
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
  const approvedCandidateRoute = useMemo(
    () => routes.find((route) => route.id === approvedCandidateRouteId) ?? null,
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
  const createReady =
    Boolean(createForm.routeName.trim()) &&
    Boolean(createResource) &&
    Boolean(createNode) &&
    createListenPort !== null &&
    createTargetPort > 0 &&
    createForm.firewallConfirmed &&
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

  async function waitForTransitCommandCompletion(commandId: string, runningStep: TransitRouteCreateStep) {
    for (let attempt = 0; attempt < 90; attempt += 1) {
      const result = await getWorkerCommand(commandId);
      if (!result.success) {
        throw new Error(`${result.error_code}: ${result.message}`);
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
          route.forwarding_method === "socat" &&
          route.status === "active" &&
          !route.deleted_at,
      ) ?? null
    );
  }

  function friendlyTransitCreateError(error: unknown) {
    const raw = error instanceof Error ? error.message : String(error || "创建失败。");
    if (raw.includes("READONLY_PREFLIGHT") || raw.includes("preflight") || raw.includes("预检")) {
      return "只读预检未通过：请确认 Worker 在线、监听端口未占用、落地目标端口可达。";
    }
    if (raw.includes("TRANSIT_PORT_ALREADY_PLANNED") || raw.includes("LISTEN") || raw.includes("listen") || raw.includes("端口")) {
      return "中转监听端口不可用：端口可能已存在链路、未放行，或 Worker 未检测到监听成功。";
    }
    if (raw.includes("WORKER") || raw.includes("Worker")) {
      return "中转 Worker 不在线或版本不满足，请检查中转服务器 Worker 状态。";
    }
    if (raw.includes("APPROVAL") || raw.includes("MISMATCH") || raw.includes("审批")) {
      return "受保护创建审批未通过：当前真实创建仍要求匹配已审批的中转资源、落地节点、端口和线路名称。";
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
    setCreateStep("preflight_create");
    setCreateCommand(null);
    setCreateExecuteResult(null);
    setCreatedRoute(null);
    setCreateExport(null);
    setCreateError("");
    setCreateCopyFallbackRequired(false);
    setCreateQrVisible(false);
    setMessage("正在自动执行中转只读预检和受保护创建流程。成功后才会临时生成客户端链接和二维码。");

    try {
      const csrfToken = await ensureCsrfToken();
      const preflightResult = await createTransitReadonlyPreflightCommand(
        {
          transit_resource_id: createResource.id,
          landing_node_id: createNode.id,
          planned_listen_port: createListenPort,
          landing_target_port: createTargetPort,
          forwarding_method: "socat",
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
          forwarding_method: "socat",
          purpose: "直播",
          route_name: createForm.routeName.trim(),
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
    setCandidateMessage("临时导出只用于手动导入测试；不会写入数据库、修改 nodes.share_link 或 cutover。");
  }

  function openDeleteRoute(routeId: string) {
    setDeleteRouteId(routeId);
    setDeleteRouteConfirmText("");
    setMessage("删除中转链路只会删除系统记录；不会停止 socat 或关闭端口。");
  }

  function closeDeleteRouteModal() {
    setDeleteRouteId("");
    setDeleteRouteConfirmText("");
  }

  async function submitDeleteRoute() {
    if (!deleteRoute || deleteRouteConfirmText !== "CONFIRM_REMOTE_DELETE") {
      return;
    }
    setCandidateLoading(true);
    setMessage("正在创建中转链路远程清理任务；清理成功后才会软删除系统记录。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await remoteCleanupDeleteTransitRoute(deleteRoute.id, csrfToken);
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setMessage(`清理任务已创建：${result.data.command_id}。等待 Worker 执行；远程清理成功后将软删除系统记录。`);
      closeDeleteRouteModal();
      setCandidateSummary(null);
      setCandidateExport(null);
      await loadData();
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

  async function loadCandidateSummary(routeId = approvedCandidateRoute?.id ?? approvedCandidateRouteId) {
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
    setCandidateMessage("正在临时导出候选测试配置；不会写入数据库或执行 cutover。");
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
        setCandidateMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      const route = routes.find((item) => item.id === routeId) ?? approvedCandidateRoute ?? null;
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
      setCandidateMessage("候选测试配置已临时导出；完整链接仅保存在本次响应内，请只用于手动导入测试。");
    } catch (error) {
      setCandidateMessage(error instanceof Error ? error.message : "临时导出候选测试配置失败。");
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

  async function refreshRemoteCommand() {
    if (!remotePreflightCommand) {
      return;
    }
    const result = await apiFetch<WorkerCommandData>(`/api/workers/commands/${remotePreflightCommand.id}`);
    if (!result.success) {
      setRemotePreflightMessage(`${result.error_code}: ${result.message}`);
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
          <p className="message">管理中转服务器到落地节点的转发线路。日常使用只需要新增线路、查看状态、临时导出测试配置。</p>
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

      <details className="warning-box collapsible-notice">
        <summary className="collapsible-summary">
          <strong>查看中转链路安全边界</strong>
          <span className="notice-toggle-text">
            <span className="when-closed">查看说明</span>
            <span className="when-open">收起说明</span>
          </span>
        </summary>
        <div className="route-safety-body">
          <ul className="route-safety-list">
            <li>旧 POST /api/transit-routes SSH/RQ 创建入口已下线。</li>
            <li>远程只读预检只创建 transit_readonly_preflight Worker command。</li>
            <li>Worker create path 当前只允许 dry-run / approval-required，不创建真实监听。</li>
            <li>不会修改防火墙、Xray、nodes.share_link，不导出完整客户端链接，不 cutover。</li>
          </ul>
        </div>
      </details>

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
                    <span>{route.forwarding_method}</span>
                    <span title={route.status}>
                      <span className={`pill ${statusClass(route.status)}`}>{displayStatusLabel(route.status)}</span>
                    </span>
                    <div className="server-actions transit-route-row-actions">
                      <button className="secondary compact" disabled={candidateLoading} type="button" onClick={() => void loadCandidateSummary(route.id)}>
                        查看摘要
                      </button>
                      <button className="secondary compact" disabled={candidateLoading} type="button" onClick={() => openCandidateExportModal(route.id)}>
                        临时导出
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
                        删除
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
        className="advanced-section transit-advanced-section"
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
              <select value={draft.forwardingMethod} onChange={(event) => setDraft({ ...draft, forwardingMethod: event.target.value as ForwardingMethod })}>
                <option value="socat">socat</option>
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
          title="远程清理并删除中转链路"
          targetLabel={`${deleteRoute.name} / ${routeEntry(deleteRoute)} -> ${deleteRoute.target_host}:${deleteRoute.target_port}`}
          confirmText={deleteRouteConfirmText}
          submitting={candidateLoading}
          onCancel={closeDeleteRouteModal}
          onConfirmTextChange={setDeleteRouteConfirmText}
          onConfirm={() => void submitDeleteRoute()}
          description={
            <>
              这会真实停止并删除该中转链路对应的 socat 服务，入口端口会失效。清理成功后，中转链路记录会被软删除。
              不会修改防火墙、云安全组、云防火墙，也不会 cutover。
            </>
          }
        />
      ) : null}

      {candidateExportModalOpen ? (
        <div className="modal-backdrop">
          <div className="modal-card transit-route-export-modal transit-export-modal">
            <div className="modal-header">
              <div>
                <h3>临时导出测试配置</h3>
                <p className="message">仅用于手动导入客户端测试；不会写入数据库，不会修改 nodes.share_link，不会 cutover。</p>
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
              <span>仅用于手动导入客户端测试。</span>
              <span>不会写入数据库。</span>
              <span>不会修改 `nodes.share_link`。</span>
              <span>不会 cutover。</span>
              <span>原直连节点仍保留。</span>
            </div>

            {candidateExport ? (
              <div className="candidate-export-result transit-export-result">
                <strong>临时测试配置已生成</strong>
                <span>名称：{candidateExport.candidate_name}</span>
                <span>服务器：{candidateExport.server}</span>
                <span>端口：{candidateExport.port}</span>
                <span>协议：{candidateExport.protocol} / {candidateExport.security} / {candidateExport.network}</span>
                <span>masked link：{candidateExport.masked_candidate_link}</span>
                <button
                  className="secondary"
                  type="button"
                  onClick={async () => {
                    try {
                      await copyText(candidateExport.candidate_link);
                      setCandidateCopyFallbackRequired(false);
                      setCandidateMessage("完整候选链接已复制。请妥善保存，仅用于手动导入测试，不要公开分享。");
                    } catch {
                      setCandidateCopyFallbackRequired(true);
                      setCandidateMessage("当前 HTTP 环境不支持自动复制，请使用下方文本框手动复制。");
                    }
                  }}
                >
                  复制完整候选链接
                </button>
                {candidateCopyFallbackRequired ? (
                  <label className="candidate-manual-copy transit-export-manual-copy">
                    手动复制完整候选链接
                    <textarea
                      readOnly
                      value={candidateExport.candidate_link}
                      onClick={(event) => event.currentTarget.select()}
                      onFocus={(event) => event.currentTarget.select()}
                    />
                  </label>
                ) : null}
                <p className="message">只用于手动导入测试；不代表正式切换，也没有写入 `nodes.share_link`。</p>
              </div>
            ) : null}

            <p className="message">{candidateMessage}</p>

            <div className="modal-actions">
              <button className="secondary" type="button" onClick={closeCandidateExportModal}>
                {candidateExport ? "关闭" : "取消"}
              </button>
              <button disabled={candidateLoading || !candidateExportRoute} type="button" onClick={() => void exportCandidateConfig(candidateExportRouteId)}>
                {candidateLoading ? "生成中" : candidateExport ? "重新生成" : "生成测试配置"}
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
                  <strong>创建 socat 中转链路</strong>
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
                    onChange={(event) => setCreateForm({ ...createForm, listenPort: event.target.value })}
                    placeholder={String(approvedTransitListenPort)}
                  />
                  <small>新增或变更中转监听端口时，必须自行确认云安全组 / 云防火墙 / 服务器本机防火墙已放行对应 TCP 端口。</small>
                </label>
                <label>
                  转发方式
                  <input readOnly value="socat" />
                </label>

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
                    <span>创建命令只通过 transit Worker allowlist 执行固定 socat service 模板，不接受任意 shell 或任意 systemd unit。</span>
                    <span>成功条件包括 systemd service active、监听端口 LISTEN、以及中转服务器到落地目标端口连通。</span>
                    <span>失败时不会生成完整客户端链接，不写 transit_routes.share_link，不修改落地节点，不 cutover。</span>
                    <span>本页面不会自动修改防火墙、云安全组或云防火墙；端口放行仍由用户自行确认。</span>
                  </div>
                </details>

                {createStep !== "idle" ? (
                  <div className="landing-plan-result node-create-result wide-field">
                    <div className={`plan-status-card ${createStep === "failed" ? "blocked" : createStep === "complete" ? "ready" : ""}`}>
                      <strong>{transitRouteCreateProgressLabels[createStep]}</strong>
                      <span>系统会先做只读预检，再创建 socat 中转命令。只有创建、监听和连通性检查成功后，才会临时导出客户端链接。</span>
                    </div>

                    {createStep !== "failed" ? (
                      <div className="node-create-progress" aria-label="中转链路创建进度">
                        {(["preflight_create", "preflight_running", "command_create", "command_running", "refresh", "export_link", "complete"] as TransitRouteCreateStep[]).map(
                          (step, index, steps) => {
                            const currentIndex = steps.indexOf(createStep);
                            return (
                              <span className={index < currentIndex ? "done" : index === currentIndex ? "current" : ""} key={step}>
                                {transitRouteCreateProgressLabels[step]}
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
