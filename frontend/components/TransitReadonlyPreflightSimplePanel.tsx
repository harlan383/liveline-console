"use client";

import { useEffect, useState } from "react";

import {
  apiFetch,
  createTransitReadonlyPreflightCommand,
  listWorkerCommands,
  type CsrfResult,
  type NodeData,
  type NodeListResult,
  type TransitResourceData,
  type TransitResourceListResult,
  type TransitReadonlyPreflightCommandRequest,
  type WorkerCommandData,
} from "@/lib/api";

const workerCommandTerminalStatuses = new Set(["succeeded", "failed", "expired", "cancelled"]);
const protectedPorts = new Set([22, 8443, 18443, 20575]);

type SimpleStatus = "idle" | "running" | "passed" | "failed" | "blocked";

function formatTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "暂无";
}

function parsePort(value: string) {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 65535 ? parsed : null;
}

function objectValue(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function stringValue(record: Record<string, unknown> | null, key: string) {
  const value = record?.[key];
  return typeof value === "string" && value ? value : "-";
}

function booleanValue(record: Record<string, unknown> | null, key: string) {
  return record?.[key] === true;
}

function transitHostLabel(resource: TransitResourceData | null) {
  return resource?.entry_host || resource?.ssh_host || "-";
}

function nodeHostLabel(node: NodeData | null) {
  return node?.vps_ip || node?.vps_id || "-";
}

function nodePortLabel(node: NodeData | null) {
  return node?.port ? String(node.port) : "";
}

function isSelectableTransitResource(resource: TransitResourceData) {
  if (resource.resource_type !== "server" || resource.status === "disabled") {
    return false;
  }
  const displayStatus = resource.display_status || resource.status;
  return resource.worker_online || displayStatus === "online" || displayStatus === "worker_online";
}

function commandStatusLabel(status: string | null | undefined) {
  const labels: Record<string, string> = {
    pending: "等待中",
    claimed: "已领取",
    running: "预检中",
    succeeded: "成功",
    failed: "失败",
    expired: "已过期",
    cancelled: "已取消",
  };
  return labels[status || ""] ?? status ?? "未预检";
}

function simpleStatusFromCommand(command: WorkerCommandData | null): SimpleStatus {
  if (!command) {
    return "idle";
  }
  if (!workerCommandTerminalStatuses.has(command.status)) {
    return "running";
  }
  if (command.status !== "succeeded") {
    return "failed";
  }
  const result = objectValue(command.result_json);
  if (result?.["passed"] === true || result?.["status"] === "passed" || result?.["status"] === "ready") {
    return "passed";
  }
  if (result?.["status"] === "blocked") {
    return "blocked";
  }
  return "failed";
}

function simpleStatusLabel(status: SimpleStatus) {
  const labels: Record<SimpleStatus, string> = {
    idle: "未预检",
    running: "预检中",
    passed: "预检通过",
    failed: "预检未通过",
    blocked: "预检被阻止",
  };
  return labels[status];
}

function simpleStatusClass(status: SimpleStatus) {
  if (status === "passed") {
    return "ok";
  }
  if (status === "idle") {
    return "muted";
  }
  if (status === "running" || status === "blocked") {
    return "warn";
  }
  return "bad";
}

function checkStatusClass(check: Record<string, unknown> | null) {
  if (check?.["passed"] === true) {
    return "ok";
  }
  if (check?.["status"] === "skipped" || check?.["status"] === "blocked") {
    return "warn";
  }
  return "bad";
}

export function TransitReadonlyPreflightSimplePanel() {
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [selectedResourceId, setSelectedResourceId] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [plannedListenPort, setPlannedListenPort] = useState("24731");
  const [landingTargetPort, setLandingTargetPort] = useState("");
  const [purpose, setPurpose] = useState("直播线路");
  const [ackReadonly, setAckReadonly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState("请选择中转服务器和落地节点，然后点击一次远程只读预检。");
  const [command, setCommand] = useState<WorkerCommandData | null>(null);

  const selectableResources = resources.filter(isSelectableTransitResource);
  const activeNodes = nodes.filter((node) => node.status === "active");
  const selectedResource = selectableResources.find((resource) => resource.id === selectedResourceId) ?? null;
  const selectedNode = activeNodes.find((node) => node.id === selectedNodeId) ?? null;
  const plannedPortNumber = parsePort(plannedListenPort);
  const landingPortNumber = parsePort(landingTargetPort || nodePortLabel(selectedNode));
  const simpleStatus = simpleStatusFromCommand(command);
  const commandResult = objectValue(command?.result_json);
  const commandChecks = Array.isArray(commandResult?.["checks"]) ? commandResult["checks"] : [];
  const canRun = Boolean(
    selectedResource &&
      selectedNode &&
      plannedPortNumber &&
      landingPortNumber &&
      !protectedPorts.has(plannedPortNumber) &&
      ackReadonly &&
      !running,
  );

  async function ensureCsrfToken() {
    const csrf = await apiFetch<CsrfResult>("/api/auth/csrf");
    if (!csrf.success) {
      throw new Error(csrf.message);
    }
    return csrf.data.csrf_token;
  }

  async function loadData() {
    setLoading(true);
    const [resourceResult, nodeResult] = await Promise.all([
      apiFetch<TransitResourceListResult>("/api/transit-resources?resource_type=server"),
      apiFetch<NodeListResult>("/api/nodes"),
    ]);

    if (!resourceResult.success) {
      setMessage(resourceResult.message);
      setLoading(false);
      return;
    }
    if (!nodeResult.success) {
      setMessage(nodeResult.message);
      setLoading(false);
      return;
    }

    const nextResources = resourceResult.data.resources.filter((resource) => resource.resource_type === "server");
    const nextNodes = nodeResult.data.nodes.filter((node) => node.status === "active");
    const nextSelectableResources = nextResources.filter(isSelectableTransitResource);
    const nextNode = nextNodes[0] ?? null;

    setResources(nextResources);
    setNodes(nextNodes);
    setSelectedResourceId((current) => current || nextSelectableResources[0]?.id || "");
    setSelectedNodeId((current) => current || nextNode?.id || "");
    setLandingTargetPort((current) => current || (nextNode?.port ? String(nextNode.port) : "27939"));
    setLoading(false);
  }

  useEffect(() => {
    void loadData();
  }, []);

  useEffect(() => {
    const node = activeNodes.find((item) => item.id === selectedNodeId) ?? null;
    if (node?.port && !landingTargetPort) {
      setLandingTargetPort(String(node.port));
    }
  }, [activeNodes, landingTargetPort, selectedNodeId]);

  useEffect(() => {
    if (!command?.target_worker_id || workerCommandTerminalStatuses.has(command.status)) {
      return;
    }
    const timer = window.setTimeout(() => {
      void refreshCommand(command.target_worker_id, command.id);
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [command]);

  function validateInputs() {
    if (!selectedResource) {
      return "请选择在线的中转服务器。";
    }
    if (!selectedResource.worker_online) {
      return "当前中转服务器 Worker 不在线，不能做远程只读预检。";
    }
    if (!selectedNode) {
      return "请选择 active 落地节点。";
    }
    if (!plannedPortNumber) {
      return "计划监听端口必须是 1-65535 之间的整数。";
    }
    if (protectedPorts.has(plannedPortNumber)) {
      return "计划监听端口不能使用 22 / 8443 / 18443 / 20575。";
    }
    if (!landingPortNumber) {
      return "落地目标端口必须是 1-65535 之间的整数。";
    }
    if (!ackReadonly) {
      return "请先确认这只是只读预检，不会创建真实线路。";
    }
    return null;
  }

  async function runSimpleReadonlyPreflight() {
    const validationError = validateInputs();
    if (validationError) {
      setMessage(validationError);
      return;
    }
    const payload: TransitReadonlyPreflightCommandRequest = {
      transit_resource_id: selectedResourceId,
      landing_node_id: selectedNodeId,
      planned_listen_port: plannedPortNumber as number,
      landing_target_port: landingPortNumber as number,
      forwarding_method: "socat",
      purpose: purpose.trim() || "直播线路",
      readonly: true,
    };

    try {
      setRunning(true);
      setCommand(null);
      setMessage("正在创建远程只读预检。系统只会读取状态，不会创建真实线路。");
      const csrfToken = await ensureCsrfToken();
      const result = await createTransitReadonlyPreflightCommand(payload, csrfToken);
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setCommand(result.data.command);
      setMessage("远程只读预检已创建，正在等待 Worker 返回结果。页面会自动刷新。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "远程只读预检创建失败。");
    } finally {
      setRunning(false);
    }
  }

  async function refreshCommand(workerId: string, commandId: string) {
    const result = await listWorkerCommands(workerId);
    if (!result.success) {
      setMessage(`${result.error_code}: ${result.message}`);
      return;
    }
    const updated = result.data.commands.find((item) => item.id === commandId);
    if (!updated) {
      setMessage("暂未找到预检命令，请稍后再看。");
      return;
    }
    setCommand(updated);
    if (workerCommandTerminalStatuses.has(updated.status)) {
      const status = simpleStatusFromCommand(updated);
      setMessage(status === "passed" ? "远程只读预检通过。" : "远程只读预检未通过，请查看检查项。");
    }
  }

  return (
    <section className="panel wide transit-simple-preflight-panel">
      <div className="server-panel-header">
        <div>
          <h2>中转链路远程只读预检</h2>
          <p>简化版：选择中转服务器、落地节点和计划端口，然后点一次按钮。不会创建真实中转链路。</p>
        </div>
        <span className={`pill ${simpleStatusClass(simpleStatus)}`}>{simpleStatusLabel(simpleStatus)}</span>
      </div>

      <div className="warning-box wide-field">
        <strong>安全边界</strong>
        <span>这个按钮只做远程只读检查：Worker、端口占用、socat/gost 状态、中转到落地连通性和防火墙只读摘要。</span>
        <span>不会安装、启动、停止或重启 socat/gost，不会绑定 24731，不会改防火墙，不会修改 Xray 或 nodes.share_link。</span>
      </div>

      <div className="form server-modal-form">
        <label>
          中转服务器
          <select value={selectedResourceId} onChange={(event) => setSelectedResourceId(event.target.value)}>
            {selectableResources.length === 0 ? <option value="">暂无在线中转服务器</option> : null}
            {selectableResources.map((resource) => (
              <option key={resource.id} value={resource.id}>
                {resource.name} / {transitHostLabel(resource)} / Worker {resource.worker_version || "未知版本"}
              </option>
            ))}
          </select>
          <span className="field-hint">只显示 Worker 在线的中转服务器。</span>
        </label>

        <label>
          目标落地节点
          <select
            value={selectedNodeId}
            onChange={(event) => {
              const nextNode = activeNodes.find((node) => node.id === event.target.value) ?? null;
              setSelectedNodeId(event.target.value);
              setLandingTargetPort(nextNode?.port ? String(nextNode.port) : "");
            }}
          >
            {activeNodes.length === 0 ? <option value="">暂无 active 落地节点</option> : null}
            {activeNodes.map((node) => (
              <option key={node.id} value={node.id}>
                {node.node_name} / {nodeHostLabel(node)}:{node.port || "-"}
              </option>
            ))}
          </select>
          <span className="field-hint">只允许 active 落地节点。</span>
        </label>

        <label>
          计划监听端口
          <input inputMode="numeric" value={plannedListenPort} onChange={(event) => setPlannedListenPort(event.target.value)} />
          <span className="field-hint">默认 24731；真实创建前仍需确认云安全组 / 云防火墙 / 服务器防火墙。</span>
        </label>

        <label>
          落地目标端口
          <input inputMode="numeric" value={landingTargetPort} onChange={(event) => setLandingTargetPort(event.target.value)} />
          <span className="field-hint">应与当前落地节点端口一致。</span>
        </label>

        <label className="wide-field">
          用途
          <input value={purpose} onChange={(event) => setPurpose(event.target.value)} placeholder="例如：直播线路" />
        </label>

        <label className="checkbox-label wide-field">
          <input checked={ackReadonly} type="checkbox" onChange={(event) => setAckReadonly(event.target.checked)} />
          我确认这里只执行远程只读预检，不创建中转链路、不绑定端口、不改防火墙、不修改节点链接。
        </label>

        <div className="modal-actions wide-field">
          <button disabled={loading || !canRun} type="button" onClick={() => void runSimpleReadonlyPreflight()}>
            {running || simpleStatus === "running" ? "预检中..." : "远程只读预检"}
          </button>
          <button className="secondary" type="button" onClick={() => void loadData()}>
            刷新服务器列表
          </button>
        </div>
      </div>

      <div className="server-panel-footer">
        <span>{message}</span>
      </div>

      {selectedResource || selectedNode ? (
        <div className="detail-grid">
          <span>当前中转</span>
          <strong>{selectedResource ? `${selectedResource.name} / ${transitHostLabel(selectedResource)}` : "-"}</strong>
          <span>Worker</span>
          <strong>{selectedResource ? `${selectedResource.worker_online ? "在线" : "离线"} / ${selectedResource.worker_version || "未知版本"}` : "-"}</strong>
          <span>最后心跳</span>
          <strong>{formatTime(selectedResource?.worker_last_heartbeat_at)}</strong>
          <span>当前落地</span>
          <strong>{selectedNode ? `${selectedNode.node_name} / ${nodeHostLabel(selectedNode)}:${selectedNode.port || "-"}` : "-"}</strong>
        </div>
      ) : null}

      {command ? (
        <div className="readonly-preflight-api-result">
          <div className="status-row">
            <div>
              <h3>{simpleStatusLabel(simpleStatus)}</h3>
              <p className="message">{stringValue(commandResult, "summary")}</p>
            </div>
            <span className={`pill ${simpleStatusClass(simpleStatus)}`}>{commandStatusLabel(command.status)}</span>
          </div>

          {commandChecks.length > 0 ? (
            <div className="readonly-preflight-checklist api-check-list">
              {commandChecks.map((item, index) => {
                const check = objectValue(item);
                return (
                  <div className="readonly-preflight-item api-check-card" key={`${stringValue(check, "id")}-${index}`}>
                    <div className="status-row">
                      <div>
                        <strong>{stringValue(check, "label")}</strong>
                        <p className="message">{stringValue(check, "detail")}</p>
                      </div>
                      <span className={`pill ${checkStatusClass(check)}`}>{stringValue(check, "status")}</span>
                    </div>
                    <div className="detail-grid compact-detail-grid">
                      <span>是否通过</span>
                      <strong>{booleanValue(check, "passed") ? "是" : "否"}</strong>
                      <span>检查编号</span>
                      <strong>{stringValue(check, "id")}</strong>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="warning-box">
              <strong>等待结果</strong>
              <span>Worker 还没有返回检查项；页面会自动刷新。</span>
            </div>
          )}

          <details className="warning-box collapsible-notice wide-field">
            <summary className="collapsible-summary">
              <strong>高级信息</strong>
              <span className="notice-toggle-text">
                <span className="when-closed">查看</span>
                <span className="when-open">收起</span>
              </span>
            </summary>
            <div className="collapsible-body">
              <span>command id：{command.id}</span>
              <span>target worker：{command.target_worker_id}</span>
              <span>worker version：{command.target_worker_version || "-"}</span>
              <span>created_at：{formatTime(command.created_at)}</span>
              <span>completed_at：{formatTime(command.completed_at)}</span>
            </div>
          </details>
        </div>
      ) : null}
    </section>
  );
}
