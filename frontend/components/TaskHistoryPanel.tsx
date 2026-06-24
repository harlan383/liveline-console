"use client";

import { useEffect, useMemo, useState } from "react";

import { apiFetch, type TaskData, type TaskListResult, type TaskLogData } from "@/lib/api";

const terminalStatuses = new Set(["success", "completed", "failed", "cancelled", "timeout"]);
const secretKeyPattern = /(private|private_key|passphrase|password|passwd|secret|token|cookie|session|admin_password_hash|ssh_key)/i;
const linkPattern = /(vless|vmess|trojan|ss):\/\//i;
const privateKeyPattern = /BEGIN (OPENSSH|RSA|EC|DSA)? ?PRIVATE KEY/i;

function shortId(id: string) {
  return id.length > 12 ? `${id.slice(0, 8)}...${id.slice(-4)}` : id;
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "-";
}

function statusClass(status: string) {
  if (status === "success" || status === "completed") {
    return "ok";
  }
  if (terminalStatuses.has(status)) {
    return "bad";
  }
  return "warn";
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: "等待中",
    running: "运行中",
    success: "成功",
    completed: "成功",
    failed: "失败",
    cancelled: "已取消",
    timeout: "超时",
    unknown: "未知",
  };
  return labels[status] ?? status;
}

function redactString(value: string) {
  if (privateKeyPattern.test(value)) {
    return "[redacted private key]";
  }
  if (linkPattern.test(value)) {
    const protocol = value.match(linkPattern)?.[1] ?? "node";
    return `[redacted ${protocol} link]`;
  }
  if (value.length > 180) {
    return `${value.slice(0, 140)}... [truncated]`;
  }
  return value;
}

function sanitizeValue(value: unknown, key = "", depth = 0): unknown {
  if (secretKeyPattern.test(key)) {
    return "[redacted]";
  }
  if (value === null || value === undefined) {
    return value;
  }
  if (typeof value === "string") {
    return redactString(value);
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return value;
  }
  if (depth >= 4) {
    return "[nested data truncated]";
  }
  if (Array.isArray(value)) {
    const visible = value.slice(0, 8).map((item) => sanitizeValue(item, key, depth + 1));
    return value.length > 8 ? [...visible, `[${value.length - 8} more item(s) truncated]`] : visible;
  }
  if (typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([childKey, childValue]) => [
        childKey,
        sanitizeValue(childValue, childKey, depth + 1),
      ]),
    );
  }
  return "[unsupported value]";
}

function taskFailureSummary(task: TaskData) {
  if (task.status !== "failed" && !task.error_code && !task.error_message) {
    return "无失败信息。";
  }

  const source = `${task.error_code ?? ""} ${task.error_message ?? ""} ${task.current_step ?? ""}`.toLowerCase();
  if (source.includes("ssh") || source.includes("banner") || source.includes("authentication")) {
    return "SSH 连接、协议握手或认证失败。";
  }
  if (source.includes("port") || source.includes("listen") || source.includes("listening")) {
    return "端口监听、端口占用或监听验证异常。";
  }
  if (source.includes("process") || source.includes("service") || source.includes("systemd")) {
    return "远端进程或 systemd 服务状态异常。";
  }
  if (source.includes("health")) {
    return "本地健康检查异常。";
  }
  if (source.includes("auth") || source.includes("csrf") || source.includes("login")) {
    return "认证、登录状态或 CSRF 校验异常。";
  }
  if (source.includes("required") || source.includes("missing") || source.includes("invalid")) {
    return "参数缺失或参数格式不符合要求。";
  }
  return task.error_message ? redactString(task.error_message) : "未知错误。";
}

function resultSummary(task: TaskData) {
  if (!task.result_data) {
    return "暂无 result_data。";
  }
  return JSON.stringify(sanitizeValue(task.result_data), null, 2);
}

function logOutput(log: TaskLogData) {
  if (!log.raw_output) {
    return null;
  }
  return redactString(log.raw_output);
}

export function TaskHistoryPanel() {
  const [tasks, setTasks] = useState<TaskData[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [logs, setLogs] = useState<TaskLogData[]>([]);
  const [message, setMessage] = useState("正在读取本地任务记录。");
  const [loading, setLoading] = useState(false);
  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) ?? tasks[0] ?? null,
    [selectedTaskId, tasks],
  );

  async function loadTasks(nextSelectedId?: string | null) {
    setLoading(true);
    try {
      const result = await apiFetch<TaskListResult>("/api/tasks?limit=30");
      if (!result.success) {
        setMessage(result.message);
        return;
      }
      setTasks(result.data.tasks);
      setSelectedTaskId(
        nextSelectedId ??
          selectedTaskId ??
          result.data.tasks[0]?.id ??
          null,
      );
      setMessage(result.data.tasks.length > 0 ? "任务记录已刷新。" : "当前没有任务记录。");
    } catch {
      setMessage("无法读取任务记录。");
    } finally {
      setLoading(false);
    }
  }

  async function loadLogs(taskId: string) {
    const result = await apiFetch<{ logs: TaskLogData[] }>(`/api/tasks/${taskId}/logs`);
    if (result.success) {
      setLogs(result.data.logs);
    } else {
      setLogs([]);
      setMessage(result.message);
    }
  }

  useEffect(() => {
    void loadTasks();
  }, []);

  useEffect(() => {
    if (!selectedTask?.id) {
      setLogs([]);
      return;
    }
    void loadLogs(selectedTask.id);
  }, [selectedTask?.id]);

  return (
    <section className="panel wide">
      <div className="status-row">
        <div>
          <h2>本地任务记录</h2>
        </div>
        <button className="secondary" disabled={loading} type="button" onClick={() => void loadTasks()}>
          刷新任务记录
        </button>
      </div>

      {tasks.length === 0 ? (
        <div className="empty">暂无任务记录。执行已授权的本地流程后，任务摘要会显示在这里。</div>
      ) : (
        <div className="task-history-layout">
          <div className="task-history-list">
            {tasks.map((task) => (
              <button
                className={`task-history-row${selectedTask?.id === task.id ? " active" : ""}`}
                key={task.id}
                type="button"
                onClick={() => setSelectedTaskId(task.id)}
              >
                <span className={`pill ${statusClass(task.status)}`}>{statusLabel(task.status)}</span>
                <strong>{task.task_type}</strong>
                <span>{shortId(task.id)}</span>
                <span>{task.current_step ?? "-"}</span>
                <span>{task.progress}%</span>
                <span>{formatDate(task.updated_at ?? task.created_at)}</span>
                <span className="task-row-action">查看详情</span>
              </button>
            ))}
          </div>

          {selectedTask ? (
            <div className="task-history-detail">
              <div className="status-row">
                <div>
                  <h3>{selectedTask.task_type}</h3>
                  <p className="message">任务 ID：{shortId(selectedTask.id)}</p>
                </div>
                <div className="task-detail-actions">
                  <span className={`pill ${statusClass(selectedTask.status)}`}>{statusLabel(selectedTask.status)}</span>
                  <button className="danger" disabled type="button">
                    重试需单独审批
                  </button>
                </div>
              </div>

              <div className="detail-grid">
                <span>状态</span>
                <strong>{statusLabel(selectedTask.status)}</strong>
                <span>当前步骤</span>
                <strong>{selectedTask.current_step ?? "-"}</strong>
                <span>进度</span>
                <strong>{selectedTask.progress}%</strong>
                <span>创建时间</span>
                <strong>{formatDate(selectedTask.created_at)}</strong>
                <span>更新时间</span>
                <strong>{formatDate(selectedTask.updated_at)}</strong>
                <span>开始时间</span>
                <strong>{formatDate(selectedTask.started_at)}</strong>
                <span>完成时间</span>
                <strong>{formatDate(selectedTask.finished_at)}</strong>
                <span>错误码</span>
                <strong>{selectedTask.error_code ?? "-"}</strong>
                <span>失败原因摘要</span>
                <strong>{taskFailureSummary(selectedTask)}</strong>
              </div>
              <div className="task-progress-card">
                <div className="status-row">
                  <strong>任务进度</strong>
                  <span>{selectedTask.progress}%</span>
                </div>
                <div className="task-progress-bar" aria-label={`任务进度 ${selectedTask.progress}%`}>
                  <span style={{ width: `${Math.max(0, Math.min(100, selectedTask.progress))}%` }} />
                </div>
              </div>

              {selectedTask.error_message ? (
                <div className="failure-box">{redactString(selectedTask.error_message)}</div>
              ) : null}

              <details className="task-history-details" open>
                <summary>脱敏任务结果摘要</summary>
                <pre>{resultSummary(selectedTask)}</pre>
              </details>

              <div className="task-history-logs">
                <h4>任务日志</h4>
                {logs.length === 0 ? (
                  <p className="message">暂无任务日志。</p>
                ) : (
                  <div className="log-list">
                    {logs.map((log) => {
                      const output = logOutput(log);
                      return (
                        <div className="log-row task-log-row" key={log.id}>
                          <span>{log.level}</span>
                          <span>{log.step ?? "-"}</span>
                          <span>
                            {redactString(log.message)}
                            {output ? (
                              <details className="task-log-output">
                                <summary>查看脱敏原始输出</summary>
                                <pre>{output}</pre>
                              </details>
                            ) : null}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </div>
      )}

      <p className="message">{message}</p>
    </section>
  );
}
