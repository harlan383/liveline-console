"use client";

import { useEffect, useRef, useState } from "react";
import QRCode from "react-qr-code";

import {
  apiFetch,
  createLandingNodeExecution,
  createLandingNodePlan,
  createWorkerCommand,
  createVpsWorkerBootstrap,
  createWorkerToken,
  exportNodeShareLink,
  getWorkerCommand,
  listWorkerCommands,
  OFFLINE_LOCAL_REMOVE_CONFIRM_TEXT,
  remoteCleanupDeleteNode,
  remoteCleanupDeleteVpsServer,
  REMOTE_CLEANUP_CONFIRM_TEXT,
  type LandingNodePlanResponse,
  type LandingNodeCreateResponse,
  type CsrfResult,
  type NodeData,
  type RemoteCleanupUnavailableData,
  type VpsServerData,
  type VpsServerListResult,
  type VpsServerUpdateResult,
  type WorkerCommandData,
  type WorkerRole,
  type WorkerTokenCreateResult,
} from "@/lib/api";

type ModalMode = "add" | "edit" | "delete" | "deleteNode" | "nodePlan" | "workerCommand" | null;
type DeleteFlowMode = "remote_cleanup" | "offline_local_remove";

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

type ServerFormState = {
  name: string;
  ip: string;
  sshPort: string;
  sshUser: string;
  notes: string;
};

type NodePlanFormState = {
  nodeName: string;
  listenPort: string;
  protocol: string;
  security: string;
  flow: string;
  serverName: string;
  dest: string;
  remark: string;
  allowInstallXray: boolean;
  allowModifyFirewall: boolean;
  allowGenerateShareLink: boolean;
  allowOverwriteExistingConfig: boolean;
  cloudSecurityGroupConfirmed: boolean;
  cloudFirewallConfirmed: boolean;
  serverFirewallConfirmed: boolean;
  requirePreflightSuccess: boolean;
  protectedCreateConfirmed: boolean;
};

type WorkerBootstrapFormState = {
  name: string;
  ip: string;
  interfaceName: string;
  expiresInMinutes: string;
};

type ServerNodeSummary = VpsServerData["nodes"][number];

const APPROVED_FORMAL_LISTEN_PORT = 27939;
const BLOCKED_NODE_LISTEN_PORTS = new Set([
  22,
  80,
  443,
  8080,
  8443,
  18443,
  3000,
  3200,
  8000,
  8200,
  5432,
  6379,
  15432,
  16379,
  10000,
  27017,
]);

const emptyServerForm: ServerFormState = {
  name: "",
  ip: "",
  sshPort: "22",
  sshUser: "root",
  notes: "",
};

function createEmptyNodePlanForm(): NodePlanFormState {
  return {
    nodeName: `liveline-reality-${APPROVED_FORMAL_LISTEN_PORT}`,
    listenPort: String(APPROVED_FORMAL_LISTEN_PORT),
    protocol: "vless",
    security: "reality",
    flow: "xtls-rprx-vision",
    serverName: "www.microsoft.com",
    dest: "www.microsoft.com:443",
    remark: "",
    allowInstallXray: true,
    allowModifyFirewall: false,
    allowGenerateShareLink: true,
    allowOverwriteExistingConfig: false,
    cloudSecurityGroupConfirmed: true,
    cloudFirewallConfirmed: true,
    serverFirewallConfirmed: true,
    requirePreflightSuccess: true,
    protectedCreateConfirmed: false,
  };
}

const NODE_CREATE_PROGRESS_LABELS: Record<string, string> = {
  idle: "准备中",
  preflight_create: "创建只读预检",
  preflight_running: "预检中",
  plan: "生成创建计划",
  command_create: "创建 Reality 节点命令",
  command_running: "安装 Xray / 写入配置 / 启动服务 / 检查端口",
  refresh: "刷新节点摘要",
  complete: "完成",
  failed: "失败",
};

const NODE_CREATE_TERMINAL_STATUSES = new Set(["succeeded", "failed", "expired", "cancelled"]);
const CLEANUP_COMMAND_TERMINAL_STATUSES = new Set(["succeeded", "failed", "cancelled", "timeout", "expired"]);
const CLEANUP_COMMAND_POLL_INTERVAL_MS = 2000;
const CLEANUP_COMMAND_MAX_POLLS = 30;
const WORKER_INSTALL_POLL_INTERVAL_MS = 3000;
const WORKER_INSTALL_MAX_POLLS = 60;

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

const emptyWorkerBootstrapForm: WorkerBootstrapFormState = {
  name: "",
  ip: "",
  interfaceName: "eth0",
  expiresInMinutes: "60",
};

const workerInterfaceNamePattern = /^[A-Za-z0-9_.-]+$/;

function defaultWorkerInterfaceName(value: string | null | undefined) {
  return value?.trim() || "eth0";
}

function isValidWorkerInterfaceName(value: string) {
  const cleaned = value.trim();
  return Boolean(cleaned) && cleaned.length <= 80 && workerInterfaceNamePattern.test(cleaned);
}

function sshStatusLabel(status: string) {
  const labels: Record<string, string> = {
    online: "在线",
    offline: "离线",
    unchecked: "未检测",
  };
  return labels[status] ?? status;
}

function displayStatusLabel(status: string) {
  const labels: Record<string, string> = {
    pending_worker: "待接入",
    online: "在线",
    stale: "心跳过期 / 离线",
    offline: "离线",
    unchecked: "未检测",
    disabled: "已停用",
    deleted: "已删除",
  };
  return labels[status] ?? sshStatusLabel(status);
}

function statusClass(status: string) {
  if (status === "online" || status === "active" || status === "success" || status === "worker_online") {
    return "ok";
  }
  if (status === "offline" || status === "stale" || status === "deleted" || status === "failed" || status === "worker_offline") {
    return "bad";
  }
  if (status === "unchecked" || status === "pending" || status === "pending_worker") {
    return "warn";
  }
  if (status === "not_checked") {
    return "warn";
  }
  return "muted";
}

function isVpsServerWorkerOnline(server: VpsServerData) {
  const displayStatus = server.display_status ?? "";
  const workerDisplayStatus = server.worker_display_status ?? "";
  return (
    server.worker_online ||
    server.worker_heartbeat_status === "online" ||
    displayStatus === "online" ||
    displayStatus === "worker_online" ||
    displayStatus === "active" ||
    workerDisplayStatus === "online" ||
    workerDisplayStatus === "worker_online" ||
    Boolean(server.worker_id && server.worker_last_heartbeat_at && !server.worker_is_heartbeat_stale)
  );
}

function nodeStatusLabel(status: string | undefined | null) {
  const labels: Record<string, string> = {
    active: "已启用",
    disabled: "已停用",
    deleted: "已删除",
    pending: "等待中",
    running: "执行中",
    success: "成功",
    completed: "成功",
    failed: "失败",
    not_checked: "未检测",
    cancelled: "已取消",
    timeout: "超时",
    unknown: "未知",
  };
  return labels[status ?? ""] ?? status ?? "-";
}

function formatTime(value: string | null) {
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
    landing_preflight: "只读预检",
    landing_node_create: "正式创建落地节点",
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
    timeout: "超时",
  };
  return labels[status] ?? status;
}

function maskShareLink(shareLink: string) {
  if (shareLink.length <= 40) {
    return `${shareLink.slice(0, 12)}...`;
  }
  return `${shareLink.slice(0, 24)}...${shareLink.slice(-12)}`;
}

function nodeEntryLabel(node: ServerNodeSummary, serverIp: string) {
  const host = node.ip || node.address || serverIp;
  return node.port ? `${host}:${node.port}` : host;
}

function nodeProtocolSummary(node: ServerNodeSummary) {
  return node.protocol === "vless" ? "vless / reality / tcp" : node.protocol;
}

function nodeConnectivityLabel(node: ServerNodeSummary | NodeData) {
  return node.connectivity_display_label ?? nodeStatusLabel(node.connectivity_status);
}

function nodeHealthSummary(node: ServerNodeSummary | NodeData) {
  return node.node_health_summary ?? nodeConnectivityLabel(node);
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.trim() ? value : "未返回";
}

function numericValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : "0";
}

function serviceByName(value: unknown, name: string) {
  if (!Array.isArray(value)) {
    return {};
  }
  const found = value.find((item) => item && typeof item === "object" && (item as Record<string, unknown>).name === name);
  return found && typeof found === "object" ? (found as Record<string, unknown>) : {};
}

async function copyTextWithFallback(text: string, textArea: HTMLTextAreaElement | null) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to the textarea selection fallback.
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

export function ServerManagementPanel() {
  const workerInstallCommandRef = useRef<HTMLTextAreaElement | null>(null);
  const nodeShareLinkRef = useRef<HTMLTextAreaElement | null>(null);
  const nodeQrFrameRef = useRef<HTMLDivElement | null>(null);
  const [servers, setServers] = useState<VpsServerData[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("落地服务器管理只读取本地系统记录；不会在页面加载时执行 SSH。");
  const [modalMode, setModalMode] = useState<ModalMode>(null);
  const [selectedServer, setSelectedServer] = useState<VpsServerData | null>(null);
  const [serverForm, setServerForm] = useState<ServerFormState>(emptyServerForm);
  const [nodePlanForm, setNodePlanForm] = useState<NodePlanFormState>(() => createEmptyNodePlanForm());
  const [nodePlanResult, setNodePlanResult] = useState<LandingNodePlanResponse | null>(null);
  const [formalCreateResult, setFormalCreateResult] = useState<LandingNodeCreateResponse | null>(null);
  const [nodeCreateStep, setNodeCreateStep] = useState("idle");
  const [nodeCreateCommand, setNodeCreateCommand] = useState<WorkerCommandData | null>(null);
  const [createdNodeSummary, setCreatedNodeSummary] = useState<ServerNodeSummary | null>(null);
  const [nodeCreateError, setNodeCreateError] = useState<string | null>(null);
  const [workerBootstrapForm, setWorkerBootstrapForm] = useState<WorkerBootstrapFormState>(emptyWorkerBootstrapForm);
  const [workerTokenResult, setWorkerTokenResult] = useState<WorkerTokenCreateResult | null>(null);
  const [workerInstallHeartbeatMessage, setWorkerInstallHeartbeatMessage] = useState("");
  const [workerCommandsByWorkerId, setWorkerCommandsByWorkerId] = useState<Record<string, WorkerCommandData[]>>({});
  const [latestWorkerCommandByServerId, setLatestWorkerCommandByServerId] = useState<Record<string, WorkerCommandData>>({});
  const [workerCommandLoadingId, setWorkerCommandLoadingId] = useState<string | null>(null);
  const [deleteMode, setDeleteMode] = useState<DeleteFlowMode>("remote_cleanup");
  const [selectedNodeForDelete, setSelectedNodeForDelete] = useState<ServerNodeSummary | null>(null);
  const [selectedNodeDetail, setSelectedNodeDetail] = useState<NodeData | null>(null);
  const [nodeDetailLoading, setNodeDetailLoading] = useState(false);
  const [showFullShareLink, setShowFullShareLink] = useState(false);
  const [showNodeQrCode, setShowNodeQrCode] = useState(false);
  const [exportedNodeShareLink, setExportedNodeShareLink] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const workerInstallPollTimeoutRef = useRef<number | null>(null);
  const workerInstallPollingServerIdRef = useRef<string | null>(null);
  const pendingDeletedServerIdsRef = useRef<Set<string>>(new Set());
  const pendingDeletedNodeIdsRef = useRef<Set<string>>(new Set());

  function filterVisibleServers(nextServers: VpsServerData[]) {
    const pendingServerIds = pendingDeletedServerIdsRef.current;
    const pendingNodeIds = pendingDeletedNodeIdsRef.current;
    return nextServers
      .filter((server) => !pendingServerIds.has(server.id) && server.status.toLowerCase() !== "deleted")
      .map((server) => ({
        ...server,
        nodes: server.nodes.filter((node) => !pendingNodeIds.has(node.id) && node.status.toLowerCase() !== "deleted"),
      }));
  }

  function setVisibleServers(nextServers: VpsServerData[]) {
    const visibleServers = filterVisibleServers(nextServers);
    setServers(visibleServers);
    return visibleServers;
  }

  function markServerPendingDelete(serverId: string) {
    pendingDeletedServerIdsRef.current.add(serverId);
    if (workerInstallPollingServerIdRef.current === serverId) {
      clearWorkerInstallPolling();
    }
    setServers((current) => filterVisibleServers(current));
  }

  function releaseServerPendingDelete(serverId: string) {
    pendingDeletedServerIdsRef.current.delete(serverId);
  }

  function markNodePendingDelete(nodeId: string) {
    pendingDeletedNodeIdsRef.current.add(nodeId);
    setServers((current) => filterVisibleServers(current));
  }

  function releaseNodePendingDelete(nodeId: string) {
    pendingDeletedNodeIdsRef.current.delete(nodeId);
  }

  async function ensureCsrfToken() {
    const csrf = await apiFetch<CsrfResult>("/api/auth/csrf");
    if (!csrf.success) {
      throw new Error(csrf.message);
    }
    return csrf.data.csrf_token;
  }

  async function loadServers() {
    setLoading(true);
    const result = await apiFetch<VpsServerListResult>("/api/vps");
    if (result.success) {
      const visibleServers = setVisibleServers(result.data.servers);
      await Promise.all(
        visibleServers
          .filter((server) => server.worker_id)
          .map((server) => loadWorkerCommands(server.worker_id as string, server.id)),
      );
      setMessage("服务器列表已刷新。");
      setLoading(false);
      return visibleServers;
    } else {
      setMessage(`${result.error_code}: ${result.message}`);
    }
    setLoading(false);
    return [];
  }

  function clearWorkerInstallPolling() {
    if (workerInstallPollTimeoutRef.current !== null) {
      window.clearTimeout(workerInstallPollTimeoutRef.current);
      workerInstallPollTimeoutRef.current = null;
    }
    workerInstallPollingServerIdRef.current = null;
  }

  async function pollWorkerInstallHeartbeat(serverId: string, attempt = 0) {
    if (workerInstallPollingServerIdRef.current !== serverId || pendingDeletedServerIdsRef.current.has(serverId)) {
      if (pendingDeletedServerIdsRef.current.has(serverId)) {
        clearWorkerInstallPolling();
      }
      return;
    }

    const result = await apiFetch<VpsServerListResult>("/api/vps");
    if (result.success) {
      const visibleServers = setVisibleServers(result.data.servers);
      const server = visibleServers.find((item) => item.id === serverId);
      if (server?.worker_id) {
        await loadWorkerCommands(server.worker_id, server.id);
      }
      if (server && isVpsServerWorkerOnline(server)) {
        clearWorkerInstallPolling();
        setWorkerInstallHeartbeatMessage("已检测到 Worker 在线。");
        setMessage("已检测到 Worker 在线，落地服务器列表已自动刷新。");
        return;
      }
    }

    if (attempt + 1 >= WORKER_INSTALL_MAX_POLLS) {
      clearWorkerInstallPolling();
      await loadServers();
      const timeoutMessage = "未检测到 Worker 上线，请检查安装命令是否执行成功、curl 是否可用、systemd 是否正常、VPS 是否能访问主控 backend。";
      setWorkerInstallHeartbeatMessage(timeoutMessage);
      setMessage(timeoutMessage);
      return;
    }

    setWorkerInstallHeartbeatMessage("等待 Worker 上线...");
    workerInstallPollTimeoutRef.current = window.setTimeout(() => {
      void pollWorkerInstallHeartbeat(serverId, attempt + 1);
    }, WORKER_INSTALL_POLL_INTERVAL_MS);
  }

  function startWorkerInstallPolling(serverId: string) {
    clearWorkerInstallPolling();
    workerInstallPollingServerIdRef.current = serverId;
    setWorkerInstallHeartbeatMessage("等待 Worker 上线...");
    setMessage("Worker 安装命令已生成，正在等待 Worker 注册和 heartbeat。");
    void pollWorkerInstallHeartbeat(serverId);
  }

  useEffect(() => {
    void loadServers();
    return () => {
      clearWorkerInstallPolling();
    };
  }, []);

  function closeModal() {
    // Keep Worker heartbeat polling alive after the modal closes; it stops on
    // online, timeout, unmount, or when a new install command replaces it.
    setModalMode(null);
    setSelectedServer(null);
    setServerForm(emptyServerForm);
    setNodePlanForm(createEmptyNodePlanForm());
    setNodePlanResult(null);
    setFormalCreateResult(null);
    setNodeCreateStep("idle");
    setNodeCreateCommand(null);
    setCreatedNodeSummary(null);
    setNodeCreateError(null);
    setWorkerBootstrapForm(emptyWorkerBootstrapForm);
    setWorkerTokenResult(null);
    setWorkerInstallHeartbeatMessage("");
    setDeleteMode("remote_cleanup");
    setSelectedNodeForDelete(null);
  }

  function closeNodeDetail() {
    setSelectedNodeDetail(null);
    setShowFullShareLink(false);
    setShowNodeQrCode(false);
    setExportedNodeShareLink(null);
  }

  function openAddServer() {
    setServerForm(emptyServerForm);
    setWorkerBootstrapForm(emptyWorkerBootstrapForm);
    setWorkerTokenResult(null);
    setWorkerInstallHeartbeatMessage("");
    setSelectedServer(null);
    setModalMode("add");
  }

  function openWorkerCommand(server: VpsServerData) {
    setSelectedServer(server);
    setWorkerBootstrapForm({
      name: server.name || server.ip,
      ip: server.ip,
      interfaceName: defaultWorkerInterfaceName(server.worker_interface_name),
      expiresInMinutes: "60",
    });
    setWorkerTokenResult(null);
    setWorkerInstallHeartbeatMessage("");
    setModalMode("workerCommand");
  }

  function openEdit(server: VpsServerData) {
    setSelectedServer(server);
    setServerForm({
      ...emptyServerForm,
      name: server.name,
      ip: server.ip,
      sshPort: String(server.ssh_port),
      sshUser: server.ssh_user || server.ssh_username || "root",
      notes: server.notes ?? "",
    });
    setModalMode("edit");
  }

  function openDelete(server: VpsServerData) {
    setSelectedServer(server);
    setDeleteMode(server.worker_online ? "remote_cleanup" : "offline_local_remove");
    setModalMode("delete");
  }

  function openDeleteNode(server: VpsServerData, node: ServerNodeSummary) {
    setSelectedServer(server);
    setSelectedNodeForDelete(node);
    setDeleteMode(server.worker_online ? "remote_cleanup" : "offline_local_remove");
    setModalMode("deleteNode");
  }

  function openNodePlan(server: VpsServerData) {
    setSelectedServer(server);
    setNodePlanForm(createEmptyNodePlanForm());
    setNodePlanResult(null);
    setFormalCreateResult(null);
    setNodeCreateStep("idle");
    setNodeCreateCommand(null);
    setCreatedNodeSummary(null);
    setNodeCreateError(null);
    setModalMode("nodePlan");
  }

  async function closeNodeCreateModal(refreshAfterSuccess = false) {
    closeModal();
    if (refreshAfterSuccess) {
      await loadServers();
      setMessage("直连节点创建完成，服务器和节点列表已刷新。");
    }
  }

  async function fetchNodeDetail(nodeId: string) {
    setNodeDetailLoading(true);
    try {
      const result = await apiFetch<NodeData>(`/api/nodes/${nodeId}`);
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return null;
      }
      return result.data;
    } finally {
      setNodeDetailLoading(false);
    }
  }

  async function generateWorkerInstallCommand(role: WorkerRole) {
    const name = workerBootstrapForm.name.trim();
    const ip = workerBootstrapForm.ip.trim();
    const interfaceName = workerBootstrapForm.interfaceName.trim();
    const expiresInMinutes = Number(workerBootstrapForm.expiresInMinutes);
    if (modalMode === "add" && !name) {
      setMessage("请填写服务器名称。");
      return;
    }
    if (modalMode === "add" && !ip) {
      setMessage("请填写服务器 IP。");
      return;
    }
    if (!Number.isInteger(expiresInMinutes) || expiresInMinutes < 1 || expiresInMinutes > 10080) {
      setMessage("过期时间必须是 1 到 10080 分钟之间的整数。");
      return;
    }
    if (!isValidWorkerInterfaceName(interfaceName)) {
      setMessage("网卡不能为空，且只能包含字母、数字、点、下划线或短横线。");
      return;
    }
    setSubmitting(true);
    setWorkerTokenResult(null);
    setWorkerInstallHeartbeatMessage("");
    clearWorkerInstallPolling();
    setMessage(modalMode === "add" ? "正在保存落地服务器并生成一次性 Worker 安装命令。" : "正在重新生成一次性 Worker 安装命令。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result =
        modalMode === "workerCommand" && selectedServer
          ? await createWorkerToken(
              {
                role,
                name: name || selectedServer.name,
                server_id: selectedServer.id,
                expires_in_minutes: expiresInMinutes,
                interface_name: interfaceName,
              },
              csrfToken,
            )
          : await createVpsWorkerBootstrap(
              {
                name,
                ip,
                expires_in_minutes: expiresInMinutes,
                interface_name: interfaceName,
              },
              csrfToken,
            );
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      const tokenResult = "token" in result.data ? result.data.token : result.data;
      const targetServerId = "server" in result.data ? result.data.server.id : tokenResult.server_id ?? selectedServer?.id ?? null;
      setWorkerTokenResult(tokenResult);
      await loadServers();
      if (targetServerId) {
        startWorkerInstallPolling(targetServerId);
      } else {
        setMessage("Worker 安装命令已生成，请在 VPS 上执行后手动刷新列表查看上线状态。");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "生成 Worker 安装命令失败。");
    } finally {
      setSubmitting(false);
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

  async function loadWorkerCommands(workerId: string, serverId?: string) {
    const result = await listWorkerCommands(workerId);
    if (!result.success) {
      setMessage(`${result.error_code}: ${result.message}`);
      return;
    }
    setWorkerCommandsByWorkerId((current) => ({ ...current, [workerId]: result.data.commands }));
    if (serverId && result.data.commands[0]) {
      setLatestWorkerCommandByServerId((current) => ({ ...current, [serverId]: result.data.commands[0] }));
    }
  }

  function scheduleServerRefresh(command?: WorkerCommandData | null, serverId?: string | null) {
    [1500, 4000].forEach((delay) => {
      window.setTimeout(() => {
        void loadServers();
        if (command?.target_worker_id) {
          void loadWorkerCommands(command.target_worker_id, serverId ?? undefined);
        } else if (command?.worker_id) {
          void loadWorkerCommands(command.worker_id, serverId ?? undefined);
        }
      }, delay);
    });
  }

  async function refreshWhenCleanupCommandCompletes(
    command?: WorkerCommandData | null,
    serverId?: string | null,
    pendingDelete?: { serverId?: string; nodeId?: string },
  ) {
    if (!command?.id) {
      return;
    }

    let latestCommand: WorkerCommandData | null = command;
    const commandServerId = serverId ?? command.server_id ?? undefined;

    for (let attempt = 0; attempt < CLEANUP_COMMAND_MAX_POLLS; attempt += 1) {
      await sleep(CLEANUP_COMMAND_POLL_INTERVAL_MS);
      const result = await getWorkerCommand(command.id);
      if (result.success) {
        latestCommand = result.data;
        if (commandServerId) {
          setLatestWorkerCommandByServerId((current) => ({ ...current, [commandServerId]: result.data }));
        }
        if (CLEANUP_COMMAND_TERMINAL_STATUSES.has(result.data.status)) {
          const workerId = result.data.target_worker_id || result.data.worker_id;
          if (result.data.status !== "succeeded") {
            if (pendingDelete?.serverId) {
              releaseServerPendingDelete(pendingDelete.serverId);
            }
            if (pendingDelete?.nodeId) {
              releaseNodePendingDelete(pendingDelete.nodeId);
            }
          }
          await loadServers();
          if (workerId) {
            await loadWorkerCommands(workerId, commandServerId);
          }
          setMessage(
            result.data.status === "succeeded"
              ? "清理任务已完成，服务器和节点列表已自动刷新。"
              : `清理任务已进入终态：${workerCommandStatusLabel(result.data.status)}。列表已自动刷新，请查看最近命令详情。`,
          );
          return;
        }
      }
    }

    await loadServers();
    const workerId = latestCommand?.target_worker_id || latestCommand?.worker_id;
    if (workerId) {
      await loadWorkerCommands(workerId, commandServerId);
    }
    setMessage("清理任务仍在执行，列表已再次刷新；请稍后查看任务中心或再次刷新。");
  }

  async function runWorkerCheck(server: VpsServerData) {
    if (!server.worker_id || !server.worker_online) {
      setMessage("Worker 未在线，不能创建 Worker 检查命令。");
      return;
    }
    setWorkerCommandLoadingId(server.worker_id);
    setMessage("正在创建 Worker 状态检查命令。该命令只会由 Worker 轮询执行，不会 SSH。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await createWorkerCommand(
        server.worker_id,
        { command_type: "collect_status", payload: null, server_id: server.id, server_type: "landing" },
        csrfToken,
      );
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setLatestWorkerCommandByServerId((current) => ({ ...current, [server.id]: result.data.command }));
      const targetVersion = result.data.target_worker_version || "未知版本";
      const targetNote = result.data.target_worker_changed ? "已自动切换到最新支持命令的 Worker。" : "";
      setMessage(
        `Worker 检查命令已创建：${result.data.command.id}；目标 Worker：${result.data.target_worker_id} / ${targetVersion}。${targetNote}`,
      );
      await loadWorkerCommands(result.data.target_worker_id, server.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "创建 Worker 检查命令失败。");
    } finally {
      setWorkerCommandLoadingId(null);
    }
  }

  async function runLandingPreflight(server: VpsServerData) {
    if (!server.worker_id || !server.worker_online) {
      setMessage("Worker 未在线，不能创建落地服务器只读预检命令。");
      return;
    }
    setWorkerCommandLoadingId(server.worker_id);
    setMessage("正在创建落地服务器只读预检命令。该命令只由已注册 Worker 执行固定只读检查，不会 SSH 或创建节点。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await createWorkerCommand(
        server.worker_id,
        { command_type: "landing_preflight", payload: null, server_id: server.id, server_type: "landing" },
        csrfToken,
      );
      if (!result.success) {
        const upgradeHint =
          result.error_code === "WORKER_COMMAND_UNSUPPORTED"
            ? " 请重新生成安装命令并升级该服务器上的 liveline-worker 后再试。"
            : "";
        setMessage(`${result.error_code}: ${result.message}${upgradeHint}`);
        return;
      }
      setLatestWorkerCommandByServerId((current) => ({ ...current, [server.id]: result.data.command }));
      const targetVersion = result.data.target_worker_version || "未知版本";
      const targetNote = result.data.target_worker_changed ? "已自动切换到最新支持只读预检的 Worker。" : "";
      setMessage(
        `只读预检命令已创建：${result.data.command.id}；目标 Worker：${result.data.target_worker_id} / ${targetVersion}。${targetNote}`,
      );
      await loadWorkerCommands(result.data.target_worker_id, server.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "创建落地服务器只读预检命令失败。");
    } finally {
      setWorkerCommandLoadingId(null);
    }
  }

  async function waitForWorkerCommandCompletion(workerId: string, commandId: string, serverId: string, runningStep: string) {
    for (let attempt = 0; attempt < 90; attempt += 1) {
      const result = await listWorkerCommands(workerId);
      if (!result.success) {
        throw new Error(`${result.error_code}: ${result.message}`);
      }
      setWorkerCommandsByWorkerId((current) => ({ ...current, [workerId]: result.data.commands }));
      if (result.data.commands[0]) {
        setLatestWorkerCommandByServerId((current) => ({ ...current, [serverId]: result.data.commands[0] }));
      }
      const command = result.data.commands.find((item) => item.id === commandId);
      if (command) {
        setNodeCreateCommand(command);
        if (NODE_CREATE_TERMINAL_STATUSES.has(command.status)) {
          return command;
        }
      }
      setNodeCreateStep(runningStep);
      await sleep(2000);
    }
    throw new Error("Worker 命令等待超时。请刷新列表查看最新状态。");
  }

  function friendlyNodeCreateError(error: unknown) {
    const raw = error instanceof Error ? error.message : String(error || "创建失败。");
    if (
      raw.includes("FORMAL_SERVER_NOT_APPROVED") ||
      raw.includes("FORMAL_PREFLIGHT_INTERFACE") ||
      raw.includes("FORMAL_WORKER_INTERFACE_MISMATCH")
    ) {
      return "正式创建审批未通过：请重新运行预检，确认当前落地服务器 Worker 在线、绑定服务器正确，并且 Worker 网卡与默认公网网卡一致。";
    }
    if (raw.includes("WORKER") || raw.includes("Worker")) {
      return "Worker 不在线或版本不满足，请检查落地服务器 Worker 状态。";
    }
    if (raw.includes("PORT") || raw.includes("port") || raw.includes("端口")) {
      return "端口检查失败：端口可能已被占用，或云安全组 / 云防火墙 / 服务器防火墙未放行。";
    }
    if (raw.includes("XRAY") || raw.includes("Xray") || raw.includes("xray")) {
      return "Xray 检查失败：可能已存在配置，或服务启动 / 配置测试失败。";
    }
    if (raw.includes("PREFLIGHT") || raw.includes("preflight") || raw.includes("预检")) {
      return "预检失败：请检查 Worker、端口监听、Xray 状态和防火墙放行情况。";
    }
    return raw;
  }

  function findCreatedNode(serverList: VpsServerData[], serverId: string, listenPort: number) {
    const server = serverList.find((item) => item.id === serverId);
    return server?.nodes.find((node) => node.port === listenPort && node.share_link_present) ?? null;
  }

  async function submitSimplifiedLandingNodeCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedServer) {
      return;
    }
    if (!selectedServer.worker_id || !selectedServer.worker_online) {
      setMessage("Worker 未在线，不能创建直连节点。");
      return;
    }
    const listenPort = Number(nodePlanForm.listenPort);
    if (listenPort !== APPROVED_FORMAL_LISTEN_PORT) {
      setMessage(`当前正式创建仍使用受保护端口 ${APPROVED_FORMAL_LISTEN_PORT}/TCP。本阶段不支持动态端口正式创建。`);
      return;
    }
    if (BLOCKED_NODE_LISTEN_PORTS.has(listenPort)) {
      setMessage(`端口 ${listenPort} 是常用 / 保留端口，请换一个端口。`);
      return;
    }
    if (!nodePlanForm.protectedCreateConfirmed) {
      setMessage(`请先确认 ${APPROVED_FORMAL_LISTEN_PORT}/TCP 已在云安全组、云防火墙和服务器本机防火墙放行。`);
      return;
    }
    setSubmitting(true);
    setNodePlanResult(null);
    setFormalCreateResult(null);
    setCreatedNodeSummary(null);
    setNodeCreateCommand(null);
    setNodeCreateError(null);
    setMessage("正在自动执行预检和创建流程；完整链接只会在创建成功后通过受控导出显示。");

    try {
      const csrfToken = await ensureCsrfToken();
      setNodeCreateStep("preflight_create");
      const preflightResult = await createWorkerCommand(
        selectedServer.worker_id,
        { command_type: "landing_preflight", payload: null, server_id: selectedServer.id, server_type: "landing" },
        csrfToken,
      );
      if (!preflightResult.success) {
        throw new Error(`${preflightResult.error_code}: ${preflightResult.message}`);
      }
      setLatestWorkerCommandByServerId((current) => ({ ...current, [selectedServer.id]: preflightResult.data.command }));
      const preflightCommand = await waitForWorkerCommandCompletion(
        preflightResult.data.target_worker_id,
        preflightResult.data.command.id,
        selectedServer.id,
        "preflight_running",
      );
      if (preflightCommand.status !== "succeeded") {
        throw new Error(preflightCommand.error_message || "预检未通过。");
      }

      setNodeCreateStep("plan");
      const planResult = await createLandingNodePlan(
        selectedServer.id,
        {
          listen_port: listenPort,
          protocol: nodePlanForm.protocol,
          security: nodePlanForm.security,
          flow: nodePlanForm.flow,
          server_name: nodePlanForm.serverName,
          dest: nodePlanForm.dest,
          remark: nodePlanForm.nodeName || null,
          allow_install_xray: true,
          allow_modify_firewall: false,
          allow_generate_share_link: true,
          allow_overwrite_existing_config: false,
          cloud_security_group_confirmed: nodePlanForm.protectedCreateConfirmed,
          cloud_firewall_confirmed: nodePlanForm.protectedCreateConfirmed,
          server_firewall_confirmed: nodePlanForm.protectedCreateConfirmed,
          require_manual_cloud_firewall_confirmation: true,
          require_preflight_success: true,
        },
        csrfToken,
      );
      if (!planResult.success) {
        throw new Error(`${planResult.error_code}: ${planResult.message}`);
      }
      setNodePlanResult(planResult.data);
      if (!planResult.data.ready) {
        throw new Error(
          planResult.data.blocked_reasons.length
            ? planResult.data.blocked_reasons.map((reason) => blockedReasonLabel(reason)).join("；")
            : "创建计划未通过。",
        );
      }

      setNodeCreateStep("command_create");
      const createResult = await createLandingNodeExecution(
        selectedServer.id,
        {
          approved_port: APPROVED_FORMAL_LISTEN_PORT,
          node_name: nodePlanForm.nodeName || null,
          server_name: nodePlanForm.serverName,
          dest: nodePlanForm.dest,
          confirm_firewall_open: nodePlanForm.protectedCreateConfirmed,
          confirm_generate_share_link: nodePlanForm.protectedCreateConfirmed,
          confirm_write_share_link_after_success: nodePlanForm.protectedCreateConfirmed,
          confirm_no_existing_xray: nodePlanForm.protectedCreateConfirmed,
          confirm_rollback_new_artifacts_only: nodePlanForm.protectedCreateConfirmed,
        },
        csrfToken,
      );
      if (!createResult.success) {
        throw new Error(`${createResult.error_code}: ${createResult.message}`);
      }
      setFormalCreateResult(createResult.data);
      setLatestWorkerCommandByServerId((current) => ({ ...current, [selectedServer.id]: createResult.data.command }));
      const createCommand = await waitForWorkerCommandCompletion(
        createResult.data.target_worker_id,
        createResult.data.command_id,
        selectedServer.id,
        "command_running",
      );
      if (createCommand.status !== "succeeded") {
        throw new Error(createCommand.error_message || "创建命令执行失败。");
      }

      setNodeCreateStep("refresh");
      const refreshedServers = await loadServers();
      const createdNode = findCreatedNode(refreshedServers, selectedServer.id, listenPort);
      setCreatedNodeSummary(createdNode);
      setNodeCreateStep("complete");
      setMessage(
        createdNode
          ? "直连节点创建完成。可以复制客户端链接或临时显示二维码。"
          : "直连节点创建命令已成功。列表刷新后如未看到节点，请再次点击刷新。",
      );
    } catch (error) {
      const friendly = friendlyNodeCreateError(error);
      setNodeCreateStep("failed");
      setNodeCreateError(friendly);
      setMessage(`${friendly} 失败时不会写入 node.share_link，也不会生成完整链接。`);
    } finally {
      setSubmitting(false);
    }
  }

  function latestWorkerCommandForServer(server: VpsServerData) {
    return latestWorkerCommandByServerId[server.id] ?? (server.worker_id ? workerCommandsByWorkerId[server.worker_id]?.[0] : undefined);
  }

  function renderLandingPreflightSummary(resultJson: Record<string, unknown>) {
    const system = resultJson.system && typeof resultJson.system === "object" ? (resultJson.system as Record<string, unknown>) : {};
    const network = resultJson.network && typeof resultJson.network === "object" ? (resultJson.network as Record<string, unknown>) : {};
    const ports = resultJson.ports && typeof resultJson.ports === "object" ? (resultJson.ports as Record<string, unknown>) : {};
    const xrayService = serviceByName(resultJson.services, "xray");
    const firewall = resultJson.firewall && typeof resultJson.firewall === "object" ? (resultJson.firewall as Record<string, unknown>) : {};
    const xray = resultJson.xray_discovery && typeof resultJson.xray_discovery === "object" ? (resultJson.xray_discovery as Record<string, unknown>) : {};
    const warnings = Array.isArray(resultJson.warnings) ? resultJson.warnings.length : 0;
    const listenCount = typeof ports.listening_count === "number" ? ports.listening_count : 0;
    const importantPorts = ports.important_ports && typeof ports.important_ports === "object" ? (ports.important_ports as Record<string, unknown>) : {};
    const workerConfigInterface = network.worker_config_interface || system.worker_config_interface || system.interface_name;
    const defaultRouteInterface = network.default_route_interface || network.primary_interface;
    const defaultRouteGateway = network.default_route_gateway;
    const primaryInterfaceIp = network.primary_interface_ip;
    const interfaceMismatch = network.interface_mismatch === true;
    const listeningSummary = Array.isArray(ports.listening_summary) ? ports.listening_summary : [];
    const validListeningPorts = listeningSummary
      .map((item) => (item && typeof item === "object" ? (item as Record<string, unknown>).port : undefined))
      .filter((port) => typeof port === "number" && port > 0)
      .map((port) => String(port));

    return (
      <div className="worker-preflight-summary" aria-label="落地服务器只读预检摘要">
        <span title={stringValue(system.hostname)}>主机：{stringValue(system.hostname)}</span>
        <span>Worker 配置网卡：{stringValue(workerConfigInterface)}</span>
        <span>系统默认公网网卡：{stringValue(defaultRouteInterface)}</span>
        <span>默认公网网关：{stringValue(defaultRouteGateway)}</span>
        <span>默认公网网卡 IP：{stringValue(primaryInterfaceIp)}</span>
        <span>是否不一致：{interfaceMismatch ? "是" : "否"}</span>
        <span title={stringValue(network.ip_route)}>默认路由：{stringValue(network.ip_route)}</span>
        <span>监听端口：{String(listenCount)}</span>
        <span title={validListeningPorts.join(", ")}>有效监听：{validListeningPorts.length ? validListeningPorts.join(", ") : "无"}</span>
        <span>443：{stringValue((importantPorts["443"] as Record<string, unknown> | undefined)?.status)}</span>
        <span>Xray：{stringValue(xrayService.active)}</span>
        <span>防火墙：ufw {firewall.ufw_status ? "已返回摘要" : "未返回"}</span>
        <span>配置发现：{Array.isArray(xray.paths) ? "已返回元数据" : "未返回"}</span>
        <span>警告：{numericValue(warnings)}</span>
      </div>
    );
  }

  function renderRecentWorkerCommand(command: WorkerCommandData | undefined) {
    if (!command) {
      return null;
    }
    return (
      <div className="worker-command-status">
        <span>
          最近命令：
          {workerCommandTypeLabel(command.command_type)} / {workerCommandStatusLabel(command.status)}
          {command.target_worker_version ? ` / Worker ${command.target_worker_version}` : ""}
          {command.result_summary ? ` / ${command.result_summary}` : ""}
          {command.error_message ? ` / ${command.error_message}` : ""}
        </span>
        {command.command_type === "landing_preflight" && command.status === "succeeded"
          ? renderLandingPreflightSummary(command.result_json)
          : null}
      </div>
    );
  }

  async function openNodeDetail(node: ServerNodeSummary, showQr = false) {
    setMessage("正在读取节点详情。");
    const detail = await fetchNodeDetail(node.id);
    if (!detail) {
      return;
    }
    setSelectedNodeDetail(detail);
    setShowFullShareLink(false);
    setShowNodeQrCode(false);
    setExportedNodeShareLink(null);
    if (showQr) {
      await exportSelectedNodeShareLink(detail.id, "qr_code", { showQr: true });
    }
    setMessage("节点详情已读取。完整分享链接默认隐藏。");
  }

  async function exportSelectedNodeShareLink(
    nodeId: string,
    reason: string,
    options: { copy?: boolean; reveal?: boolean; showQr?: boolean } = {},
  ) {
    const confirmed = window.confirm(
      "节点分享链接属于敏感信息，仅用于导入客户端。不要粘贴到聊天、PR、日志或文档中。确认继续导出吗？",
    );
    if (!confirmed) {
      return null;
    }
    const csrfToken = await ensureCsrfToken();
    const result = await exportNodeShareLink(nodeId, csrfToken, reason);
    if (!result.success) {
      setMessage(`${result.error_code}: ${result.message}`);
      return null;
    }
    const link = result.data.share_link;
    setExportedNodeShareLink(link);
    setShowFullShareLink(Boolean(options.reveal));
    setShowNodeQrCode(Boolean(options.showQr));
    if (options.copy) {
      const copied = await copyTextWithFallback(link, nodeShareLinkRef.current);
      if (copied) {
        setMessage("客户端链接已复制到剪贴板，请妥善保存，不要公开分享。");
      } else {
        setShowFullShareLink(true);
        setMessage("当前浏览器不支持自动复制。请在节点详情弹窗中使用链接框手动复制，勿公开分享。");
      }
    } else {
      setMessage("节点链接已临时导出，请勿公开分享。");
    }
    return link;
  }

  async function copyNodeShareLink(node: ServerNodeSummary) {
    if (!node.share_link_present) {
      setMessage("该节点还没有可复制的分享链接。");
      return;
    }
    if (!navigator.clipboard?.writeText) {
      setMessage("当前 HTTP 环境可能无法自动复制，正在打开节点详情以便手动复制。");
      const detail = await fetchNodeDetail(node.id);
      if (!detail) {
        return;
      }
      setSelectedNodeDetail(detail);
      setShowFullShareLink(false);
      setShowNodeQrCode(false);
      setExportedNodeShareLink(null);
    }
    await exportSelectedNodeShareLink(node.id, "client_import", { copy: true });
  }

  function downloadNodeQrCode() {
    const svg = nodeQrFrameRef.current?.querySelector("svg");
    if (!svg || !selectedNodeDetail) {
      setMessage("请先显示二维码。");
      return;
    }
    const source = new XMLSerializer().serializeToString(svg);
    const blob = new Blob([source], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${selectedNodeDetail.node_name || "liveline-node"}-qr.svg`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setMessage("二维码已下载。请妥善保存，不要公开分享。");
  }

  async function submitEdit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedServer) {
      return;
    }
    setSubmitting(true);
    setMessage("正在保存服务器信息。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await apiFetch<VpsServerUpdateResult>(`/api/vps/${selectedServer.id}`, {
        method: "PATCH",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify({
          name: serverForm.name,
          ip: serverForm.ip,
          ssh_port: Number(serverForm.sshPort),
          ssh_user: serverForm.sshUser,
          notes: serverForm.notes,
        }),
      });

      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }

      setMessage(result.data.ssh_status_reset ? "服务器信息已保存，SSH 状态已重置为未检测。" : "服务器信息已保存。");
      closeModal();
      await loadServers();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "编辑服务器失败。");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitDelete() {
    const requiredConfirmText = requiredDeleteConfirmText(deleteMode);
    if (!selectedServer) {
      return;
    }
    const serverId = selectedServer.id;
    markServerPendingDelete(serverId);
    setSubmitting(true);
    setMessage(
      deleteMode === "offline_local_remove"
        ? "正在本地移除落地服务器记录；不会创建 Worker command 或执行远程清理。"
        : "正在创建落地服务器远程清理任务；清理成功后才会软删除系统记录。",
    );
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await remoteCleanupDeleteVpsServer(selectedServer.id, csrfToken, requiredConfirmText);

      if (!result.success) {
        releaseServerPendingDelete(serverId);
        await loadServers();
        if (result.error_code === "REMOTE_CLEANUP_UNAVAILABLE" && isOfflineLocalRemoveOffer(result.data)) {
          setDeleteMode("offline_local_remove");
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
      await loadServers();
      scheduleServerRefresh(result.data.command, serverId);
      void refreshWhenCleanupCommandCompletes(result.data.command, serverId, { serverId });
    } catch (error) {
      releaseServerPendingDelete(serverId);
      await loadServers();
      setMessage(error instanceof Error ? error.message : "删除服务器失败。");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitDeleteNode() {
    const requiredConfirmText = requiredDeleteConfirmText(deleteMode);
    if (!selectedNodeForDelete) {
      return;
    }
    const nodeId = selectedNodeForDelete.id;
    const serverId = selectedServer?.id ?? null;
    markNodePendingDelete(nodeId);
    setSubmitting(true);
    setMessage(
      deleteMode === "offline_local_remove"
        ? "正在本地移除节点记录；不会创建 Worker command 或执行远程清理。"
        : "正在创建节点远程清理任务；清理成功后才会软删除系统记录。",
    );
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await remoteCleanupDeleteNode(selectedNodeForDelete.id, csrfToken, requiredConfirmText);

      if (!result.success) {
        releaseNodePendingDelete(nodeId);
        await loadServers();
        if (result.error_code === "REMOTE_CLEANUP_UNAVAILABLE" && isOfflineLocalRemoveOffer(result.data)) {
          setDeleteMode("offline_local_remove");
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
      await loadServers();
      scheduleServerRefresh(result.data.command, serverId);
      void refreshWhenCleanupCommandCompletes(result.data.command, serverId, { nodeId });
    } catch (error) {
      releaseNodePendingDelete(nodeId);
      await loadServers();
      setMessage(error instanceof Error ? error.message : "删除节点失败。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel wide server-management-panel">
      <div className="server-management-header">
        <div>
          <h2>落地服务器</h2>
        </div>
        <button type="button" onClick={openAddServer}>
          添加落地服务器
        </button>
      </div>

      <div className="server-table" aria-label="落地服务器管理表格">
        <div className="server-table-row server-table-head">
          <span>名称</span>
          <span>IP 地址</span>
          <span>端口</span>
          <span>状态</span>
          <span>操作</span>
        </div>
        {loading ? <div className="server-table-empty">正在加载服务器列表。</div> : null}
        {!loading && servers.length === 0 ? <div className="server-table-empty">暂无落地服务器记录。点击“添加落地服务器”开始。</div> : null}
        {!loading
          ? servers.map((server) => (
              <div className="server-table-group" key={server.id}>
                <div className="server-table-row">
                  <strong>{server.name || server.ip}</strong>
                  <span>{server.ip}</span>
                  <span>SSH {server.ssh_port}</span>
                  <span>
                    <span className={`pill ${statusClass(server.display_status)}`}>{displayStatusLabel(server.display_status)}</span>
                    <small className="node-share-status">直连节点：{server.nodes.length} 个</small>
                  </span>
                  <div className="server-actions">
                    <button
                      className="secondary"
                      title="自动预检并创建直连 Reality 节点"
                      type="button"
                      onClick={() => openNodePlan(server)}
                    >
                      创建直连节点
                    </button>
                    <button className="secondary" type="button" onClick={() => openWorkerCommand(server)}>
                      安装命令
                    </button>
                    <button className="secondary" type="button" onClick={() => openEdit(server)}>
                      编辑
                    </button>
                    <button className="danger" type="button" onClick={() => openDelete(server)}>
                      删除
                    </button>
                    <details className="server-advanced-actions">
                      <summary>高级读取与调试</summary>
                      <div className="server-advanced-actions-body">
                        <span>这些功能主要用于开发或排障。日常搭建网络时一般不需要展开。</span>
                        {server.worker_id ? (
                          <>
                            <button
                              className="secondary"
                              disabled={!server.worker_online || workerCommandLoadingId === server.worker_id}
                              title={!server.worker_online ? "Worker 未在线，不能创建检查命令" : "创建只读 Worker 检查命令"}
                              type="button"
                              onClick={() => void runWorkerCheck(server)}
                            >
                              Worker 检查
                            </button>
                            <button
                              className="secondary"
                              disabled={!server.worker_online || workerCommandLoadingId === server.worker_id}
                              title={!server.worker_online ? "Worker 未在线，不能创建只读预检命令" : "创建落地服务器只读预检命令"}
                              type="button"
                              onClick={() => void runLandingPreflight(server)}
                            >
                              只读预检
                            </button>
                          </>
                        ) : null}
                      </div>
                    </details>
                  </div>
                </div>
                {server.connection_mode === "worker" ? (
                  <div className="server-row-worker">
                    Worker：
                    {server.worker_display_status
                      ? displayStatusLabel(server.worker_display_status)
                      : server.worker_status
                        ? displayStatusLabel(server.worker_status)
                        : "未注册"}；主机名：
                    {server.worker_hostname || "暂无"}；网卡：{server.worker_interface_name || "暂无"}；最后心跳：
                    {formatTime(server.worker_last_heartbeat_at)}
                    {renderRecentWorkerCommand(latestWorkerCommandForServer(server))}
                  </div>
                ) : null}
                {server.last_ssh_error ? <div className="server-row-error">最近 SSH 失败原因：{server.last_ssh_error}</div> : null}
                {server.nodes.length > 0 ? (
                  <div className="server-node-rows">
                    {server.nodes.map((node) => (
                      <div className="server-table-row node-child-row" key={node.id}>
                        <span>
                          <strong>直连节点：{node.name}</strong>
                          <small className="node-meta-line">协议：{nodeProtocolSummary(node)}</small>
                        </span>
                        <span className="node-entry-label">入口：{nodeEntryLabel(node, server.ip)}</span>
                        <span className="node-config-status">配置：{node.share_link_present ? "可复制" : "未生成"}</span>
                        <span>
                          <span className={`pill ${statusClass(node.status)}`}>{nodeStatusLabel(node.status)}</span>
                          <small className="node-health-status">{nodeHealthSummary(node)}</small>
                          <small className="node-share-status">share_link：{node.share_link_present ? "已生成" : "未生成"}</small>
                        </span>
                        <span className="server-actions">
                          <button className="secondary" type="button" onClick={() => void openNodeDetail(node)}>
                            查看摘要
                          </button>
                          <button
                            className="secondary"
                            disabled={!node.share_link_present}
                            type="button"
                            onClick={() => void copyNodeShareLink(node)}
                          >
                            复制客户端链接
                          </button>
                          <button
                            className="secondary"
                            disabled={!node.share_link_present}
                            type="button"
                            onClick={() => void openNodeDetail(node, true)}
                          >
                            临时二维码
                          </button>
                          <button className="danger" type="button" onClick={() => openDeleteNode(server, node)}>
                            删除节点
                          </button>
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="server-node-empty">暂无下级节点。</div>
                )}
              </div>
            ))
          : null}
      </div>

      <div className="server-management-footer">
        <p className="message">{message}</p>
        <button className="secondary" type="button" onClick={() => void loadServers()}>
          刷新
        </button>
      </div>

      {modalMode ? renderModal() : null}
      {selectedNodeDetail ? renderNodeDetailModal() : null}
    </section>
  );

  function renderModal() {
    const mode = modalMode;
    if (!mode) {
      return null;
    }
    const titleMap: Record<Exclude<ModalMode, null>, string> = {
      add: "添加落地服务器",
      edit: "编辑落地服务器",
      delete: "确认删除",
      deleteNode: "确认删除",
      nodePlan: "创建直连节点",
      workerCommand: "重新生成 Worker 安装命令",
    };
    if (mode === "nodePlan") {
      return (
        <div className="modal-backdrop" role="presentation">
          <div className="modal-card node-create-modal" role="dialog" aria-modal="true" aria-label={titleMap[mode]}>
            <div className="modal-header node-create-modal-header">
              <div>
                <h3>{titleMap[mode]}</h3>
                <p className="message">创建成功后可复制 V2Ray 链接、临时显示二维码或下载二维码。</p>
              </div>
              <button
                aria-label="关闭创建直连节点弹窗"
                className="modal-close-button"
                type="button"
                onClick={() => void closeNodeCreateModal(nodeCreateStep === "complete")}
              >
                ×
              </button>
            </div>
            <div className="node-create-modal-body">{renderNodePlanForm()}</div>
            {renderNodeCreateFooterActions()}
          </div>
        </div>
      );
    }
    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card" role="dialog" aria-modal="true" aria-label={titleMap[mode]}>
          <div className="modal-header">
            <h3>{titleMap[mode]}</h3>
            <button className="ghost-button" type="button" onClick={closeModal}>
              取消
            </button>
          </div>
          {mode === "add" || mode === "workerCommand" ? renderWorkerBootstrapForm("landing") : null}
          {mode === "edit" ? renderServerForm(submitEdit) : null}
          {mode === "delete" ? renderDeleteConfirm() : null}
          {mode === "deleteNode" ? renderDeleteNodeConfirm() : null}
        </div>
      </div>
    );
  }

  function renderWorkerBootstrapForm(role: WorkerRole) {
    return (
      <div className="form server-modal-form worker-bootstrap-form">
        <div className="worker-bootstrap-intro wide-field">
          <strong>接入方式：Worker 安装命令</strong>
          <span>
            落地服务器使用 role = landing。点击生成后会先保存落地服务器记录，再生成绑定该记录的一次性安装命令。
          </span>
        </div>

        <label>
          服务器名称
          <input
            value={workerBootstrapForm.name}
            onChange={(event) => setWorkerBootstrapForm({ ...workerBootstrapForm, name: event.target.value })}
            placeholder="例如：美国落地服务器"
            readOnly={modalMode === "workerCommand"}
          />
        </label>

        <label>
          服务器 IP
          <input
            value={workerBootstrapForm.ip}
            onChange={(event) => setWorkerBootstrapForm({ ...workerBootstrapForm, ip: event.target.value })}
            placeholder="公网 IPv4"
            readOnly={modalMode === "workerCommand"}
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

        <label>
          网卡
          <input
            value={workerBootstrapForm.interfaceName}
            onChange={(event) => setWorkerBootstrapForm({ ...workerBootstrapForm, interfaceName: event.target.value })}
            placeholder="例如：ens17、eth0、enp1s0"
          />
        </label>

        <div className="warning-box wide-field">
          <strong>Worker 第一版安装说明</strong>
          <span>当前安装命令会安装真实 liveline-worker，并写入 systemd 服务。</span>
          <span>Worker 第一版只做注册、心跳和基础状态上报，不创建节点、不修改 Xray、不新增监听端口。</span>
          <span>生成命令必须先配置 PUBLIC_CONSOLE_URL；主控公网地址未配置时，远程 VPS 无法通过 localhost 访问安装脚本。</span>
          <span>安装完成后可使用 journalctl -u liveline-worker -f 查看日志。</span>
          <span>安装命令会使用上方填写的网卡名，例如 ens17、eth0、enp1s0。</span>
        </div>

        <div className="modal-actions wide-field">
          <button disabled={submitting} type="button" onClick={() => void generateWorkerInstallCommand(role)}>
            {submitting
              ? "生成中..."
              : modalMode === "add"
                ? "保存服务器并生成安装命令"
                : "重新生成安装命令"}
          </button>
          <button className="secondary" type="button" onClick={closeModal}>
            取消
          </button>
        </div>

        {workerTokenResult ? (
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
              请在 VPS 上先确认能访问主控地址。明文 token 只出现在这条一次性安装命令中。不要把命令写入 README、阶段文档、终端日志或 Git。
            </p>
            {workerInstallHeartbeatMessage ? <p className="message">{workerInstallHeartbeatMessage}</p> : null}
          </div>
        ) : (
          <p className="message wide-field">点击“生成安装命令”后，这里会显示一次性 curl | bash 命令和 token 过期时间。</p>
        )}
      </div>
    );
  }

  function renderServerForm(onSubmit: (event: React.FormEvent<HTMLFormElement>) => void) {
    return (
      <form className="form server-modal-form" onSubmit={onSubmit}>
        <label>
          落地服务器名称
          <input value={serverForm.name} onChange={(event) => setServerForm({ ...serverForm, name: event.target.value })} />
        </label>
        <label>
          落地服务器 IP
          <input value={serverForm.ip} onChange={(event) => setServerForm({ ...serverForm, ip: event.target.value })} />
        </label>
        <label>
          SSH 端口
          <input
            inputMode="numeric"
            value={serverForm.sshPort}
            onChange={(event) => setServerForm({ ...serverForm, sshPort: event.target.value })}
          />
        </label>
        <label>
          SSH 用户名
          <input value={serverForm.sshUser} onChange={(event) => setServerForm({ ...serverForm, sshUser: event.target.value })} />
        </label>
        <label className="wide-field">
          备注
          <textarea value={serverForm.notes} onChange={(event) => setServerForm({ ...serverForm, notes: event.target.value })} />
        </label>
        <p className="message wide-field">服务器远程检测和执行统一通过已注册 Worker；本页不再接收私钥或创建 SSH/RQ 任务。</p>
        <div className="modal-actions wide-field">
          <button disabled={submitting} type="submit">
            确认
          </button>
          <button className="secondary" type="button" onClick={closeModal}>
            取消
          </button>
        </div>
      </form>
    );
  }

  function renderDeleteConfirm() {
    if (!selectedServer) {
      return null;
    }
    const isOfflineLocalRemove = deleteMode === "offline_local_remove";
    return (
      <div className="delete-confirm">
        <p>确认删除该落地服务器？</p>
        <div className="server-delete-target">
          {selectedServer.name} / {selectedServer.ip} / 下级节点 {selectedServer.nodes.length} 个
        </div>
        <p className="message">删除方式：{isOfflineLocalRemove ? "离线本地移除" : "远程清理删除"}</p>
        <div className="modal-actions">
          <button className="secondary" type="button" onClick={closeModal}>
            取消
          </button>
          <button className="danger" disabled={submitting} type="button" onClick={() => void submitDelete()}>
            删除
          </button>
        </div>
      </div>
    );
  }

  function renderDeleteNodeConfirm() {
    if (!selectedServer || !selectedNodeForDelete) {
      return null;
    }
    const isOfflineLocalRemove = deleteMode === "offline_local_remove";
    return (
      <div className="delete-confirm">
        <p>确认删除该节点？</p>
        <div className="server-delete-target">
          {selectedNodeForDelete.name} / {nodeEntryLabel(selectedNodeForDelete, selectedServer.ip)}
        </div>
        <p className="message">删除方式：{isOfflineLocalRemove ? "离线本地移除" : "远程清理删除"}</p>
        <div className="modal-actions">
          <button className="secondary" type="button" onClick={closeModal}>
            取消
          </button>
          <button className="danger" disabled={submitting} type="button" onClick={() => void submitDeleteNode()}>
            删除
          </button>
        </div>
      </div>
    );
  }

  function blockedReasonLabel(reason: string) {
    const labels: Record<string, string> = {
      preflight_missing: "缺少成功的 landing_preflight 结果",
      worker_offline: "Worker 未在线",
      worker_not_command_capable: "Worker 版本不支持落地节点创建预案",
      interface_mismatch: "Worker 配置网卡与系统默认公网网卡不一致",
      port_already_listening: "计划端口已经监听",
      xray_existing_config_detected: "检测到已有 Xray 配置",
      missing_cloud_firewall_confirmation: "云安全组 / 云防火墙 / 服务器防火墙确认不完整",
      unsafe_port: "端口不安全或不可用于业务节点",
      approved_port_mismatch: "端口不符合本次审批的固定候选端口 27939/TCP",
      share_link_generation_not_approved: "未审批生成分享链接",
    };
    return labels[reason] ?? reason;
  }

  function renderNodePlanResult() {
    const steps = ["preflight_create", "preflight_running", "plan", "command_create", "command_running", "refresh", "complete"];
    const currentIndex = steps.indexOf(nodeCreateStep);
    return (
      <div className="landing-plan-result node-create-result wide-field">
        {nodeCreateStep !== "idle" ? (
          <div className={`plan-status-card ${nodeCreateStep === "failed" ? "blocked" : nodeCreateStep === "complete" ? "ready" : ""}`}>
            <strong>{NODE_CREATE_PROGRESS_LABELS[nodeCreateStep] ?? nodeCreateStep}</strong>
            <span>
              系统会先做只读预检，再创建 Reality 节点命令。只有远程创建成功、服务启动成功、端口监听成功后，后端才会写入
              node.share_link。
            </span>
          </div>
        ) : null}

        {nodeCreateStep !== "idle" && nodeCreateStep !== "failed" ? (
          <div className="node-create-progress" aria-label="直连节点创建进度">
            {steps.map((step, index) => (
              <span className={index < currentIndex ? "done" : index === currentIndex ? "current" : ""} key={step}>
                {NODE_CREATE_PROGRESS_LABELS[step]}
              </span>
            ))}
          </div>
        ) : null}

        {nodeCreateCommand ? (
          <div className="worker-command-panel">
            <strong>当前创建命令</strong>
            <span>命令 ID：{nodeCreateCommand.id}</span>
            <span>类型：{workerCommandTypeLabel(nodeCreateCommand.command_type)}</span>
            <span>状态：{workerCommandStatusLabel(nodeCreateCommand.status)}</span>
            {nodeCreateCommand.result_summary ? <span>{nodeCreateCommand.result_summary}</span> : null}
            {nodeCreateCommand.error_message ? <span>{nodeCreateCommand.error_message}</span> : null}
          </div>
        ) : null}

        {nodePlanResult ? (
          <div className={`plan-status-card ${nodePlanResult.ready ? "ready" : "blocked"}`}>
            <strong>{nodePlanResult.ready ? "创建计划通过" : "创建计划未通过"}</strong>
            <span>计划端口：{nodePlanResult.listen_port}/TCP</span>
            {nodePlanResult.blocked_reasons.length > 0 ? (
              <span>阻塞项：{nodePlanResult.blocked_reasons.map((reason) => blockedReasonLabel(reason)).join("；")}</span>
            ) : null}
          </div>
        ) : null}

        {nodeCreateError ? (
          <div className="failure-box">
            <strong>创建未完成</strong>
            <span>{nodeCreateError}</span>
            <span>请检查云安全组 TCP 端口、云防火墙、服务器本机防火墙，或换一个端口后重试。</span>
            <span>失败时不会写入 node.share_link，不会生成完整客户端链接。</span>
          </div>
        ) : null}

        {createdNodeSummary ? (
          <div className="node-create-success-card">
            <strong>直连节点已创建，可导入客户端</strong>
            <div className="landing-plan-grid">
              <span>节点名称</span>
              <strong>{createdNodeSummary.name}</strong>
              <span>入口</span>
              <strong>{nodeEntryLabel(createdNodeSummary, selectedServer?.ip ?? "")}</strong>
              <span>协议</span>
              <strong>{nodeProtocolSummary(createdNodeSummary)}</strong>
              <span>状态</span>
              <strong>{nodeStatusLabel(createdNodeSummary.status)}</strong>
            </div>
            <div className="modal-actions">
              <button className="secondary" type="button" onClick={() => void copyNodeShareLink(createdNodeSummary)}>
                复制 V2Ray 链接
              </button>
              <button className="secondary" type="button" onClick={() => void openNodeDetail(createdNodeSummary, true)}>
                显示二维码
              </button>
              <button className="secondary" type="button" onClick={() => void openNodeDetail(createdNodeSummary)}>
                查看节点摘要
              </button>
            </div>
            <small>Shadowrocket / V2RayN / V2RayNG 可通过完整链接或二维码导入。链接和二维码都属于敏感信息，仅自己使用。</small>
          </div>
        ) : null}

        {formalCreateResult ? (
          <div className="worker-command-panel">
            <strong>创建命令已提交</strong>
            <span>命令 ID：{formalCreateResult.command_id}</span>
            <span>目标 Worker：{formalCreateResult.target_worker_id}</span>
            <span>Worker 版本：{formalCreateResult.target_worker_version || "未返回"}</span>
          </div>
        ) : null}

        <div className="server-management-note">
          前端不会 console.log 完整分享链接；真实链接只允许在创建成功后的受控节点详情、复制或二维码区域查看。
        </div>
      </div>
    );
  }

  function renderNodeCreateFooterActions() {
    if (nodeCreateStep === "complete") {
      return (
        <div className="modal-actions node-create-modal-footer">
          <button className="success-button" type="button" onClick={() => void closeNodeCreateModal(true)}>
            完成并关闭
          </button>
        </div>
      );
    }
    if (nodeCreateStep === "failed") {
      return (
        <div className="modal-actions node-create-modal-footer">
          <button className="secondary" type="button" onClick={() => void closeNodeCreateModal(false)}>
            关闭
          </button>
          <button disabled={submitting || !nodePlanForm.protectedCreateConfirmed} form="node-create-form" type="submit">
            重新尝试
          </button>
        </div>
      );
    }
    return (
      <div className="modal-actions node-create-modal-footer">
        <button className="secondary" type="button" onClick={() => void closeNodeCreateModal(false)}>
          取消
        </button>
        <button disabled={submitting || !nodePlanForm.protectedCreateConfirmed} form="node-create-form" type="submit">
          {submitting ? "创建中..." : "创建"}
        </button>
      </div>
    );
  }

  function renderNodePlanForm() {
    if (!selectedServer) {
      return null;
    }
    return (
      <form
        className="form server-modal-form node-create-form"
        id="node-create-form"
        onSubmit={(event) => void submitSimplifiedLandingNodeCreate(event)}
      >
        <div className="worker-bootstrap-intro wide-field">
          <strong>创建直连 Reality 节点</strong>
          <span>填写必要信息后点击创建。系统会自动预检、安装 / 启动 Xray、检查受保护端口监听，成功后再允许导出链接和二维码。</span>
          <span>
            服务器：{selectedServer.name || selectedServer.ip} / {selectedServer.ip} / Worker：
            {selectedServer.worker_version || "未注册"}
          </span>
        </div>

        <label>
          节点名称
          <input
            value={nodePlanForm.nodeName}
            onChange={(event) => setNodePlanForm({ ...nodePlanForm, nodeName: event.target.value })}
            placeholder="liveline-reality-27939"
          />
        </label>
        <label>
          落地服务器
          <input readOnly value={`${selectedServer.name || selectedServer.ip} / ${selectedServer.ip}`} />
        </label>
        <label>
          当前正式创建端口
          <input readOnly value={`${APPROVED_FORMAL_LISTEN_PORT}/TCP`} />
          <small>请确认云安全组 / 云防火墙 / 服务器本机防火墙已放行该 TCP 端口。自定义端口能力后续单独进入 dynamic-port create stage。</small>
        </label>
        <label>
          Reality SNI / serverName
          <input
            value={nodePlanForm.serverName}
            onChange={(event) => setNodePlanForm({ ...nodePlanForm, serverName: event.target.value })}
          />
        </label>
        <label>
          Reality dest
          <input value={nodePlanForm.dest} onChange={(event) => setNodePlanForm({ ...nodePlanForm, dest: event.target.value })} />
        </label>
        <label>
          协议
          <input readOnly value="VLESS / Reality / TCP" />
        </label>

        <label className="node-create-confirm wide-field">
          <input
            type="checkbox"
            checked={nodePlanForm.protectedCreateConfirmed}
            onChange={(event) => setNodePlanForm({ ...nodePlanForm, protectedCreateConfirmed: event.target.checked })}
          />
          <span>
            我已确认 {APPROVED_FORMAL_LISTEN_PORT}/TCP 已在云安全组、云防火墙和服务器本机防火墙放行，并理解创建成功后会生成可用客户端链接。
          </span>
        </label>

        <details className="node-create-safety-details wide-field">
          <summary>高级安全说明</summary>
          <div className="node-create-safety-body">
            <span>系统不会自动修改云安全组、云防火墙或服务器本机防火墙；端口放行仍由用户自行确认。</span>
            <span>本阶段只简化创建体验，不扩展正式动态端口能力；正式创建仍使用当前后端受保护端口能力。</span>
            <span>如需支持自定义端口，后续需要单独进入 dynamic-port create stage，重新设计后端 / Worker 审批边界。</span>
            <span>创建前会自动运行 landing_preflight，确认端口未监听、Xray 未安装、且没有已有 LiveLine 管理配置。</span>
            <span>只有远程创建成功、Xray 服务启动成功、端口监听成功后，后端才允许写入 node.share_link。</span>
            <span>失败时不会写入 node.share_link，不会展示二维码，也不会生成可复制的完整链接。</span>
            <span>真实链接不得写入日志、文档、PR、测试快照或聊天。</span>
          </div>
        </details>

        {renderNodePlanResult()}
      </form>
    );
  }

  function renderNodeDetailModal() {
    if (!selectedNodeDetail) {
      return null;
    }
    const shareLink = exportedNodeShareLink ?? "";
    const shareLinkAvailable =
      selectedNodeDetail.has_share_link ?? selectedNodeDetail.share_link_present ?? Boolean(selectedNodeDetail.masked_share_link);
    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card node-detail-modal" role="dialog" aria-modal="true" aria-label="节点详情">
          <div className="modal-header">
            <div>
              <h3>{selectedNodeDetail.node_name}</h3>
              <p className="message">直连 Reality 节点摘要按需读取；完整客户端链接默认隐藏，不会修改 `node.share_link`。</p>
            </div>
            <button className="ghost-button" type="button" onClick={closeNodeDetail}>
              关闭
            </button>
          </div>

          {nodeDetailLoading ? <p className="message">正在读取节点详情。</p> : null}

          <div className="detail-grid">
            <span>节点名称</span>
            <strong>{selectedNodeDetail.node_name}</strong>
            <span>入口</span>
            <strong>
              {selectedNodeDetail.vps_ip ?? "-"}
              {selectedNodeDetail.port ? `:${selectedNodeDetail.port}` : ""}
            </strong>
            <span>协议 / 安全 / 传输</span>
            <strong>
              {selectedNodeDetail.protocol} / {selectedNodeDetail.security} / {selectedNodeDetail.transport ?? "tcp"}
            </strong>
            <span>状态</span>
            <strong>{nodeStatusLabel(selectedNodeDetail.status)}</strong>
            <span>服务状态</span>
            <strong>{selectedNodeDetail.service_display_label ?? selectedNodeDetail.service_status ?? "-"}</strong>
            <span>连接状态</span>
            <strong>{nodeConnectivityLabel(selectedNodeDetail)}</strong>
            <span>share_link 状态</span>
            <strong>
              {shareLinkAvailable
                ? `已生成 / 默认隐藏完整链接${selectedNodeDetail.share_link_length ? ` / ${selectedNodeDetail.share_link_length} 字符` : ""}`
                : "未生成"}
            </strong>
            <span>Reality serverName</span>
            <strong>{selectedNodeDetail.reality_server_name ?? "-"}</strong>
            <span>Reality publicKey</span>
            <strong>{selectedNodeDetail.masked_reality_public_key ?? "-"}</strong>
            <span>shortId</span>
            <strong>{selectedNodeDetail.masked_reality_short_id ?? "-"}</strong>
            <span>flow</span>
            <strong>{selectedNodeDetail.flow ?? "-"}</strong>
          </div>

          <div className="share-export">
            <label className="wide-field">
              客户端配置链接
              <textarea
                className="share-link-value"
                ref={nodeShareLinkRef}
                readOnly
                value={
                  shareLink
                    ? showFullShareLink
                      ? shareLink
                      : maskShareLink(shareLink)
                    : selectedNodeDetail.masked_share_link ?? ""
                }
              />
              <small>
                节点链接属于敏感信息；完整链接只在二次确认导出后临时用于复制、手动复制或二维码。
              </small>
            </label>

            <div className="node-actions export-actions">
              <button
                className="secondary"
                disabled={!shareLinkAvailable}
                type="button"
                onClick={() => void exportSelectedNodeShareLink(selectedNodeDetail.id, "client_import", { copy: true })}
              >
                复制客户端链接
              </button>
              <button
                className="secondary"
                disabled={!shareLinkAvailable}
                type="button"
                onClick={() => {
                  if (shareLink) {
                    setShowFullShareLink((current) => !current);
                    return;
                  }
                  void exportSelectedNodeShareLink(selectedNodeDetail.id, "temporary_reveal", { reveal: true });
                }}
              >
                {showFullShareLink ? "隐藏完整链接" : "临时查看链接"}
              </button>
              <button
                className="secondary"
                disabled={!shareLinkAvailable}
                type="button"
                onClick={() => {
                  if (shareLink) {
                    setShowNodeQrCode((current) => !current);
                    return;
                  }
                  void exportSelectedNodeShareLink(selectedNodeDetail.id, "qr_code", { showQr: true });
                }}
              >
                {showNodeQrCode ? "隐藏二维码" : "临时显示二维码"}
              </button>
            </div>

            {showNodeQrCode && shareLink ? (
              <div className="qr-panel">
                <div className="warning-box">
                  <div>二维码等同完整节点链接。</div>
                  <div>不要截图或发送给他人，泄露后别人可能使用该节点。</div>
                </div>
                <div className="qr-frame" ref={nodeQrFrameRef} aria-label="节点分享链接二维码">
                  <QRCode value={shareLink} size={220} />
                </div>
                <div className="modal-actions">
                  <button className="secondary" type="button" onClick={downloadNodeQrCode}>
                    下载二维码
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    );
  }
}
