"use client";

import { useEffect, useMemo, useState } from "react";

import { ProductIcon } from "@/components/ProductIcons";
import { apiFetch, type TaskData, type TaskListResult, type TaskLogData } from "@/lib/api";

const terminalStatuses = new Set(["success", "completed", "failed", "cancelled", "timeout"]);
const secretKeyPattern = /(private|private_key|passphrase|password|passwd|secret|token|cookie|session|admin_password_hash|ssh_key)/i;
const linkPattern = /(vless|vmess|trojan|ss):\/\//i;
const privateKeyPattern = /BEGIN (OPENSSH|RSA|EC|DSA)? ?PRIVATE KEY/i;

type TaskCategory = "all" | "create" | "check" | "failed";

const taskCategories: Array<{ label: string; value: TaskCategory }> = [
  { label: "全部任务", value: "all" },
  { label: "创建任务", value: "create" },
  { label: "检测任务", value: "check" },
  { label: "失败任务", value: "failed" },
];

function shortId(id: string) {
  return id.length > 12 ? `${id.slice(0, 8)}...${id.slice(-4)}` : id;
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "-";
}

function statusClass(status: string) {
  if (status === "success" || status === "completed") {
    return "success";
  }
  if (terminalStatuses.has(status)) {
    return "danger";
  }
  return "warning";
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

function businessTaskName(taskType: string) {
  const labels: Record<string, string> = {
    landing_node_create: "创建直连节点",
    transit_route_create: "创建中转线路",
    cleanup_landing_node: "删除节点",
    cleanup_landing_server: "清理落地服务器",
    cleanup_transit_route: "清理中转线路",
    cleanup_transit_resource: "清理中转服务器",
    bbr_enable_dry_run: "网络加速试运行",
    bbr_enable_real_execution: "启用网络加速",
    landing_preflight: "创建前检查",
    transit_readonly_preflight: "中转创建前检查",
    collect_status: "读取服务器状态",
    service_status: "读取服务状态",
  };
  return labels[taskType] ?? "系统任务";
}

function categoryForTask(taskType: string): TaskCategory {
  if (/create|install|enable/i.test(taskType)) {
    return "create";
  }
  if (/preflight|status|check|read/i.test(taskType)) {
    return "check";
  }
  return "check";
}

function relatedObject(task: TaskData) {
  if (task.node_id) {
    return `节点 ${shortId(task.node_id)}`;
  }
  if (task.vps_id) {
    return `服务器 ${shortId(task.vps_id)}`;
  }
  return "本地系统";
}

function resultAdvice(task: TaskData) {
  if (task.status === "success" || task.status === "completed") {
    return "任务已完成。";
  }
  if (task.status === "pending" || task.status === "running") {
    return "任务正在处理中。";
  }
  const failure = taskFailureSummary(task);
  if (/端口|监听/.test(failure)) {
    return `创建失败：端口未通过检测。建议：检查云安全组、云防火墙、服务器防火墙是否放行。`;
  }
  return failure;
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
    return "服务器登录连接失败。";
  }
  if (source.includes("port") || source.includes("listen") || source.includes("listening")) {
    return "端口监听、端口占用或监听验证异常。";
  }
  if (source.includes("process") || source.includes("service") || source.includes("systemd")) {
    return "服务器服务状态异常。";
  }
  if (source.includes("health")) {
    return "系统健康检查异常。";
  }
  if (source.includes("auth") || source.includes("csrf") || source.includes("login")) {
    return "登录状态或安全校验异常。";
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
  const [category, setCategory] = useState<TaskCategory>("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [showMoreFilters, setShowMoreFilters] = useState(false);
  const [dateRange, setDateRange] = useState("全部日期");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
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
      setSelectedTaskId(nextSelectedId ?? selectedTaskId ?? result.data.tasks[0]?.id ?? null);
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

  const filteredTasks = useMemo(() => {
    return tasks.filter((task) => {
      const categoryMatches = category === "all" || category === "failed" || categoryForTask(task.task_type) === category;
      const failedMatches = category !== "failed" || task.status === "failed" || task.status === "timeout";
      const statusMatches = statusFilter === "all" || task.status === statusFilter;
      const typeMatches = typeFilter === "all" || task.task_type === typeFilter;
      const keyword = search.trim().toLowerCase();
      const searchMatches = !keyword || `${businessTaskName(task.task_type)} ${relatedObject(task)} ${resultAdvice(task)}`.toLowerCase().includes(keyword);
      return categoryMatches && failedMatches && statusMatches && typeMatches && searchMatches;
    });
  }, [category, search, statusFilter, tasks, typeFilter]);

  const availableTypes = Array.from(new Set(tasks.map((task) => task.task_type))).sort();
  const availableStatuses = Array.from(new Set(tasks.map((task) => task.status))).sort();

  return (
    <section className="task-record-page wide">
      <div className="task-page-actions">
        <button className="secondary" disabled={loading} type="button" onClick={() => void loadTasks()}>
          刷新
        </button>
      </div>

      <div className="product-section-card">
        <div className="task-filter-panel">
          <div className="filter-tabs">
            {taskCategories.map((item) => (
              <button
                className={category === item.value ? "selected" : ""}
                key={item.value}
                type="button"
                onClick={() => setCategory(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <select aria-label="状态筛选" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">状态筛选</option>
            {availableStatuses.map((status) => (
              <option key={status} value={status}>
                {statusLabel(status)}
              </option>
            ))}
          </select>
          <input aria-label="搜索任务" placeholder="搜索任务或关联对象" value={search} onChange={(event) => setSearch(event.target.value)} />
          <button className="secondary" type="button" onClick={() => setShowMoreFilters((open) => !open)}>
            更多筛选
          </button>
          {showMoreFilters ? (
            <div className="more-filter-panel">
              <select aria-label="类型筛选" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
                <option value="all">类型筛选</option>
                {availableTypes.map((taskType) => (
                  <option key={taskType} value={taskType}>
                    {businessTaskName(taskType)}
                  </option>
                ))}
              </select>
              <select aria-label="日期范围" value={dateRange} onChange={(event) => setDateRange(event.target.value)}>
                <option>全部日期</option>
                <option>今天</option>
                <option>最近 7 天</option>
                <option>最近 30 天</option>
              </select>
              <div className="date-range-inputs">
                <input aria-label="开始日期" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
                <span>-</span>
                <input aria-label="结束日期" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
              </div>
            </div>
          ) : null}
        </div>

        <div className="product-table task-product-table">
          <div className="product-table-row product-table-head">
            <span>时间</span>
            <span>任务名称</span>
            <span>关联对象</span>
            <span>状态</span>
            <span>结果说明</span>
            <span>操作</span>
          </div>
          {filteredTasks.length === 0 ? (
            <div className="product-empty-state inline">
              <ProductIcon name="tasks" tone="blue" />
              <strong>暂无任务</strong>
              <p>当你创建线路或检测线路后，任务会显示在这里。</p>
            </div>
          ) : (
            filteredTasks.map((task) => (
              <button
                className={`product-table-row product-task-row${selectedTask?.id === task.id ? " active" : ""}`}
                key={task.id}
                type="button"
                onClick={() => setSelectedTaskId(task.id)}
              >
                <span>{formatDate(task.started_at ?? task.created_at)}</span>
                <strong>{businessTaskName(task.task_type)}</strong>
                <span>{relatedObject(task)}</span>
                <span className={`product-badge ${statusClass(task.status)}`}>{statusLabel(task.status)}</span>
                <span>{resultAdvice(task)}</span>
                <span className="task-row-action">查看详情</span>
              </button>
            ))
          )}
        </div>
      </div>

      {selectedTask ? (
        <section className="product-section-card task-detail-card">
          <div className="product-section-head">
            <div>
              <h3>{businessTaskName(selectedTask.task_type)}</h3>
              <p>{resultAdvice(selectedTask)}</p>
            </div>
            <span className={`product-badge ${statusClass(selectedTask.status)}`}>{statusLabel(selectedTask.status)}</span>
          </div>
          <div className="detail-grid">
            <span>任务内容</span>
            <strong>{relatedObject(selectedTask)}</strong>
            <span>当前进度</span>
            <strong>{selectedTask.progress}%</strong>
            <span>创建时间</span>
            <strong>{formatDate(selectedTask.created_at)}</strong>
            <span>完成时间</span>
            <strong>{formatDate(selectedTask.finished_at)}</strong>
          </div>

          {selectedTask.error_message ? (
            <div className="failure-box">{redactString(selectedTask.error_message)}</div>
          ) : null}

          <details className="task-history-details">
            <summary>查看技术详情</summary>
            <div className="business-detail-grid compact">
              <span>任务 ID</span>
              <strong>{shortId(selectedTask.id)}</strong>
              <span>原始类型</span>
              <strong>{selectedTask.task_type}</strong>
              <span>错误码</span>
              <strong>{selectedTask.error_code ?? "-"}</strong>
              <span>当前步骤</span>
              <strong>{selectedTask.current_step ?? "-"}</strong>
            </div>
            <pre>{resultSummary(selectedTask)}</pre>
          </details>

          <details className="task-history-details">
            <summary>查看日志</summary>
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
          </details>
        </section>
      ) : null}

      <p className="message">{message}</p>
    </section>
  );
}
