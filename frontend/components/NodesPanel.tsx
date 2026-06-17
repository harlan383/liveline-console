"use client";

import { useEffect, useRef, useState } from "react";
import QRCode from "react-qr-code";
import {
  apiFetch,
  apiFormFetch,
  exportNodeShareLink,
  type CsrfResult,
  type NodeActionResult,
  type NodeData,
  type NodeListResult,
  type TaskData,
  type TaskLogData,
  type VpsActionResult,
} from "@/lib/api";

const terminalStatuses = new Set(["success", "failed", "cancelled", "timeout"]);

type NodesPanelProps = {
  onVpsReadyForRecreate?: (vpsId: string) => void;
};

function taskFailures(task: TaskData | null) {
  const failures = task?.result_data?.["failures"];
  return Array.isArray(failures) ? failures.filter((item) => typeof item === "string") : [];
}

function maskShareLink(shareLink: string) {
  if (shareLink.length <= 40) {
    return `${shareLink.slice(0, 12)}...`;
  }
  return `${shareLink.slice(0, 24)}...${shareLink.slice(-12)}`;
}

function backupFiles(task: TaskData | null) {
  if (task?.task_type !== "list_xray_backups") {
    return [];
  }
  const files = task.result_data?.["files"];
  return Array.isArray(files) ? files.filter((item) => item && typeof item === "object") : [];
}

function backupXray(task: TaskData | null) {
  if (task?.task_type !== "list_xray_backups") {
    return null;
  }
  const xray = task.result_data?.["xray"];
  return xray && typeof xray === "object" ? (xray as Record<string, unknown>) : null;
}

function cleanupPreviewSummary(task: TaskData | null) {
  if (task?.task_type !== "preview_xray_backup_cleanup") {
    return null;
  }
  const summary = task.result_data?.["summary"];
  return summary && typeof summary === "object" ? (summary as Record<string, unknown>) : null;
}

function cleanupPreviewXray(task: TaskData | null) {
  if (task?.task_type !== "preview_xray_backup_cleanup") {
    return null;
  }
  const xray = task.result_data?.["xray"];
  return xray && typeof xray === "object" ? (xray as Record<string, unknown>) : null;
}

function cleanupPreviewFiles(task: TaskData | null, key: "candidate_files" | "retained_files") {
  if (task?.task_type !== "preview_xray_backup_cleanup") {
    return [];
  }
  const files = task.result_data?.[key];
  return Array.isArray(files) ? files.filter((item) => item && typeof item === "object") : [];
}

function fileNameOf(file: Record<string, unknown> | null) {
  const name = file?.["name"];
  return typeof name === "string" ? name : "";
}

function removeFileFromPreview(task: TaskData | null, filename: string) {
  if (!task?.result_data || task.task_type !== "preview_xray_backup_cleanup") {
    return task;
  }
  const candidateFiles = Array.isArray(task.result_data["candidate_files"])
    ? task.result_data["candidate_files"].filter((item) => item && typeof item === "object")
    : [];
  const retainedFiles = Array.isArray(task.result_data["retained_files"])
    ? task.result_data["retained_files"].filter((item) => item && typeof item === "object")
    : [];
  const removed = candidateFiles.find((item) => fileNameOf(item as Record<string, unknown>) === filename) as
    | Record<string, unknown>
    | undefined;
  const nextCandidateFiles = candidateFiles.filter(
    (item) => fileNameOf(item as Record<string, unknown>) !== filename,
  );
  const summary =
    task.result_data["summary"] && typeof task.result_data["summary"] === "object"
      ? { ...(task.result_data["summary"] as Record<string, unknown>) }
      : {};
  const removedSize = typeof removed?.["size_bytes"] === "number" ? removed["size_bytes"] : 0;
  summary["total_files"] = Math.max(0, Number(summary["total_files"] ?? 0) - (removed ? 1 : 0));
  summary["total_size_bytes"] = Math.max(0, Number(summary["total_size_bytes"] ?? 0) - removedSize);
  summary["candidate_count"] = Math.max(0, nextCandidateFiles.length);
  summary["candidate_size_bytes"] = Math.max(
    0,
    Number(summary["candidate_size_bytes"] ?? 0) - removedSize,
  );
  summary["estimated_reclaim_bytes"] = Math.max(
    0,
    Number(summary["estimated_reclaim_bytes"] ?? 0) - removedSize,
  );
  summary["retained_count"] = retainedFiles.length;
  return {
    ...task,
    result_data: {
      ...task.result_data,
      summary,
      candidate_files: nextCandidateFiles,
      retained_files: retainedFiles,
    },
  };
}

function displayBoolean(value: unknown) {
  return value === true ? "是" : "否";
}

function displayBytes(value: unknown) {
  return typeof value === "number" ? `${value.toLocaleString()} B` : "-";
}

function displayDate(value: unknown) {
  return typeof value === "string" ? new Date(value).toLocaleString() : "-";
}

function statusLabel(status: string | undefined | null) {
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

function fileTypeLabel(value: unknown) {
  const type = typeof value === "string" ? value : "unknown";
  const labels: Record<string, string> = {
    current: "当前配置",
    backup: "备份文件",
    disabled: "已停用配置",
    failed: "failed 候选",
    unknown: "未知类型",
  };
  return labels[type] ?? type;
}

export function NodesPanel({ onVpsReadyForRecreate }: NodesPanelProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [selectedNode, setSelectedNode] = useState<NodeData | null>(null);
  const [privateKeyText, setPrivateKeyText] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [message, setMessage] = useState("节点列表会显示已创建的直连节点。");
  const [task, setTask] = useState<TaskData | null>(null);
  const [logs, setLogs] = useState<TaskLogData[]>([]);
  const [deleteConfirmVisible, setDeleteConfirmVisible] = useState(false);
  const [deleteConfirmName, setDeleteConfirmName] = useState("");
  const [showFullShareLink, setShowFullShareLink] = useState(false);
  const [showQrCode, setShowQrCode] = useState(false);
  const [exportedShareLink, setExportedShareLink] = useState<string | null>(null);
  const [cleanupPreviewTask, setCleanupPreviewTask] = useState<TaskData | null>(null);
  const [backupDeleteTarget, setBackupDeleteTarget] = useState<Record<string, unknown> | null>(null);
  const [backupDeleteConfirmName, setBackupDeleteConfirmName] = useState("");
  const [backupDeleteUnderstood, setBackupDeleteUnderstood] = useState(false);
  const [backupDeleteNotNeeded, setBackupDeleteNotNeeded] = useState(false);

  async function ensureCsrfToken() {
    const csrf = await apiFetch<CsrfResult>("/api/auth/csrf");
    if (!csrf.success) {
      throw new Error(csrf.message);
    }
    return csrf.data.csrf_token;
  }

  async function loadNodes(nextSelectedId?: string) {
    const result = await apiFetch<NodeListResult>("/api/nodes");
    if (!result.success) {
      setMessage(result.message);
      return;
    }
    setNodes(result.data.nodes);
    const listSelected =
      result.data.nodes.find((item) => item.id === nextSelectedId) ??
      result.data.nodes.find((item) => item.id === selectedNode?.id) ??
      result.data.nodes[0] ??
      null;
    if (!listSelected) {
      setSelectedNode(null);
      return;
    }
    if (selectedNode?.id === listSelected.id) {
      setSelectedNode(selectedNode);
      return;
    }
    await loadNode(listSelected.id);
  }

  async function loadNode(nodeId: string) {
    const result = await apiFetch<NodeData>(`/api/nodes/${nodeId}`);
    if (result.success) {
      setSelectedNode(result.data);
      setExportedShareLink(null);
      setShowFullShareLink(false);
      setShowQrCode(false);
    } else {
      setMessage(result.message);
    }
  }

  async function loadTask(taskId: string) {
    const [taskResult, logsResult] = await Promise.all([
      apiFetch<TaskData>(`/api/tasks/${taskId}`),
      apiFetch<{ logs: TaskLogData[] }>(`/api/tasks/${taskId}/logs`),
    ]);

    if (taskResult.success) {
      setTask(taskResult.data);
      if (taskResult.data.task_type === "preview_xray_backup_cleanup") {
        setCleanupPreviewTask(taskResult.data);
      }
      const taskMessage = taskResult.data.result_data?.["message"];
      if (typeof taskMessage === "string") {
        setMessage(taskMessage);
      } else if (taskResult.data.error_message) {
        setMessage(taskResult.data.error_message);
      }
      if (terminalStatuses.has(taskResult.data.status) && selectedNode) {
        if (taskResult.data.task_type === "delete_node" && taskResult.data.status === "success") {
          onVpsReadyForRecreate?.(selectedNode.vps_id);
          setSelectedNode(null);
          setDeleteConfirmVisible(false);
          setDeleteConfirmName("");
          await loadNodes();
        } else if (
          taskResult.data.task_type === "delete_xray_backup_candidate" &&
          taskResult.data.status === "success"
        ) {
          const file = taskResult.data.result_data?.["file"];
          const deletedFilename =
            file && typeof file === "object" ? fileNameOf(file as Record<string, unknown>) : "";
          if (deletedFilename) {
            setCleanupPreviewTask((current) => removeFileFromPreview(current, deletedFilename));
          }
          setBackupDeleteTarget(null);
          setBackupDeleteConfirmName("");
          setBackupDeleteUnderstood(false);
          setBackupDeleteNotNeeded(false);
          await loadNode(selectedNode.id);
          await loadNodes(selectedNode.id);
        } else {
          await loadNode(selectedNode.id);
          await loadNodes(selectedNode.id);
        }
      }
    } else {
      setMessage(taskResult.message);
    }

    if (logsResult.success) {
      setLogs(logsResult.data.logs);
    }
  }

  useEffect(() => {
    void loadNodes();
  }, []);

  useEffect(() => {
    setShowFullShareLink(false);
    setShowQrCode(false);
    setBackupDeleteTarget(null);
    setBackupDeleteConfirmName("");
    setBackupDeleteUnderstood(false);
    setBackupDeleteNotNeeded(false);
  }, [selectedNode?.id]);

  useEffect(() => {
    if (!task?.id || terminalStatuses.has(task.status)) {
      return;
    }

    const timer = window.setTimeout(() => {
      void loadTask(task.id);
    }, 2000);

    return () => window.clearTimeout(timer);
  }, [task]);

  function buildCredentialForm(extraFields?: Record<string, string>) {
    const formData = new FormData();
    formData.append("ssh_key_passphrase", passphrase);
    for (const [key, value] of Object.entries(extraFields ?? {})) {
      formData.append(key, value);
    }
    if (privateKeyText.trim()) {
      formData.append("private_key_text", privateKeyText);
    }
    const file = fileInputRef.current?.files?.[0];
    if (file) {
      formData.append("private_key_file", file);
    }
    return formData;
  }

  function clearCredentialInputs() {
    setPrivateKeyText("");
    setPassphrase("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  async function runNodeAction(action: "refresh" | "restart" | "delete") {
    if (!selectedNode) {
      setMessage("请先选择节点。");
      return;
    }

    const actionMessages = {
      refresh: ["正在创建刷新任务。", "刷新任务已创建。"],
      restart: ["正在创建重启任务。", "重启任务已创建。"],
      delete: ["正在创建节点软删除任务。", "节点软删除任务已创建。"],
    } as const;

    if (action === "delete") {
      if (deleteConfirmName.trim() !== selectedNode.node_name) {
        setMessage("确认节点名称不匹配。");
        return;
      }
      const confirmed = window.confirm(
        "确认删除该节点？当前客户端链接将失效，Xray 服务会停止，当前连接会中断。",
      );
      if (!confirmed) {
        return;
      }
    }

    try {
      setMessage(actionMessages[action][0]);
      const csrfToken = await ensureCsrfToken();
      const extraFields =
        action === "delete"
          ? {
              confirm: "true",
              confirm_node_name: deleteConfirmName.trim(),
            }
          : undefined;
      const result = await apiFormFetch<NodeActionResult>(
        `/api/nodes/${selectedNode.id}/${action}`,
        buildCredentialForm(extraFields),
        {
          headers: { "X-CSRF-Token": csrfToken },
        },
      );
      clearCredentialInputs();

      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }

      setMessage(actionMessages[action][1]);
      await loadTask(result.data.task_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "节点任务创建失败。");
    }
  }

  async function exportSelectedShareLink(
    reason: string,
    options: { copy?: boolean; reveal?: boolean; showQr?: boolean } = {},
  ) {
    if (!selectedNode || !(selectedNode.has_share_link ?? selectedNode.share_link_present ?? Boolean(selectedNode.masked_share_link))) {
      setMessage("没有可复制的分享链接。");
      return null;
    }
    const confirmed = window.confirm(
      "节点分享链接属于敏感信息，仅用于导入客户端。不要粘贴到聊天、PR、日志或文档中。确认继续导出吗？",
    );
    if (!confirmed) {
      return null;
    }
    const csrfToken = await ensureCsrfToken();
    const result = await exportNodeShareLink(selectedNode.id, csrfToken, reason);
    if (!result.success) {
      setMessage(`${result.error_code}: ${result.message}`);
      return null;
    }
    const link = result.data.share_link;
    setExportedShareLink(link);
    setShowFullShareLink(Boolean(options.reveal));
    setShowQrCode(Boolean(options.showQr));
    if (options.copy) {
      await navigator.clipboard.writeText(link);
      setMessage("节点链接已复制到剪贴板，请妥善保存，不要公开分享。");
    } else {
      setMessage("节点链接已临时导出，请勿公开分享。");
    }
    return link;
  }

  async function copyShareLink() {
    await exportSelectedShareLink("client_import", { copy: true });
  }

  async function runBackupScan() {
    if (!selectedNode) {
      setMessage("请先选择节点。");
      return;
    }

    try {
      setMessage("正在创建 Xray 备份文件查看任务。");
      const csrfToken = await ensureCsrfToken();
      const result = await apiFormFetch<VpsActionResult>(
        `/api/vps/${selectedNode.vps_id}/xray-backups`,
        buildCredentialForm(),
        {
          headers: { "X-CSRF-Token": csrfToken },
        },
      );
      clearCredentialInputs();

      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }

      setMessage("Xray 备份文件查看任务已创建。");
      await loadTask(result.data.task_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Xray 备份文件查看任务创建失败。");
    }
  }

  async function runCleanupPreview() {
    if (!selectedNode) {
      setMessage("请先选择节点。");
      return;
    }

    try {
      setMessage("正在创建 Xray 备份清理预览任务。");
      const csrfToken = await ensureCsrfToken();
      const result = await apiFormFetch<VpsActionResult>(
        `/api/vps/${selectedNode.vps_id}/xray-backups/cleanup-preview`,
        buildCredentialForm(),
        {
          headers: { "X-CSRF-Token": csrfToken },
        },
      );
      clearCredentialInputs();

      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }

      setMessage("Xray 备份清理预览任务已创建。");
      await loadTask(result.data.task_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Xray 备份清理预览任务创建失败。");
    }
  }

  async function runDeleteBackupCandidate() {
    if (!selectedNode || !backupDeleteTarget) {
      setMessage("请先选择 failed 候选文件。");
      return;
    }
    const filename = fileNameOf(backupDeleteTarget);
    if (!filename) {
      setMessage("候选文件名无效。");
      return;
    }
    if (backupDeleteConfirmName.trim() !== filename) {
      setMessage("确认文件名不匹配。");
      return;
    }
    if (!backupDeleteUnderstood || !backupDeleteNotNeeded) {
      setMessage("请勾选删除确认项。");
      return;
    }
    const confirmed = window.confirm("确认真实删除该远端 failed 备份文件？此操作不可撤销。");
    if (!confirmed) {
      return;
    }

    try {
      setMessage("正在创建 failed 备份候选文件删除任务。");
      const csrfToken = await ensureCsrfToken();
      const result = await apiFormFetch<VpsActionResult>(
        `/api/vps/${selectedNode.vps_id}/xray-backups/delete-candidate`,
        buildCredentialForm({
          filename,
          confirm: "true",
          confirm_filename: filename,
        }),
        {
          headers: { "X-CSRF-Token": csrfToken },
        },
      );
      clearCredentialInputs();

      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }

      setMessage("failed 备份候选文件删除任务已创建。");
      await loadTask(result.data.task_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "failed 备份候选文件删除任务创建失败。");
    }
  }

  const shareLink = exportedShareLink ?? "";
  const shareLinkAvailable = selectedNode
    ? selectedNode.has_share_link ?? selectedNode.share_link_present ?? Boolean(selectedNode.masked_share_link)
    : false;
  const selectedBackupTask =
    task?.task_type === "list_xray_backups" && task.vps_id === selectedNode?.vps_id ? task : null;
  const selectedCleanupPreviewTask =
    cleanupPreviewTask?.task_type === "preview_xray_backup_cleanup" &&
    cleanupPreviewTask.vps_id === selectedNode?.vps_id
      ? cleanupPreviewTask
      : null;
  const xrayBackupStatus = backupXray(selectedBackupTask);
  const xrayBackupFiles = backupFiles(selectedBackupTask);
  const cleanupStatus = cleanupPreviewXray(selectedCleanupPreviewTask);
  const cleanupSummary = cleanupPreviewSummary(selectedCleanupPreviewTask);
  const cleanupCandidateFiles = cleanupPreviewFiles(selectedCleanupPreviewTask, "candidate_files");
  const cleanupRetainedFiles = cleanupPreviewFiles(selectedCleanupPreviewTask, "retained_files");

  return (
    <section className="panel wide">
      <div className="status-row">
        <h2>节点列表</h2>
        <button className="secondary" type="button" onClick={() => void loadNodes()}>
          刷新列表
        </button>
      </div>

      {nodes.length > 0 ? (
        <div className="node-table">
          {nodes.map((node) => (
            <button
              className={`node-row-button ${selectedNode?.id === node.id ? "active" : ""}`}
              key={node.id}
              type="button"
              onClick={() => void loadNode(node.id)}
            >
              <span>{node.node_name}</span>
              <span>{node.vps_ip ?? "-"}</span>
              <span>{node.protocol}</span>
              <span>{node.port ?? "-"}</span>
              <span className={`pill ${node.status === "active" ? "ok" : "bad"}`}>{statusLabel(node.status)}</span>
              <span>{node.created_at ? new Date(node.created_at).toLocaleString() : "-"}</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="empty">还没有节点。创建直连节点后会显示在这里。</div>
      )}

      {selectedNode ? (
        <div className="node-detail">
          <h3>{selectedNode.node_name}</h3>
          <div className="detail-grid">
            <span>VPS IP</span>
            <strong>{selectedNode.vps_ip ?? "-"}</strong>
            <span>协议</span>
            <strong>{selectedNode.protocol}</strong>
            <span>端口</span>
            <strong>{selectedNode.port ?? "-"}</strong>
            <span>状态</span>
            <strong>{statusLabel(selectedNode.status)}</strong>
            <span>share_link 状态</span>
            <strong>
              {shareLinkAvailable
                ? `已生成 / 默认隐藏完整链接${selectedNode.share_link_length ? ` / ${selectedNode.share_link_length} 字符` : ""}`
                : "未生成"}
            </strong>
            <span>Reality serverName</span>
            <strong>{selectedNode.reality_server_name ?? "-"}</strong>
            <span>Reality publicKey</span>
            <strong>{selectedNode.masked_reality_public_key ?? "-"}</strong>
            <span>shortId</span>
            <strong>{selectedNode.masked_reality_short_id ?? "-"}</strong>
            <span>flow</span>
            <strong>{selectedNode.flow ?? "-"}</strong>
          </div>

          <div className="share-export">
            <label className="wide-field">
              分享链接
              <textarea
                className="share-link-value"
                readOnly
                value={
                  shareLink
                    ? showFullShareLink
                      ? shareLink
                      : maskShareLink(shareLink)
                    : selectedNode.masked_share_link ?? ""
                }
              />
              <small>完整链接需二次确认后临时导出；不要粘贴到聊天、PR、日志或文档中。</small>
            </label>

            <div className="node-actions export-actions">
              <button
                className="secondary"
                type="button"
                disabled={!shareLinkAvailable}
                onClick={() => void copyShareLink()}
              >
                导出并复制链接
              </button>
              <button
                className="secondary"
                type="button"
                disabled={!shareLinkAvailable}
                onClick={() => {
                  if (shareLink) {
                    setShowFullShareLink((current) => !current);
                    return;
                  }
                  void exportSelectedShareLink("temporary_reveal", { reveal: true });
                }}
              >
                {showFullShareLink ? "隐藏完整链接" : "显示完整链接"}
              </button>
              <button
                className="secondary"
                type="button"
                disabled={!shareLinkAvailable}
                onClick={() => {
                  if (shareLink) {
                    setShowQrCode((current) => !current);
                    return;
                  }
                  void exportSelectedShareLink("qr_code", { showQr: true });
                }}
              >
                {showQrCode ? "隐藏二维码" : "显示二维码"}
              </button>
            </div>

            {showQrCode && shareLink ? (
              <div className="qr-panel">
                <div className="warning-box">
                  <div>二维码等同完整节点链接。</div>
                  <div>不要截图发给别人，泄露后别人可能使用你的节点。</div>
                </div>
                <div className="qr-frame" aria-label="节点分享链接二维码">
                  <QRCode value={shareLink} size={220} />
                </div>
              </div>
            ) : null}

            <details className="client-import-help">
              <summary>客户端导入提示</summary>
              <ul>
                <li>通用：复制链接或扫描二维码，在客户端添加节点后测试连接。</li>
                <li>v2rayN：从剪贴板导入分享链接。</li>
                <li>v2rayNG：复制链接后从剪贴板导入，或扫码导入。</li>
                <li>Shadowrocket：扫描二维码或从剪贴板导入。</li>
                <li>Passwall：粘贴分享链接到节点导入区域。</li>
              </ul>
            </details>
          </div>

          <div className="node-actions">
            <button type="button" onClick={() => void runNodeAction("refresh")}>
              刷新状态
            </button>
            <button type="button" onClick={() => void runNodeAction("restart")}>
              重启 Xray
            </button>
          </div>

          <details className="backup-panel">
            <summary>Xray 备份文件</summary>
            <div className="warning-box">
              <div>本阶段只查看文件元数据，不展示配置内容。</div>
              <div>config.json 可能包含 Reality privateKey，不要把备份文件发给别人。</div>
              <div>恢复旧配置可能让旧链接重新可用；请不要在直播中恢复。</div>
            </div>
            <div className="backup-actions">
              <button className="secondary" type="button" onClick={() => void runBackupScan()}>
                查看备份文件
              </button>
              <button className="secondary" type="button" onClick={() => void runCleanupPreview()}>
                清理预览
              </button>
            </div>
            <div className="warning-box">
              <div>清理预览只是计算候选文件，不会删除文件。</div>
              <div>本阶段不会执行 rm、mv、cp，也不会修改 VPS 上的任何文件。</div>
            </div>

            {xrayBackupStatus ? (
              <div className="backup-status">
                <span>config.json 存在</span>
                <strong>{displayBoolean(xrayBackupStatus["config_exists"])}</strong>
                <span>xray.service 状态</span>
                <strong>{displayBoolean(xrayBackupStatus["service_active"])}</strong>
                <span>443 监听</span>
                <strong>{displayBoolean(xrayBackupStatus["port_443_listening"])}</strong>
              </div>
            ) : null}

            {xrayBackupFiles.length > 0 ? (
              <div className="backup-table">
                {xrayBackupFiles.map((file) => {
                  const data = file as Record<string, unknown>;
                  return (
                    <div className="backup-row" key={String(data["path"] ?? data["name"])}>
                      <strong>{String(data["name"] ?? "-")}</strong>
                      <span>{fileTypeLabel(data["type"])}</span>
                      <span>{displayBytes(data["size_bytes"])}</span>
                      <span>{displayDate(data["modified_at"])}</span>
                      <code>{String(data["path"] ?? "-")}</code>
                    </div>
                  );
                })}
              </div>
            ) : selectedBackupTask?.status === "success" ? (
              <div className="empty">未发现 config.json* 文件。</div>
            ) : null}

            {cleanupSummary ? (
              <div className="cleanup-preview">
                <h4>清理预览摘要</h4>
                <div className="backup-status cleanup-summary">
                  <span>总文件数</span>
                  <strong>{String(cleanupSummary["total_files"] ?? 0)}</strong>
                  <span>总大小</span>
                  <strong>{displayBytes(cleanupSummary["total_size_bytes"])}</strong>
                  <span>候选文件数</span>
                  <strong>{String(cleanupSummary["candidate_count"] ?? 0)}</strong>
                  <span>预计可回收</span>
                  <strong>{displayBytes(cleanupSummary["estimated_reclaim_bytes"])}</strong>
                  <span>保留文件数</span>
                  <strong>{String(cleanupSummary["retained_count"] ?? 0)}</strong>
                  <span>xray.service 状态</span>
                  <strong>{displayBoolean(cleanupStatus?.["service_active"])}</strong>
                  <span>443 监听</span>
                  <strong>{displayBoolean(cleanupStatus?.["port_443_listening"])}</strong>
                </div>

                <div className="cleanup-section">
                  <h4>候选文件</h4>
                  {cleanupCandidateFiles.length > 0 ? (
                    <div className="backup-table">
                      {cleanupCandidateFiles.map((file) => {
                        const data = file as Record<string, unknown>;
                        return (
                          <div className="backup-row cleanup-row" key={String(data["path"] ?? data["name"])}>
                            <strong>{String(data["name"] ?? "-")}</strong>
                            <span>{fileTypeLabel(data["type"])}</span>
                            <span>{displayBytes(data["size_bytes"])}</span>
                            <span>{displayDate(data["modified_at"])}</span>
                            <span>原因：{String(data["reason"] ?? "-")}</span>
                            <span>风险：{String(data["risk_level"] ?? "-")}</span>
                            {data["type"] === "failed" ? (
                              <button
                                className="danger"
                                type="button"
                                onClick={() => {
                                  setBackupDeleteTarget(data);
                                  setBackupDeleteConfirmName("");
                                  setBackupDeleteUnderstood(false);
                                  setBackupDeleteNotNeeded(false);
                                }}
                              >
                                删除候选文件
                              </button>
                            ) : (
                              <span>暂不支持删除</span>
                            )}
                            <code>{String(data["path"] ?? "-")}</code>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="empty">没有符合 dry-run 策略的清理候选文件。</div>
                  )}
                </div>

                <div className="cleanup-section">
                  <h4>保留文件</h4>
                  {cleanupRetainedFiles.length > 0 ? (
                    <div className="backup-table">
                      {cleanupRetainedFiles.map((file) => {
                        const data = file as Record<string, unknown>;
                        return (
                          <div className="backup-row cleanup-row" key={String(data["path"] ?? data["name"])}>
                            <strong>{String(data["name"] ?? "-")}</strong>
                            <span>{fileTypeLabel(data["type"])}</span>
                            <span>{displayBytes(data["size_bytes"])}</span>
                            <span>{displayDate(data["modified_at"])}</span>
                            <span>原因：{String(data["reason"] ?? "-")}</span>
                            <code>{String(data["path"] ?? "-")}</code>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="empty">没有保留文件。</div>
                  )}
                </div>
              </div>
            ) : null}

            {backupDeleteTarget ? (
              <div className="backup-delete-confirm">
                <div className="warning-box">
                  <div>这是真实远端文件删除操作，不可撤销。</div>
                  <div>本阶段只允许删除 failed 类型 dry-run 候选文件，不会删除 backup / disabled。</div>
                  <div>请在下方 SSH 私钥区域重新上传或粘贴 SSH Key 后再提交。</div>
                </div>
                <div className="detail-grid">
                  <span>文件名</span>
                  <strong>{String(backupDeleteTarget["name"] ?? "-")}</strong>
                  <span>路径</span>
                  <strong>{String(backupDeleteTarget["path"] ?? "-")}</strong>
                  <span>类型</span>
                  <strong>{fileTypeLabel(backupDeleteTarget["type"])}</strong>
                  <span>大小</span>
                  <strong>{displayBytes(backupDeleteTarget["size_bytes"])}</strong>
                  <span>修改时间</span>
                  <strong>{displayDate(backupDeleteTarget["modified_at"])}</strong>
                  <span>风险</span>
                  <strong>{String(backupDeleteTarget["risk_level"] ?? "-")}</strong>
                  <span>原因</span>
                  <strong>{String(backupDeleteTarget["reason"] ?? "-")}</strong>
                </div>
                <label>
                  输入完整文件名确认删除
                  <input
                    value={backupDeleteConfirmName}
                    onChange={(event) => setBackupDeleteConfirmName(event.target.value)}
                  />
                </label>
                <label className="check-row">
                  <input
                    checked={backupDeleteUnderstood}
                    type="checkbox"
                    onChange={(event) => setBackupDeleteUnderstood(event.target.checked)}
                  />
                  我理解这是远端文件删除操作
                </label>
                <label className="check-row">
                  <input
                    checked={backupDeleteNotNeeded}
                    type="checkbox"
                    onChange={(event) => setBackupDeleteNotNeeded(event.target.checked)}
                  />
                  我确认该文件不再需要
                </label>
                <div className="node-actions">
                  <button
                    className="danger"
                    type="button"
                    disabled={
                      backupDeleteConfirmName.trim() !== fileNameOf(backupDeleteTarget) ||
                      !backupDeleteUnderstood ||
                      !backupDeleteNotNeeded
                    }
                    onClick={() => void runDeleteBackupCandidate()}
                  >
                    确认删除 failed 候选文件
                  </button>
                  <button
                    className="secondary"
                    type="button"
                    onClick={() => {
                      setBackupDeleteTarget(null);
                      setBackupDeleteConfirmName("");
                      setBackupDeleteUnderstood(false);
                      setBackupDeleteNotNeeded(false);
                    }}
                  >
                    取消
                  </button>
                </div>
              </div>
            ) : null}

            <details className="restore-help">
              <summary>手动恢复说明</summary>
              <p className="message">
                这些命令需要人工 SSH 到 VPS 后执行；系统本阶段不会自动恢复。恢复旧配置可能让旧链接重新可用。
              </p>
              <pre className="manual-commands">{`# 1. 手动 SSH 到 VPS

# 2. 先备份当前配置
cp /usr/local/etc/xray/config.json /usr/local/etc/xray/config.json.manual-backup.<timestamp>

# 3. 复制目标备份为正式配置
cp /usr/local/etc/xray/config.json.bak.<timestamp> /usr/local/etc/xray/config.json

# 4. 测试配置
xray run -test -config /usr/local/etc/xray/config.json

# 5. 重启服务
systemctl restart xray

# 6. 验证
systemctl is-active xray
ss -ltnH | grep ':443'`}</pre>
            </details>
          </details>

          <div className="danger-zone">
            <div>
              <strong>危险操作区</strong>
              <p>删除后当前客户端链接将失效，Xray 服务会停止，当前连接会中断。请不要在直播中执行。</p>
            </div>
            {!deleteConfirmVisible ? (
              <button
                className="danger"
                type="button"
                onClick={() => {
                  setDeleteConfirmVisible(true);
                  setDeleteConfirmName("");
                }}
              >
                删除节点
              </button>
            ) : (
              <div className="delete-confirm">
                <label>
                  输入节点名称确认删除
                  <input
                    value={deleteConfirmName}
                    onChange={(event) => setDeleteConfirmName(event.target.value)}
                  />
                </label>
                <div className="node-actions">
                  <button
                    className="danger"
                    type="button"
                    disabled={deleteConfirmName.trim() !== selectedNode.node_name}
                    onClick={() => void runNodeAction("delete")}
                  >
                    确认删除节点
                  </button>
                  <button
                    className="secondary"
                    type="button"
                    onClick={() => {
                      setDeleteConfirmVisible(false);
                      setDeleteConfirmName("");
                    }}
                  >
                    取消
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="credential-grid">
            <label>
              上传 SSH 私钥
              <input ref={fileInputRef} type="file" />
            </label>
            <label>
              SSH Key Passphrase
              <input
                type="password"
                value={passphrase}
                onChange={(event) => setPassphrase(event.target.value)}
              />
            </label>
            <label className="wide-field">
              粘贴 SSH 私钥
              <textarea
                value={privateKeyText}
                onChange={(event) => setPrivateKeyText(event.target.value)}
              />
            </label>
          </div>
        </div>
      ) : null}

      <p className="message">{message}</p>

      {task ? (
        <div className="task-card">
          <div className="status-row">
            <div>
              <strong>任务状态</strong>
              <p className="message">
                {statusLabel(task.status)} / {task.current_step ?? "-"} / {task.progress}%
              </p>
            </div>
            <span className={`pill ${task.status === "success" ? "ok" : "bad"}`}>
              {task.error_code ?? statusLabel(task.status)}
            </span>
          </div>
          {taskFailures(task).length > 0 ? (
            <div className="failure-box">
              {taskFailures(task).map((failure) => (
                <div key={failure}>{failure}</div>
              ))}
            </div>
          ) : null}
          {task.result_data ? (
            <pre className="result-box">{JSON.stringify(task.result_data, null, 2)}</pre>
          ) : null}
          <div className="log-list">
            {logs.map((log) => (
              <div className="log-row" key={log.id}>
                <span>{log.level}</span>
                <span>{log.step ?? "-"}</span>
                <span>{log.message}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
