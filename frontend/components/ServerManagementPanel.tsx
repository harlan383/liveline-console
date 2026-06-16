"use client";

import { useEffect, useRef, useState } from "react";
import QRCode from "react-qr-code";

import {
  apiFetch,
  apiFormFetch,
  createLandingNodeExecution,
  createLandingNodePlan,
  createWorkerCommand,
  createVpsWorkerBootstrap,
  createWorkerToken,
  listWorkerCommands,
  type LandingNodePlanResponse,
  type LandingNodeCreateResponse,
  type CsrfResult,
  type NodeData,
  type VpsServerData,
  type VpsServerDeleteResult,
  type VpsServerListResult,
  type VpsServerTaskResult,
  type VpsServerUpdateResult,
  type WorkerCommandData,
  type WorkerRole,
  type WorkerTokenCreateResult,
} from "@/lib/api";

type ModalMode = "add" | "recheck" | "edit" | "delete" | "nodePlan" | "workerCommand" | null;

type ServerFormState = {
  name: string;
  ip: string;
  sshPort: string;
  sshUser: string;
  notes: string;
  privateKeyText: string;
  passphrase: string;
};

type NodePlanFormState = {
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
};

type FormalCreateConfirmState = {
  firewallOpen: boolean;
  installXray: boolean;
  createRealityNode: boolean;
  noExistingXray: boolean;
  listenPortApproved: boolean;
  generateShareLink: boolean;
  writeShareLinkAfterSuccess: boolean;
  rollbackNewArtifactsOnly: boolean;
};

type WorkerBootstrapFormState = {
  name: string;
  ip: string;
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
  privateKeyText: "",
  passphrase: "",
};

function createEmptyNodePlanForm(): NodePlanFormState {
  return {
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
  };
}

function createEmptyFormalCreateConfirm(): FormalCreateConfirmState {
  return {
    firewallOpen: false,
    installXray: false,
    createRealityNode: false,
    noExistingXray: false,
    listenPortApproved: false,
    generateShareLink: false,
    writeShareLinkAfterSuccess: false,
    rollbackNewArtifactsOnly: false,
  };
}

const emptyWorkerBootstrapForm: WorkerBootstrapFormState = {
  name: "",
  ip: "",
  expiresInMinutes: "60",
};

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
    offline: "离线",
    unchecked: "未检测",
    disabled: "已停用",
  };
  return labels[status] ?? sshStatusLabel(status);
}

function statusClass(status: string) {
  if (status === "online" || status === "active" || status === "success" || status === "worker_online") {
    return "ok";
  }
  if (status === "offline" || status === "deleted" || status === "failed" || status === "worker_offline") {
    return "bad";
  }
  if (status === "unchecked" || status === "pending" || status === "pending_worker") {
    return "warn";
  }
  return "muted";
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
  };
  return labels[status] ?? status;
}

function maskShareLink(shareLink: string) {
  if (shareLink.length <= 40) {
    return `${shareLink.slice(0, 12)}...`;
  }
  return `${shareLink.slice(0, 24)}...${shareLink.slice(-12)}`;
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
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const workerInstallCommandRef = useRef<HTMLTextAreaElement | null>(null);
  const [servers, setServers] = useState<VpsServerData[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("落地服务器管理只读取本地系统记录；不会在页面加载时执行 SSH。");
  const [modalMode, setModalMode] = useState<ModalMode>(null);
  const [selectedServer, setSelectedServer] = useState<VpsServerData | null>(null);
  const [serverForm, setServerForm] = useState<ServerFormState>(emptyServerForm);
  const [nodePlanForm, setNodePlanForm] = useState<NodePlanFormState>(() => createEmptyNodePlanForm());
  const [nodePlanResult, setNodePlanResult] = useState<LandingNodePlanResponse | null>(null);
  const [formalCreateConfirm, setFormalCreateConfirm] = useState<FormalCreateConfirmState>(() => createEmptyFormalCreateConfirm());
  const [formalCreateResult, setFormalCreateResult] = useState<LandingNodeCreateResponse | null>(null);
  const [workerBootstrapForm, setWorkerBootstrapForm] = useState<WorkerBootstrapFormState>(emptyWorkerBootstrapForm);
  const [workerTokenResult, setWorkerTokenResult] = useState<WorkerTokenCreateResult | null>(null);
  const [workerCommandsByWorkerId, setWorkerCommandsByWorkerId] = useState<Record<string, WorkerCommandData[]>>({});
  const [latestWorkerCommandByServerId, setLatestWorkerCommandByServerId] = useState<Record<string, WorkerCommandData>>({});
  const [workerCommandLoadingId, setWorkerCommandLoadingId] = useState<string | null>(null);
  const [selectedNodeDetail, setSelectedNodeDetail] = useState<NodeData | null>(null);
  const [nodeDetailLoading, setNodeDetailLoading] = useState(false);
  const [showFullShareLink, setShowFullShareLink] = useState(false);
  const [showNodeQrCode, setShowNodeQrCode] = useState(false);
  const [submitting, setSubmitting] = useState(false);

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
      setServers(result.data.servers);
      await Promise.all(
        result.data.servers
          .filter((server) => server.worker_id)
          .map((server) => loadWorkerCommands(server.worker_id as string, server.id)),
      );
      setMessage("服务器列表已刷新。");
    } else {
      setMessage(`${result.error_code}: ${result.message}`);
    }
    setLoading(false);
  }

  useEffect(() => {
    void loadServers();
  }, []);

  function clearFileInput() {
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  function closeModal() {
    setModalMode(null);
    setSelectedServer(null);
    setServerForm(emptyServerForm);
    setNodePlanForm(createEmptyNodePlanForm());
    setNodePlanResult(null);
    setFormalCreateConfirm(createEmptyFormalCreateConfirm());
    setFormalCreateResult(null);
    setWorkerBootstrapForm(emptyWorkerBootstrapForm);
    setWorkerTokenResult(null);
    clearFileInput();
  }

  function closeNodeDetail() {
    setSelectedNodeDetail(null);
    setShowFullShareLink(false);
    setShowNodeQrCode(false);
  }

  function openAddServer() {
    setServerForm(emptyServerForm);
    setWorkerBootstrapForm(emptyWorkerBootstrapForm);
    setWorkerTokenResult(null);
    setSelectedServer(null);
    setModalMode("add");
  }

  function openWorkerCommand(server: VpsServerData) {
    setSelectedServer(server);
    setWorkerBootstrapForm({
      name: server.name || server.ip,
      ip: server.ip,
      expiresInMinutes: "60",
    });
    setWorkerTokenResult(null);
    setModalMode("workerCommand");
  }

  function openRecheck(server: VpsServerData) {
    setSelectedServer(server);
    setServerForm({
      ...emptyServerForm,
      name: server.name,
      ip: server.ip,
      sshPort: String(server.ssh_port),
      sshUser: server.ssh_user || server.ssh_username || "root",
      notes: server.notes ?? "",
    });
    setModalMode("recheck");
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
    setModalMode("delete");
  }

  function openNodePlan(server: VpsServerData) {
    setSelectedServer(server);
    setNodePlanForm(createEmptyNodePlanForm());
    setNodePlanResult(null);
    setFormalCreateConfirm(createEmptyFormalCreateConfirm());
    setFormalCreateResult(null);
    setModalMode("nodePlan");
  }

  function appendPrivateKey(formData: FormData, text: string, passphrase: string) {
    if (text.trim()) {
      formData.append("private_key_text", text);
    }
    const file = fileInputRef.current?.files?.[0];
    if (file) {
      formData.append("private_key_file", file);
    }
    formData.append("ssh_key_passphrase", passphrase);
    formData.append("private_key_passphrase", passphrase);
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
    setSubmitting(true);
    setWorkerTokenResult(null);
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
              },
              csrfToken,
            )
          : await createVpsWorkerBootstrap(
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
      const tokenResult = "token" in result.data ? result.data.token : result.data;
      setWorkerTokenResult(tokenResult);
      setMessage(
        modalMode === "add"
          ? "落地服务器已保存为待接入，Worker 安装命令已生成。请在 VPS 上先确认能访问主控地址。"
          : "Worker 安装命令已重新生成。请在 VPS 上先确认能访问主控地址。",
      );
      await loadServers();
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
    setShowNodeQrCode(showQr && Boolean(detail.share_link));
    setMessage("节点详情已读取。完整分享链接默认隐藏。");
  }

  async function copyNodeShareLink(node: ServerNodeSummary) {
    if (!node.share_link_present) {
      setMessage("该节点还没有可复制的分享链接。");
      return;
    }
    const detail = await fetchNodeDetail(node.id);
    if (!detail?.share_link) {
      setMessage("该节点还没有可复制的分享链接。");
      return;
    }
    await navigator.clipboard.writeText(detail.share_link);
    setMessage("完整分享链接已复制。完整链接未写入页面默认展示。");
  }

  async function submitAddServer(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setMessage("正在添加服务器并创建 SSH 只读握手任务。");
    try {
      const csrfToken = await ensureCsrfToken();
      const formData = new FormData();
      formData.append("name", serverForm.name);
      formData.append("ip", serverForm.ip);
      formData.append("ssh_port", serverForm.sshPort);
      formData.append("ssh_user", serverForm.sshUser);
      formData.append("notes", serverForm.notes);
      appendPrivateKey(formData, serverForm.privateKeyText, serverForm.passphrase);

      const result = await apiFormFetch<VpsServerTaskResult>("/api/vps", formData, {
        headers: { "X-CSRF-Token": csrfToken },
      });

      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }

      setMessage(`服务器记录已创建，SSH 检测任务 ${result.data.task_id} 已排队。`);
      closeModal();
      await loadServers();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "添加服务器失败。");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitRecheck(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedServer) {
      return;
    }
    setSubmitting(true);
    setMessage("正在创建服务器重新检测任务。");
    try {
      const csrfToken = await ensureCsrfToken();
      const formData = new FormData();
      formData.append("ssh_port", serverForm.sshPort);
      formData.append("ssh_user", serverForm.sshUser);
      appendPrivateKey(formData, serverForm.privateKeyText, serverForm.passphrase);

      const result = await apiFormFetch<VpsServerTaskResult>(`/api/vps/${selectedServer.id}/recheck`, formData, {
        headers: { "X-CSRF-Token": csrfToken },
      });

      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }

      setMessage(`重新检测任务 ${result.data.task_id} 已排队。`);
      closeModal();
      await loadServers();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "重新检测失败。");
    } finally {
      setSubmitting(false);
    }
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
    if (!selectedServer) {
      return;
    }
    setSubmitting(true);
    setMessage("正在删除服务器系统记录。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await apiFetch<VpsServerDeleteResult>(`/api/vps/${selectedServer.id}?confirm=true`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": csrfToken },
      });

      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }

      setMessage(
        `服务器系统记录已删除；同时处理下级节点 ${result.data.affected_nodes} 个；未清理远程服务器配置。`,
      );
      closeModal();
      await loadServers();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "删除服务器失败。");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitLandingNodePlan(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedServer) {
      return;
    }
    const listenPort = Number(nodePlanForm.listenPort);
    if (!Number.isInteger(listenPort) || listenPort < 1 || listenPort > 65535) {
      setMessage("计划监听端口必须是 1-65535 之间的整数。");
      return;
    }
    if (listenPort !== APPROVED_FORMAL_LISTEN_PORT) {
      setMessage(`Stage 3.3.36 的正式审批候选端口固定为 ${APPROVED_FORMAL_LISTEN_PORT}/TCP，本阶段不会为其他端口生成执行计划。`);
      return;
    }
    if (BLOCKED_NODE_LISTEN_PORTS.has(listenPort)) {
      setMessage(`端口 ${listenPort} 是常用 / 保留端口，不能作为本次落地节点候选监听端口。请改用 10000-30000 中未被保留的 TCP 端口。`);
      return;
    }
    setSubmitting(true);
    setNodePlanResult(null);
    setMessage("正在生成落地节点 dry-run 创建计划；不会执行远程命令。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await createLandingNodePlan(
        selectedServer.id,
        {
          listen_port: listenPort,
          protocol: nodePlanForm.protocol,
          security: nodePlanForm.security,
          flow: nodePlanForm.flow,
          server_name: nodePlanForm.serverName,
          dest: nodePlanForm.dest,
          remark: nodePlanForm.remark || null,
          allow_install_xray: nodePlanForm.allowInstallXray,
          allow_modify_firewall: nodePlanForm.allowModifyFirewall,
          allow_generate_share_link: nodePlanForm.allowGenerateShareLink,
          allow_overwrite_existing_config: nodePlanForm.allowOverwriteExistingConfig,
          cloud_security_group_confirmed: nodePlanForm.cloudSecurityGroupConfirmed,
          cloud_firewall_confirmed: nodePlanForm.cloudFirewallConfirmed,
          server_firewall_confirmed: nodePlanForm.serverFirewallConfirmed,
          require_manual_cloud_firewall_confirmation: true,
          require_preflight_success: nodePlanForm.requirePreflightSuccess,
        },
        csrfToken,
      );
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setNodePlanResult(result.data);
      setMessage(
        result.data.ready
          ? "dry-run 计划已生成：当前只表示可进入下一阶段审批，不会创建真实节点。"
          : `dry-run 计划已生成：存在 ${result.data.blocked_reasons.length} 个阻塞项，不能进入真实创建。`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "生成落地节点创建计划失败。");
    } finally {
      setSubmitting(false);
    }
  }

  function allFormalCreateConfirmationsChecked() {
    return Object.values(formalCreateConfirm).every(Boolean);
  }

  async function submitFormalLandingNodeCreate() {
    if (!selectedServer) {
      return;
    }
    if (!nodePlanResult?.ready) {
      setMessage("必须先生成 Ready 的 dry-run / execution guard 计划。");
      return;
    }
    if (!allFormalCreateConfirmationsChecked()) {
      setMessage("正式创建前必须完成全部二次确认。");
      return;
    }
    setSubmitting(true);
    setFormalCreateResult(null);
    setMessage("正在创建正式落地节点 Worker 命令；真实执行由审批锁定的 Worker 轮询处理。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await createLandingNodeExecution(
        selectedServer.id,
        {
          approved_port: APPROVED_FORMAL_LISTEN_PORT,
          confirm_firewall_open: formalCreateConfirm.firewallOpen,
          confirm_generate_share_link: formalCreateConfirm.generateShareLink,
          confirm_write_share_link_after_success: formalCreateConfirm.writeShareLinkAfterSuccess,
          confirm_no_existing_xray: formalCreateConfirm.noExistingXray,
          confirm_rollback_new_artifacts_only: formalCreateConfirm.rollbackNewArtifactsOnly,
        },
        csrfToken,
      );
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setFormalCreateResult(result.data);
      setLatestWorkerCommandByServerId((current) => ({ ...current, [selectedServer.id]: result.data.command }));
      setMessage(
        `正式创建 Worker 命令已创建：${result.data.command_id}。真实链接不会写入命令结果、日志或聊天记录。`,
      );
      await loadWorkerCommands(result.data.target_worker_id, selectedServer.id);
      await loadServers();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "创建正式落地节点命令失败。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel wide server-management-panel">
      <div className="server-management-header">
        <div>
          <h2>落地服务器</h2>
          <p className="message">管理本地系统中的落地服务器记录和下级节点摘要。页面加载不会执行 SSH 或远程命令。</p>
        </div>
        <button type="button" onClick={openAddServer}>
          添加落地服务器
        </button>
      </div>

      <div className="server-management-note">
        share_link 仅显示是否存在；本页面不允许修改 `node.share_link`。删除落地服务器只处理系统记录，不清理远程 Xray / 节点配置。
      </div>

      <details className="route-safety-guardrail collapsible-notice server-node-merge-notice" aria-label="节点合并说明">
        <summary className="route-safety-summary">
          <div className="route-safety-heading">
            <span>安全提示</span>
            <strong>查看节点合并说明</strong>
          </div>
          <span className="notice-toggle-text">
            <span className="when-closed">查看说明</span>
            <span className="when-open">收起说明</span>
          </span>
        </summary>
        <div className="route-safety-body">
          <ul className="route-safety-list">
            <li>节点已合并到落地服务器页，节点属于某一台服务器。</li>
            <li>左侧不再提供独立节点菜单，节点详情、复制链接和二维码从服务器下级节点行进入。</li>
            <li>share_link 只在用户明确点击查看或复制时展示 / 复制，默认不暴露完整链接。</li>
            <li>本阶段不修改 node.share_link、不创建真实节点、不新增监听端口、不执行正式 cutover。</li>
            <li>后续新增或变更节点监听端口时，必须同步检查云服务器安全组 / 云防火墙 / 服务器防火墙是否放行对应 TCP 端口。</li>
          </ul>
        </div>
      </details>

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
                  <span className={`pill ${statusClass(server.display_status)}`}>{displayStatusLabel(server.display_status)}</span>
                  <div className="server-actions">
                    <button
                      className="secondary"
                      title="只生成 dry-run 创建计划，不创建真实节点"
                      type="button"
                      onClick={() => openNodePlan(server)}
                    >
                      创建节点计划
                    </button>
                    {server.connection_mode === "worker" ? (
                      <button className="secondary" type="button" onClick={() => openWorkerCommand(server)}>
                        安装命令
                      </button>
                    ) : (
                      <button className="secondary" type="button" onClick={() => openRecheck(server)}>
                        重新检测
                      </button>
                    )}
                    <button className="secondary" type="button" onClick={() => openEdit(server)}>
                      编辑
                    </button>
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
                    <button className="danger" type="button" onClick={() => openDelete(server)}>
                      删除
                    </button>
                  </div>
                </div>
                {server.connection_mode === "worker" ? (
                  <div className="server-row-worker">
                    Worker：{server.worker_status ? displayStatusLabel(server.worker_status) : "未注册"}；主机名：
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
                          └ {node.name}
                          <small className="node-meta-line">协议：{node.protocol}</small>
                        </span>
                        <span>{node.ip || node.address || server.ip}</span>
                        <span>节点 {node.port ?? "-"}</span>
                        <span>
                          <span className={`pill ${statusClass(node.status)}`}>{nodeStatusLabel(node.status)}</span>
                          <small className="node-share-status">share_link：{node.share_link_present ? "已生成" : "未生成"}</small>
                        </span>
                        <span className="server-actions">
                          <button className="secondary" type="button" onClick={() => void openNodeDetail(node)}>
                            查看
                          </button>
                          <button
                            className="secondary"
                            disabled={!node.share_link_present}
                            type="button"
                            onClick={() => void copyNodeShareLink(node)}
                          >
                            复制
                          </button>
                          <button
                            className="secondary"
                            disabled={!node.share_link_present}
                            type="button"
                            onClick={() => void openNodeDetail(node, true)}
                          >
                            二维码
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
      recheck: "重新检测落地服务器",
      edit: "编辑落地服务器",
      delete: "删除落地服务器",
      nodePlan: "创建落地节点计划",
      workerCommand: "重新生成 Worker 安装命令",
    };
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
          {mode === "recheck" ? renderServerForm(submitRecheck, true, true) : null}
          {mode === "edit" ? renderServerForm(submitEdit, false) : null}
          {mode === "delete" ? renderDeleteConfirm() : null}
          {mode === "nodePlan" ? renderNodePlanForm() : null}
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

        <div className="warning-box wide-field">
          <strong>Worker 第一版安装说明</strong>
          <span>当前安装命令会安装真实 liveline-worker，并写入 systemd 服务。</span>
          <span>Worker 第一版只做注册、心跳和基础状态上报，不创建节点、不修改 Xray、不新增监听端口。</span>
          <span>生成命令必须先配置 PUBLIC_CONSOLE_URL；主控公网地址未配置时，远程 VPS 无法通过 localhost 访问安装脚本。</span>
          <span>安装完成后可使用 journalctl -u liveline-worker -f 查看日志。</span>
          <span>如果服务器网卡不是 eth0，请根据实际网卡名修改，例如 ens3、ens5、enp1s0。</span>
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
          </div>
        ) : (
          <p className="message wide-field">点击“生成安装命令”后，这里会显示一次性 curl | bash 命令和 token 过期时间。</p>
        )}
      </div>
    );
  }

  function renderServerForm(
    onSubmit: (event: React.FormEvent<HTMLFormElement>) => void,
    includeKeyFields: boolean,
    recheckOnly = false,
  ) {
    return (
      <form className="form server-modal-form" onSubmit={onSubmit}>
        {!recheckOnly ? (
          <label>
            落地服务器名称
            <input value={serverForm.name} onChange={(event) => setServerForm({ ...serverForm, name: event.target.value })} />
          </label>
        ) : null}
        {!recheckOnly ? (
          <label>
            落地服务器 IP
            <input value={serverForm.ip} onChange={(event) => setServerForm({ ...serverForm, ip: event.target.value })} />
          </label>
        ) : null}
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
        {!recheckOnly ? (
          <label className="wide-field">
            备注
            <textarea value={serverForm.notes} onChange={(event) => setServerForm({ ...serverForm, notes: event.target.value })} />
          </label>
        ) : null}
        {includeKeyFields ? (
          <>
            <label>
              上传 SSH 私钥
              <input ref={fileInputRef} type="file" />
            </label>
            <label className="wide-field">
              粘贴 SSH 私钥
              <textarea
                value={serverForm.privateKeyText}
                onChange={(event) => setServerForm({ ...serverForm, privateKeyText: event.target.value })}
              />
            </label>
            <label>
              私钥密码，可选
              <input
                type="password"
                value={serverForm.passphrase}
                onChange={(event) => setServerForm({ ...serverForm, passphrase: event.target.value })}
              />
            </label>
          </>
        ) : null}
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
    return (
      <div className="delete-confirm">
        <div className="failure-box">
          <strong>危险操作二次确认</strong>
          <span>将删除落地服务器系统记录，并将该服务器下未删除节点标记为 deleted。</span>
          <span>不会 SSH 登录远程服务器，不会清理远程 Xray 或节点配置。</span>
        </div>
        <div className="server-delete-target">
          {selectedServer.name} / {selectedServer.ip} / 下级节点 {selectedServer.nodes.length} 个
        </div>
        <div className="modal-actions">
          <button className="danger" disabled={submitting} type="button" onClick={() => void submitDelete()}>
            确认删除系统记录
          </button>
          <button className="secondary" type="button" onClick={closeModal}>
            取消
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

  function planValue(value: unknown) {
    if (value === null || value === undefined || value === "") {
      return "未返回";
    }
    if (typeof value === "boolean") {
      return value ? "是" : "否";
    }
    return String(value);
  }

  function renderNodePlanResult() {
    if (!nodePlanResult) {
      return null;
    }
    const summary = nodePlanResult.preflight_summary ?? {};
    const workerInterface = summary.worker_config_interface ?? summary.configured_interface;
    const defaultInterface = summary.default_route_interface ?? summary.detected_default_interface;
    return (
      <div className="landing-plan-result wide-field">
        <div className={`plan-status-card ${nodePlanResult.ready ? "ready" : "blocked"}`}>
          <strong>{nodePlanResult.ready ? "Ready for approval" : "No-Go / 仍有阻塞项"}</strong>
          <span>plan_id：{nodePlanResult.plan_id}</span>
          <span>下一阶段：{nodePlanResult.next_stage_required}</span>
        </div>

        <div className="landing-plan-grid">
          <span>Worker 版本</span>
          <strong>{planValue(summary.worker_version)}</strong>
          <span>预检状态</span>
          <strong>{planValue(summary.preflight_status)}</strong>
          <span>配置网卡</span>
          <strong>{planValue(workerInterface)}</strong>
          <span>默认公网网卡</span>
          <strong>{planValue(defaultInterface)}</strong>
          <span>默认公网网关</span>
          <strong>{planValue(summary.default_route_gateway)}</strong>
          <span>公网网卡 IP</span>
          <strong>{planValue(summary.primary_interface_ip)}</strong>
          <span>网卡是否不一致</span>
          <strong>{planValue(summary.interface_mismatch)}</strong>
          <span>监听端口数量</span>
          <strong>{planValue(summary.listening_count)}</strong>
          <span>Xray 是否已安装</span>
          <strong>{planValue(summary.xray_installed)}</strong>
          <span>已有 Xray 配置</span>
          <strong>{planValue(summary.xray_existing_config_detected)}</strong>
        </div>

        {nodePlanResult.blocked_reasons.length > 0 ? (
          <div className="failure-box">
            <strong>阻塞项</strong>
            {nodePlanResult.blocked_reasons.map((reason) => (
              <span key={reason}>{blockedReasonLabel(reason)}</span>
            ))}
          </div>
        ) : null}

        {nodePlanResult.warnings.length > 0 ? (
          <div className="warning-box">
            <strong>风险提示</strong>
            {nodePlanResult.warnings.map((warning) => (
              <span key={warning}>{warning}</span>
            ))}
          </div>
        ) : null}

        <div className="warning-box">
          <strong>下一步审批清单</strong>
          {nodePlanResult.required_user_confirmations.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>

        <div className="failure-box">
          <strong>正式执行保护清单</strong>
          {nodePlanResult.execution_guard.map((item) => (
            <span key={item}>{item}</span>
          ))}
          <span>只有完成下面全部二次确认后，才允许创建正式 Worker 执行命令。</span>
        </div>

        <div className="landing-plan-checklist formal-create-checklist">
          <strong>正式创建二次确认</strong>
          <label>
            <input
              type="checkbox"
              checked={formalCreateConfirm.firewallOpen}
              onChange={(event) => setFormalCreateConfirm({ ...formalCreateConfirm, firewallOpen: event.target.checked })}
            />
            已确认云安全组 / 云防火墙 / 服务器本机防火墙均已放行 27939/TCP
          </label>
          <label>
            <input
              type="checkbox"
              checked={formalCreateConfirm.installXray}
              onChange={(event) => setFormalCreateConfirm({ ...formalCreateConfirm, installXray: event.target.checked })}
            />
            允许本次正式执行安装 Xray-core
          </label>
          <label>
            <input
              type="checkbox"
              checked={formalCreateConfirm.createRealityNode}
              onChange={(event) => setFormalCreateConfirm({ ...formalCreateConfirm, createRealityNode: event.target.checked })}
            />
            允许本次正式执行创建 VLESS Reality 落地节点
          </label>
          <label>
            <input
              type="checkbox"
              checked={formalCreateConfirm.listenPortApproved}
              onChange={(event) => setFormalCreateConfirm({ ...formalCreateConfirm, listenPortApproved: event.target.checked })}
            />
            允许本次正式执行监听 27939/TCP
          </label>
          <label>
            <input
              type="checkbox"
              checked={formalCreateConfirm.noExistingXray}
              onChange={(event) => setFormalCreateConfirm({ ...formalCreateConfirm, noExistingXray: event.target.checked })}
            />
            已确认正式执行前仍需复核 Xray 未安装且无已有 Xray 配置
          </label>
          <label>
            <input
              type="checkbox"
              checked={formalCreateConfirm.generateShareLink}
              onChange={(event) => setFormalCreateConfirm({ ...formalCreateConfirm, generateShareLink: event.target.checked })}
            />
            允许生成真实分享链接，但不写入文档、日志或聊天
          </label>
          <label>
            <input
              type="checkbox"
              checked={formalCreateConfirm.writeShareLinkAfterSuccess}
              onChange={(event) => setFormalCreateConfirm({ ...formalCreateConfirm, writeShareLinkAfterSuccess: event.target.checked })}
            />
            允许在创建成功、Xray 启动成功、端口监听成功后写入 node.share_link
          </label>
          <label>
            <input
              type="checkbox"
              checked={formalCreateConfirm.rollbackNewArtifactsOnly}
              onChange={(event) => setFormalCreateConfirm({ ...formalCreateConfirm, rollbackNewArtifactsOnly: event.target.checked })}
            />
            如失败，只允许清理本次新增内容，不删除非 LiveLine 管理文件
          </label>
          <button
            className="danger"
            disabled={submitting || !nodePlanResult.ready || !allFormalCreateConfirmationsChecked()}
            type="button"
            onClick={() => void submitFormalLandingNodeCreate()}
          >
            {submitting ? "创建命令中..." : "正式创建落地节点"}
          </button>
          <small>该按钮只创建 Worker 命令；Worker 会先重新预检。命令结果不会默认展示完整分享链接。</small>
        </div>

        {formalCreateResult ? (
          <div className="worker-command-panel">
            <strong>正式创建命令已创建</strong>
            <span>命令 ID：{formalCreateResult.command_id}</span>
            <span>目标 Worker：{formalCreateResult.target_worker_id}</span>
            <span>Worker 版本：{formalCreateResult.target_worker_version || "未返回"}</span>
            <span>状态：{workerCommandStatusLabel(formalCreateResult.status)}</span>
            <span>{formalCreateResult.next_action}</span>
            {formalCreateResult.safety_boundary.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
        ) : null}

        <div className="server-management-note">
          前端不会 console.log 完整分享链接；真实链接只允许在创建成功后的受控节点详情 / 复制区域查看。
        </div>

        <div className="server-management-note">
          dry-run 计划本身只用于审批准备；只有上方二次确认全部完成并点击正式创建后，才会创建 Worker 执行命令。
        </div>
      </div>
    );
  }

  function renderNodePlanForm() {
    if (!selectedServer) {
      return null;
    }
    return (
      <form className="form server-modal-form" onSubmit={(event) => void submitLandingNodePlan(event)}>
        <div className="worker-bootstrap-intro wide-field">
          <strong>创建落地节点计划 / dry-run</strong>
          <span>本弹窗只生成审批计划，不安装 Xray、不创建节点、不开放端口、不修改防火墙、不生成真实节点链接。</span>
          <span>
            服务器：{selectedServer.name || selectedServer.ip} / {selectedServer.ip} / Worker：
            {selectedServer.worker_version || "未注册"}
          </span>
        </div>

        <label>
          计划监听端口
          <input
            inputMode="numeric"
            readOnly
            value={nodePlanForm.listenPort}
            onChange={(event) => setNodePlanForm({ ...nodePlanForm, listenPort: event.target.value })}
          />
          <small>Stage 3.3.36 候选端口固定为 27939/TCP，本阶段只生成审批计划。</small>
        </label>
        <label>
          协议
          <select value={nodePlanForm.protocol} onChange={(event) => setNodePlanForm({ ...nodePlanForm, protocol: event.target.value })}>
            <option value="vless">VLESS</option>
          </select>
        </label>
        <label>
          安全类型
          <select value={nodePlanForm.security} onChange={(event) => setNodePlanForm({ ...nodePlanForm, security: event.target.value })}>
            <option value="reality">Reality</option>
          </select>
        </label>
        <label>
          flow
          <select value={nodePlanForm.flow} onChange={(event) => setNodePlanForm({ ...nodePlanForm, flow: event.target.value })}>
            <option value="xtls-rprx-vision">xtls-rprx-vision</option>
          </select>
        </label>
        <label>
          Reality serverName
          <input value={nodePlanForm.serverName} onChange={(event) => setNodePlanForm({ ...nodePlanForm, serverName: event.target.value })} />
        </label>
        <label>
          Reality dest
          <input value={nodePlanForm.dest} onChange={(event) => setNodePlanForm({ ...nodePlanForm, dest: event.target.value })} />
        </label>
        <label className="wide-field">
          备注，可选
          <textarea value={nodePlanForm.remark} onChange={(event) => setNodePlanForm({ ...nodePlanForm, remark: event.target.value })} />
        </label>

        <div className="landing-plan-checklist wide-field">
          <label>
            <input
              type="checkbox"
              checked={nodePlanForm.cloudSecurityGroupConfirmed}
              onChange={(event) => setNodePlanForm({ ...nodePlanForm, cloudSecurityGroupConfirmed: event.target.checked })}
            />
            已确认云服务器安全组会放行计划 TCP 端口
          </label>
          <label>
            <input
              type="checkbox"
              checked={nodePlanForm.cloudFirewallConfirmed}
              onChange={(event) => setNodePlanForm({ ...nodePlanForm, cloudFirewallConfirmed: event.target.checked })}
            />
            已确认云防火墙会放行计划 TCP 端口
          </label>
          <label>
            <input
              type="checkbox"
              checked={nodePlanForm.serverFirewallConfirmed}
              onChange={(event) => setNodePlanForm({ ...nodePlanForm, serverFirewallConfirmed: event.target.checked })}
            />
            已确认服务器本机防火墙会放行计划 TCP 端口
          </label>
          <label>
            <input
              type="checkbox"
              checked={nodePlanForm.allowInstallXray}
              onChange={(event) => setNodePlanForm({ ...nodePlanForm, allowInstallXray: event.target.checked })}
            />
            仅用于计划：后续审批允许安装 Xray-core
          </label>
          <label>
            <input
              type="checkbox"
              checked={nodePlanForm.allowModifyFirewall}
              onChange={(event) => setNodePlanForm({ ...nodePlanForm, allowModifyFirewall: event.target.checked })}
            />
            仅用于计划：后续审批允许修改服务器本机防火墙
          </label>
          <label>
            <input
              type="checkbox"
              checked={nodePlanForm.allowGenerateShareLink}
              onChange={(event) => setNodePlanForm({ ...nodePlanForm, allowGenerateShareLink: event.target.checked })}
            />
            仅用于计划：后续审批允许生成分享链接，本阶段不生成真实链接
          </label>
          <label>
            <input
              type="checkbox"
              checked={nodePlanForm.allowOverwriteExistingConfig}
              onChange={(event) => setNodePlanForm({ ...nodePlanForm, allowOverwriteExistingConfig: event.target.checked })}
            />
            仅用于计划：如发现已有 Xray 配置，后续审批允许覆盖
          </label>
          <label>
            <input
              type="checkbox"
              checked={nodePlanForm.requirePreflightSuccess}
              onChange={(event) => setNodePlanForm({ ...nodePlanForm, requirePreflightSuccess: event.target.checked })}
            />
            要求已有成功 landing_preflight 结果
          </label>
        </div>

        <div className="warning-box wide-field">
          <strong>端口和安全组提醒</strong>
          <span>候选端口固定为 27939/TCP，用户已确认云安全组 / 云防火墙 / 服务器本机防火墙放行该端口。</span>
          <span>禁止使用常用 / 保留端口：22、80、443、8080、8443、18443、3000、3200、8000、8200、5432、6379、15432、16379、10000、27017。</span>
          <span>正式创建前仍必须重新运行 landing_preflight，确认 27939/TCP 未监听，Xray 未安装，且当前无已有 Xray 配置。</span>
        </div>

        <div className="failure-box wide-field">
          <strong>正式执行保护清单</strong>
          <span>27939/TCP 已确认放行。</span>
          <span>正式执行前必须重新预检。</span>
          <span>27939/TCP 当前必须未监听。</span>
          <span>Xray 当前必须未安装。</span>
          <span>当前必须无已有 Xray 配置。</span>
          <span>只有创建成功、Xray 服务启动成功、端口监听成功后才能写入 node.share_link。</span>
          <span>真实链接不得写入日志、文档或聊天。</span>
          <span>失败回滚只清理本次新增内容。</span>
        </div>

        <div className="failure-box wide-field">
          <strong>当前阶段不会执行</strong>
          <span>不会执行 SSH / 远程命令，不会安装 Xray，不会创建节点，不会开放端口，不会修改防火墙。</span>
          <span>不会生成完整节点链接，不会修改 node.share_link，不会执行 cutover。</span>
          <span>正式创建必须进入 Stage 3.3.37-formal-landing-node-create-execution。</span>
        </div>

        <div className="modal-actions wide-field">
          <button disabled={submitting} type="submit">
            {submitting ? "生成中..." : "生成 dry-run 计划"}
          </button>
          <button className="secondary" type="button" onClick={closeModal}>
            取消
          </button>
        </div>

        {renderNodePlanResult()}
      </form>
    );
  }

  function renderNodeDetailModal() {
    if (!selectedNodeDetail) {
      return null;
    }
    const shareLink = selectedNodeDetail.share_link ?? "";
    return (
      <div className="modal-backdrop" role="presentation">
        <div className="modal-card node-detail-modal" role="dialog" aria-modal="true" aria-label="节点详情">
          <div className="modal-header">
            <div>
              <h3>{selectedNodeDetail.node_name}</h3>
              <p className="message">节点详情按需读取；完整 share_link 默认隐藏，不会修改 `node.share_link`。</p>
            </div>
            <button className="ghost-button" type="button" onClick={closeNodeDetail}>
              关闭
            </button>
          </div>

          {nodeDetailLoading ? <p className="message">正在读取节点详情。</p> : null}

          <div className="detail-grid">
            <span>节点名称</span>
            <strong>{selectedNodeDetail.node_name}</strong>
            <span>VPS IP / 服务器 IP</span>
            <strong>{selectedNodeDetail.vps_ip ?? "-"}</strong>
            <span>协议</span>
            <strong>{selectedNodeDetail.protocol}</strong>
            <span>端口</span>
            <strong>{selectedNodeDetail.port ?? "-"}</strong>
            <span>状态</span>
            <strong>{nodeStatusLabel(selectedNodeDetail.status)}</strong>
            <span>share_link 状态</span>
            <strong>{shareLink ? "已生成 / 默认隐藏完整链接" : "未生成"}</strong>
            <span>Reality serverName</span>
            <strong>{selectedNodeDetail.reality_server_name ?? "-"}</strong>
            <span>Reality publicKey</span>
            <strong>{selectedNodeDetail.reality_public_key ?? "-"}</strong>
            <span>shortId</span>
            <strong>{selectedNodeDetail.reality_short_id ?? "-"}</strong>
            <span>flow</span>
            <strong>{selectedNodeDetail.flow ?? "-"}</strong>
          </div>

          <div className="share-export">
            <label className="wide-field">
              分享链接
              <textarea
                className="share-link-value"
                readOnly
                value={shareLink ? (showFullShareLink ? shareLink : maskShareLink(shareLink)) : ""}
              />
            </label>

            <div className="node-actions export-actions">
              <button
                className="secondary"
                disabled={!shareLink}
                type="button"
                onClick={() => void navigator.clipboard.writeText(shareLink).then(() => setMessage("完整分享链接已复制。"))}
              >
                复制完整链接
              </button>
              <button
                className="secondary"
                disabled={!shareLink}
                type="button"
                onClick={() => setShowFullShareLink((current) => !current)}
              >
                {showFullShareLink ? "隐藏完整链接" : "显示完整链接"}
              </button>
              <button
                className="secondary"
                disabled={!shareLink}
                type="button"
                onClick={() => setShowNodeQrCode((current) => !current)}
              >
                {showNodeQrCode ? "隐藏二维码" : "显示二维码"}
              </button>
            </div>

            {showNodeQrCode && shareLink ? (
              <div className="qr-panel">
                <div className="warning-box">
                  <div>二维码等同完整节点链接。</div>
                  <div>不要截图或发送给他人，泄露后别人可能使用该节点。</div>
                </div>
                <div className="qr-frame" aria-label="节点分享链接二维码">
                  <QRCode value={shareLink} size={220} />
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    );
  }
}
