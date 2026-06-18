"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";

import { TransitReadonlyPreflightSimplePanel } from "@/components/TransitReadonlyPreflightSimplePanel";
import {
  apiFetch,
  createTransitReadonlyPreflightCommand,
  createTransitWorkerBootstrap,
  createWorkerCommand,
  listWorkerCommands,
  regenerateTransitWorkerBootstrap,
  requestReadonlyPreflightPlan,
  type CsrfResult,
  type NodeData,
  type NodeListResult,
  type ReadonlyPreflightPlanRequest,
  type ReadonlyPreflightPlanResponse,
  type TransitReadonlyPreflightCommandRequest,
  type TransitResourceData,
  type TransitResourceListResult,
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

function routeRoleLabel(route: TransitRouteData) {
  if (route.forwarding_method === "socat" && route.listen_port === 18443) {
    return "当前正式链路 / socat 18443";
  }
  if (route.forwarding_method === "gost" && route.listen_port === 8443) {
    return "回退链路 / 保留";
  }
  if (route.status === "creating") {
    return "本地规划";
  }
  return "候选链路";
}

async function ensureCsrfToken() {
  const csrf = await apiFetch<CsrfResult>("/api/auth/csrf");
  if (!csrf.success) {
    throw new Error(csrf.message);
  }
  return csrf.data.csrf_token;
}

async function copyText(value: string) {
  await navigator.clipboard.writeText(value);
}

export function TransitServersPanel() {
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("中转服务器页面只管理 Worker 接入资源；不会执行旧 SSH/RQ 检测或安装。");
  const [modalMode, setModalMode] = useState<"add" | "edit" | "install" | null>(null);
  const [selectedResource, setSelectedResource] = useState<TransitResourceData | null>(null);
  const [bootstrapForm, setBootstrapForm] = useState<TransitWorkerBootstrapFormState>(emptyBootstrapForm);
  const [workerTokenResult, setWorkerTokenResult] = useState<WorkerTokenCreateResult | null>(null);
  const [workerCommandsByWorkerId, setWorkerCommandsByWorkerId] = useState<Record<string, WorkerCommandData[]>>({});
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
                      <button className="secondary" disabled type="button" title="安全删除需要后续 Worker 清理阶段。">
                        删除待开放
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

      {modalMode ? (
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
                        void copyText(workerTokenResult.install_command);
                        setMessage("安装命令已复制。请勿写入聊天、Git、README、PR 或日志。");
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

  const selectableResources = useMemo(() => resources.filter(isPlanningSelectableTransitResource), [resources]);
  const activeNodes = useMemo(() => nodes.filter((node) => node.status === "active"), [nodes]);
  const selectedResource = selectableResources.find((resource) => resource.id === draft.transitResourceId) ?? selectableResources[0] ?? null;
  const selectedNode = activeNodes.find((node) => node.id === draft.landingNodeId) ?? activeNodes[0] ?? null;
  const plannedPort = parsePort(draft.plannedListenPort);
  const targetPort = targetPortForNode(selectedNode);

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
    const [resourceResult, nodeResult, routeResult] = await Promise.all([
      apiFetch<TransitResourceListResult>("/api/transit-resources?resource_type=server"),
      apiFetch<NodeListResult>("/api/nodes"),
      apiFetch<TransitRouteListResult>("/api/transit-routes"),
    ]);

    if (resourceResult.success) {
      setResources(resourceResult.data.resources);
    } else {
      setMessage(`${resourceResult.error_code}: ${resourceResult.message}`);
    }
    if (nodeResult.success) {
      setNodes(nodeResult.data.nodes);
    } else {
      setMessage(`${nodeResult.error_code}: ${nodeResult.message}`);
    }
    if (routeResult.success) {
      setRoutes(routeResult.data.routes);
    } else {
      setMessage(`${routeResult.error_code}: ${routeResult.message}`);
    }
    setLoading(false);
  }

  useEffect(() => {
    void loadData();
  }, []);

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
    await copyText(summary);
    setPreflightSummaryCopied(true);
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
          <p className="message">管理“中转服务器 → 落地服务器节点”的转发关系；本页不提供旧 SSH/RQ 创建入口。</p>
        </div>
        <button className="secondary" type="button" onClick={() => void loadData()}>
          刷新
        </button>
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

      <div className="transit-link-table-scroll">
        <div className="transit-link-table" aria-label="中转链路表格">
          <div className="transit-link-row transit-link-head">
            <span>链路名称</span>
            <span>中转服务器</span>
            <span>监听端口</span>
            <span>落地服务器</span>
            <span>目标节点</span>
            <span>目标端口</span>
            <span>转发方式</span>
            <span>状态</span>
            <span>角色标识</span>
            <span className="sticky-action-cell">操作</span>
          </div>
          {loading ? <div className="server-table-empty">正在加载中转链路。</div> : null}
          {!loading && routes.length === 0 ? <div className="server-table-empty">暂无中转链路记录。</div> : null}
          {!loading
            ? routes.map((route) => (
                <div className="transit-link-row" key={route.id}>
                  <span title={route.name}>
                    {route.name}
                    <small className="node-meta-line">{route.id}</small>
                  </span>
                  <span title={route.transit_resource_name ?? ""}>{route.transit_resource_name ?? route.transit_resource_id}</span>
                  <span>监听 {route.listen_port}</span>
                  <span title={route.landing_vps_ip ?? ""}>{route.landing_vps_ip ?? route.landing_vps_id ?? "-"}</span>
                  <span title={route.node_name ?? ""}>{route.node_name ?? route.node_id}</span>
                  <span>{route.target_port}</span>
                  <span>{route.forwarding_method}</span>
                  <span>
                    <span className={`pill ${statusClass(route.status)}`}>{displayStatusLabel(route.status)}</span>
                    <small className="node-meta-line">本地记录 / 远程状态需单独诊断</small>
                  </span>
                  <span title={routeRoleLabel(route)}>{routeRoleLabel(route)}</span>
                  <span className="server-actions sticky-action-cell">
                    <button className="secondary compact" type="button" onClick={() => setMessage(`链路 ${route.name}：只读查看，不执行诊断或删除。`)}>
                      查看
                    </button>
                    <button className="secondary compact" disabled type="button" title="旧 SSH 诊断入口已移除，请使用上方 Worker 只读预检。">
                      诊断
                    </button>
                    <button className="danger compact" disabled type="button" title="删除需要后续 Worker 清理阶段。">
                      删除
                    </button>
                  </span>
                </div>
              ))
            : null}
        </div>
      </div>

      <p className="message">{message}</p>
    </section>
  );
}
