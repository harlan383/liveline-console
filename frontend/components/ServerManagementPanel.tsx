"use client";

import { useEffect, useRef, useState } from "react";
import QRCode from "react-qr-code";

import {
  apiFetch,
  apiFormFetch,
  createWorkerToken,
  type CsrfResult,
  type NodeData,
  type ReadNodeResult,
  type VpsServerData,
  type VpsServerDeleteResult,
  type VpsServerListResult,
  type VpsServerTaskResult,
  type VpsServerUpdateResult,
  type WorkerRole,
  type WorkerTokenCreateResult,
} from "@/lib/api";

type ModalMode = "add" | "recheck" | "edit" | "delete" | "node" | null;

type ServerFormState = {
  name: string;
  ip: string;
  sshPort: string;
  sshUser: string;
  notes: string;
  privateKeyText: string;
  passphrase: string;
};

type NodeFormState = {
  nodeName: string;
  ip: string;
  port: string;
  protocol: string;
  privateKeyText: string;
  passphrase: string;
};

type WorkerBootstrapFormState = {
  name: string;
  expiresInMinutes: string;
};

type ServerNodeSummary = VpsServerData["nodes"][number];

const emptyServerForm: ServerFormState = {
  name: "",
  ip: "",
  sshPort: "22",
  sshUser: "root",
  notes: "",
  privateKeyText: "",
  passphrase: "",
};

const emptyNodeForm: NodeFormState = {
  nodeName: "直连 Reality 节点",
  ip: "",
  port: "443",
  protocol: "VLESS Reality",
  privateKeyText: "",
  passphrase: "",
};

const emptyWorkerBootstrapForm: WorkerBootstrapFormState = {
  name: "",
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

function statusClass(status: string) {
  if (status === "online" || status === "active" || status === "success") {
    return "ok";
  }
  if (status === "offline" || status === "deleted" || status === "failed") {
    return "bad";
  }
  if (status === "unchecked" || status === "pending") {
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

function maskShareLink(shareLink: string) {
  if (shareLink.length <= 40) {
    return `${shareLink.slice(0, 12)}...`;
  }
  return `${shareLink.slice(0, 24)}...${shareLink.slice(-12)}`;
}

export function ServerManagementPanel() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [servers, setServers] = useState<VpsServerData[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("落地服务器管理只读取本地系统记录；不会在页面加载时执行 SSH。");
  const [modalMode, setModalMode] = useState<ModalMode>(null);
  const [selectedServer, setSelectedServer] = useState<VpsServerData | null>(null);
  const [serverForm, setServerForm] = useState<ServerFormState>(emptyServerForm);
  const [nodeForm, setNodeForm] = useState<NodeFormState>(emptyNodeForm);
  const [workerBootstrapForm, setWorkerBootstrapForm] = useState<WorkerBootstrapFormState>(emptyWorkerBootstrapForm);
  const [workerTokenResult, setWorkerTokenResult] = useState<WorkerTokenCreateResult | null>(null);
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
    setNodeForm(emptyNodeForm);
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

  function openAddNode(server: VpsServerData) {
    if (server.last_ssh_status !== "online") {
      setMessage("离线或未检测服务器不能添加节点。请先重新检测 SSH 状态。");
      return;
    }
    setSelectedServer(server);
    setNodeForm({
      ...emptyNodeForm,
      ip: server.ip,
      nodeName: `${server.name || server.ip} Reality 节点`,
    });
    setModalMode("node");
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
    const expiresInMinutes = Number(workerBootstrapForm.expiresInMinutes);
    if (!Number.isInteger(expiresInMinutes) || expiresInMinutes < 1 || expiresInMinutes > 10080) {
      setMessage("过期时间必须是 1 到 10080 分钟之间的整数。");
      return;
    }
    setSubmitting(true);
    setWorkerTokenResult(null);
    setMessage("正在生成一次性 Worker 安装命令。");
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await createWorkerToken(
        {
          role,
          name: workerBootstrapForm.name.trim() || null,
          expires_in_minutes: expiresInMinutes,
        },
        csrfToken,
      );
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setWorkerTokenResult(result.data);
      setMessage("Worker 安装命令已生成。明文 token 仅包含在本次安装命令中。");
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
    await navigator.clipboard.writeText(workerTokenResult.install_command);
    setMessage("Worker 安装命令已复制。请勿把该命令写入文档、日志或 Git。");
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

  async function submitAddNode(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedServer) {
      return;
    }
    if (selectedServer.last_ssh_status !== "online") {
      setMessage("服务器不在线，不能添加节点。");
      return;
    }
    setSubmitting(true);
    setMessage("正在创建直连节点任务。");
    try {
      const csrfToken = await ensureCsrfToken();
      const formData = new FormData();
      formData.append("vps_id", selectedServer.id);
      formData.append("node_name", nodeForm.nodeName);
      formData.append("listen_port", nodeForm.port);
      formData.append("reality_server_name", "www.microsoft.com");
      formData.append("reality_dest", "www.microsoft.com:443");
      appendPrivateKey(formData, nodeForm.privateKeyText, nodeForm.passphrase);

      const result = await apiFormFetch<ReadNodeResult>("/api/nodes/create-direct", formData, {
        headers: { "X-CSRF-Token": csrfToken },
      });

      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }

      setMessage(`节点创建任务 ${result.data.task_id} 已排队。任务成功后刷新列表即可看到下级节点。`);
      closeModal();
      await loadServers();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "添加节点失败。");
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
                  <span className={`pill ${statusClass(server.last_ssh_status)}`}>{sshStatusLabel(server.last_ssh_status)}</span>
                  <div className="server-actions">
                    <button
                      className="secondary"
                      disabled={server.last_ssh_status !== "online"}
                      title={server.last_ssh_status !== "online" ? "离线 / 未检测服务器禁止添加节点" : "添加节点"}
                      type="button"
                      onClick={() => openAddNode(server)}
                    >
                      添加节点
                    </button>
                    <button className="secondary" type="button" onClick={() => openRecheck(server)}>
                      重新检测
                    </button>
                    <button className="secondary" type="button" onClick={() => openEdit(server)}>
                      编辑
                    </button>
                    <button className="danger" type="button" onClick={() => openDelete(server)}>
                      删除
                    </button>
                  </div>
                </div>
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
      node: "添加节点",
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
          {mode === "add" ? renderWorkerBootstrapForm("landing") : null}
          {mode === "recheck" ? renderServerForm(submitRecheck, true, true) : null}
          {mode === "edit" ? renderServerForm(submitEdit, false) : null}
          {mode === "delete" ? renderDeleteConfirm() : null}
          {mode === "node" ? renderNodeForm() : null}
        </div>
      </div>
    );
  }

  function renderWorkerBootstrapForm(role: WorkerRole) {
    return (
      <div className="form server-modal-form worker-bootstrap-form">
        <div className="worker-bootstrap-intro wide-field">
          <strong>接入方式：Worker 安装命令</strong>
          <span>落地服务器使用 role = landing。前端默认不再显示 SSH 添加表单，SSH 源码和现有 API 仍保留。</span>
        </div>

        <label>
          服务器名称，可选
          <input
            value={workerBootstrapForm.name}
            onChange={(event) => setWorkerBootstrapForm({ ...workerBootstrapForm, name: event.target.value })}
            placeholder="例如：美国落地服务器"
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
          <span>安装完成后可使用 journalctl -u liveline-worker -f 查看日志。</span>
          <span>如果服务器网卡不是 eth0，请根据实际网卡名修改，例如 ens3、ens5、enp1s0。</span>
        </div>

        <div className="modal-actions wide-field">
          <button disabled={submitting} type="button" onClick={() => void generateWorkerInstallCommand(role)}>
            {submitting ? "生成中..." : "生成安装命令"}
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
              <textarea className="worker-install-command" readOnly value={workerTokenResult.install_command} />
            </label>
            <div className="modal-actions">
              <button className="secondary" type="button" onClick={() => void copyInstallCommand()}>
                复制命令
              </button>
            </div>
            <p className="message">
              明文 token 只出现在这条一次性安装命令中。不要把命令写入 README、阶段文档、终端日志或 Git。
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

  function renderNodeForm() {
    if (!selectedServer) {
      return null;
    }
    return (
      <form className="form server-modal-form" onSubmit={(event) => void submitAddNode(event)}>
        <label>
          节点名称
          <input value={nodeForm.nodeName} onChange={(event) => setNodeForm({ ...nodeForm, nodeName: event.target.value })} />
        </label>
        <label>
          IP 地址
          <input readOnly value={nodeForm.ip} />
        </label>
        <label>
          端口
          <input inputMode="numeric" value={nodeForm.port} onChange={(event) => setNodeForm({ ...nodeForm, port: event.target.value })} />
        </label>
        <label>
          协议
          <select value={nodeForm.protocol} onChange={(event) => setNodeForm({ ...nodeForm, protocol: event.target.value })}>
            <option value="VLESS Reality">VLESS Reality</option>
          </select>
        </label>
        <label>
          上传 SSH 私钥
          <input ref={fileInputRef} type="file" />
        </label>
        <label>
          私钥密码，可选
          <input
            type="password"
            value={nodeForm.passphrase}
            onChange={(event) => setNodeForm({ ...nodeForm, passphrase: event.target.value })}
          />
        </label>
        <label className="wide-field">
          粘贴 SSH 私钥
          <textarea value={nodeForm.privateKeyText} onChange={(event) => setNodeForm({ ...nodeForm, privateKeyText: event.target.value })} />
        </label>
        <div className="warning-box wide-field">
          <span>添加节点会显式提交现有节点创建流程；不会修改 `node.share_link`，也不是正式 cutover。</span>
          <span>新增或变更监听端口后，请同步检查云服务器安全组 / 云防火墙 / 服务器防火墙是否放行对应 TCP 端口。</span>
          <span>离线 / 未检测服务器不可添加节点。SSH 私钥只通过临时凭据传递，不保存明文。</span>
        </div>
        <div className="modal-actions wide-field">
          <button disabled={submitting} type="submit">
            创建节点任务
          </button>
          <button className="secondary" type="button" onClick={closeModal}>
            取消
          </button>
        </div>
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
