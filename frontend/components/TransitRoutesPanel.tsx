"use client";

import { useEffect, useRef, useState } from "react";

import {
  apiFetch,
  apiFormFetch,
  type CsrfResult,
  type NodeData,
  type NodeListResult,
  type TaskData,
  type TaskLogData,
  type TransitResourceData,
  type TransitResourceListResult,
  type TransitRouteCreateResult,
  type TransitRouteData,
  type TransitRouteDiagnoseResult,
  type TransitRouteListResult,
  type TransitRouteRestartSocatResult,
} from "@/lib/api";

const terminalStatuses = new Set(["success", "failed", "cancelled", "timeout"]);
const SOCAT_RESOURCE_ID = "6d67c275-8ac9-4775-9519-c89b50718157";
const SOCAT_RESERVED_PORTS = new Set(["22", "8443", "20575"]);

type ForwardingMethod = "gost" | "socat";

function displayValue(value: string | number | null | undefined) {
  return value === null || value === undefined || value === "" ? "-" : String(value);
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

function scalarValue(record: Record<string, unknown> | null, key: string) {
  const value = record?.[key];
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "-";
}

function maskLink(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  if (value.length <= 44) {
    return value;
  }
  return `${value.slice(0, 24)}...${value.slice(-12)}`;
}

export function TransitRoutesPanel() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const diagnosticFileInputRef = useRef<HTMLInputElement | null>(null);
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [routes, setRoutes] = useState<TransitRouteData[]>([]);
  const [selectedResourceId, setSelectedResourceId] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [forwardingMethod, setForwardingMethod] = useState<ForwardingMethod>("gost");
  const [routeName, setRouteName] = useState("hk-gost-route-01");
  const [listenPort, setListenPort] = useState("8443");
  const [confirm, setConfirm] = useState(false);
  const [privateKeyText, setPrivateKeyText] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [task, setTask] = useState<TaskData | null>(null);
  const [logs, setLogs] = useState<TaskLogData[]>([]);
  const [message, setMessage] = useState("Stage 3.3.3 只创建一条 gost TCP 转发规则。");
  const [copied, setCopied] = useState(false);
  const [copiedRouteId, setCopiedRouteId] = useState<string | null>(null);
  const [copiedSocatTestRouteId, setCopiedSocatTestRouteId] = useState<string | null>(null);
  const [copiedDiagnosticsRouteId, setCopiedDiagnosticsRouteId] = useState<string | null>(null);
  const [diagnosticPrivateKeyText, setDiagnosticPrivateKeyText] = useState("");
  const [diagnosticPassphrase, setDiagnosticPassphrase] = useState("");
  const [diagnosticTask, setDiagnosticTask] = useState<TaskData | null>(null);
  const [diagnosticLogs, setDiagnosticLogs] = useState<TaskLogData[]>([]);
  const [diagnosticRouteId, setDiagnosticRouteId] = useState<string | null>(null);
  const [diagnosticMessage, setDiagnosticMessage] = useState("只读诊断不会停止、删除、重启或创建线路。");

  async function ensureCsrfToken() {
    const csrf = await apiFetch<CsrfResult>("/api/auth/csrf");
    if (!csrf.success) {
      throw new Error(csrf.message);
    }
    return csrf.data.csrf_token;
  }

  async function loadData() {
    const [resourceResult, nodeResult, routeResult] = await Promise.all([
      apiFetch<TransitResourceListResult>("/api/transit-resources?status=active&resource_type=server"),
      apiFetch<NodeListResult>("/api/nodes"),
      apiFetch<TransitRouteListResult>("/api/transit-routes"),
    ]);

    if (!resourceResult.success) {
      setMessage(resourceResult.message);
      return;
    }
    if (!nodeResult.success) {
      setMessage(nodeResult.message);
      return;
    }
    if (!routeResult.success) {
      setMessage(routeResult.message);
      return;
    }

    const activeResources = resourceResult.data.resources.filter(
      (resource) => resource.resource_type === "server" && resource.status === "active",
    );
    const activeNodes = nodeResult.data.nodes.filter((node) => node.status === "active");
    const activeNodeDetails = await Promise.all(
      activeNodes.map(async (node) => {
        const detailResult = await apiFetch<NodeData>(`/api/nodes/${node.id}`);
        return detailResult.success ? { ...node, ...detailResult.data } : node;
      }),
    );
    setResources(activeResources);
    setNodes(activeNodeDetails);
    setRoutes(routeResult.data.routes);
    setSelectedResourceId((current) => current || activeResources[0]?.id || "");
    setSelectedNodeId((current) => current || activeNodes[0]?.id || "");
  }

  useEffect(() => {
    void loadData();
  }, []);

  useEffect(() => {
    setConfirm(false);
    setTask(null);
    setLogs([]);
    setCopied(false);
    if (forwardingMethod === "socat") {
      setRouteName("hk-socat-test-18443");
      setListenPort("18443");
      setSelectedResourceId((current) =>
        resources.some((resource) => resource.id === SOCAT_RESOURCE_ID) ? SOCAT_RESOURCE_ID : current,
      );
      setMessage("Stage 3.3.3-fix-b1：只创建 socat 测试转发。");
      return;
    }

    setRouteName("hk-gost-route-01");
    setListenPort("8443");
    setMessage("Stage 3.3.3 只创建一条 gost TCP 转发规则。");
  }, [forwardingMethod, resources]);

  useEffect(() => {
    if (!task?.id || terminalStatuses.has(task.status)) {
      return;
    }
    const timer = window.setTimeout(() => {
      void loadTask(task.id);
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [task]);

  useEffect(() => {
    if (!diagnosticTask?.id || terminalStatuses.has(diagnosticTask.status)) {
      return;
    }
    const timer = window.setTimeout(() => {
      void loadDiagnosticTask(diagnosticTask.id);
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [diagnosticTask]);

  async function loadTask(taskId: string) {
    const [taskResult, logsResult] = await Promise.all([
      apiFetch<TaskData>(`/api/tasks/${taskId}`),
      apiFetch<{ logs: TaskLogData[] }>(`/api/tasks/${taskId}/logs`),
    ]);

    if (taskResult.success) {
      setTask(taskResult.data);
      const taskMessage = taskResult.data.result_data?.["message"];
      if (typeof taskMessage === "string") {
        setMessage(taskMessage);
      } else if (taskResult.data.error_message) {
        setMessage(taskResult.data.error_message);
      }
      if (terminalStatuses.has(taskResult.data.status)) {
        void loadData();
      }
    } else {
      setMessage(taskResult.message);
    }

    if (logsResult.success) {
      setLogs(logsResult.data.logs);
    }
  }

  async function loadDiagnosticTask(taskId: string) {
    const [taskResult, logsResult] = await Promise.all([
      apiFetch<TaskData>(`/api/tasks/${taskId}`),
      apiFetch<{ logs: TaskLogData[] }>(`/api/tasks/${taskId}/logs`),
    ]);

    if (taskResult.success) {
      setDiagnosticTask(taskResult.data);
      const taskMessage = taskResult.data.result_data?.["message"];
      if (typeof taskMessage === "string") {
        setDiagnosticMessage(taskMessage);
      } else if (taskResult.data.error_message) {
        setDiagnosticMessage(taskResult.data.error_message);
      }
      if (terminalStatuses.has(taskResult.data.status)) {
        void loadData();
      }
    } else {
      setDiagnosticMessage(taskResult.message);
    }

    if (logsResult.success) {
      setDiagnosticLogs(logsResult.data.logs);
    }
  }

  function buildForm() {
    const formData = new FormData();
    formData.append("transit_resource_id", selectedResourceId);
    formData.append("node_id", selectedNodeId);
    formData.append("listen_port", listenPort);
    formData.append("forwarding_method", forwardingMethod);
    formData.append("route_name", routeName);
    formData.append("confirm", confirm ? "true" : "false");
    formData.append("ssh_key_passphrase", passphrase);
    if (privateKeyText.trim()) {
      formData.append("private_key_text", privateKeyText);
    }
    const file = fileInputRef.current?.files?.[0];
    if (file) {
      formData.append("private_key_file", file);
    }
    return formData;
  }

  function buildDiagnosticForm() {
    const formData = new FormData();
    formData.append("ssh_key_passphrase", diagnosticPassphrase);
    if (diagnosticPrivateKeyText.trim()) {
      formData.append("private_key_text", diagnosticPrivateKeyText);
    }
    const file = diagnosticFileInputRef.current?.files?.[0];
    if (file) {
      formData.append("private_key_file", file);
    }
    return formData;
  }

  function clearCredentials() {
    setPrivateKeyText("");
    setPassphrase("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  function clearDiagnosticCredentials() {
    setDiagnosticPrivateKeyText("");
    setDiagnosticPassphrase("");
    if (diagnosticFileInputRef.current) {
      diagnosticFileInputRef.current.value = "";
    }
  }

  async function createTransitRoute() {
    setCopied(false);
    if (!selectedResourceId || !selectedNodeId) {
      setMessage("请选择中转资源和 active 节点。");
      return;
    }
    if (forwardingMethod === "socat" && selectedResourceId !== SOCAT_RESOURCE_ID) {
      setMessage("socat 首轮测试只允许选择正式香港中转服务器。");
      return;
    }
    if (forwardingMethod === "socat" && SOCAT_RESERVED_PORTS.has(listenPort.trim())) {
      setMessage("socat 测试转发禁止使用 22 / 8443 / 20575。");
      return;
    }
    if (!confirm) {
      setMessage("请先确认风险提示。");
      return;
    }

    try {
      setMessage(`正在创建单条 ${forwardingMethod} TCP 转发任务。`);
      const csrfToken = await ensureCsrfToken();
      const result = await apiFormFetch<TransitRouteCreateResult>(
        "/api/transit-routes",
        buildForm(),
        {
          headers: { "X-CSRF-Token": csrfToken },
        },
      );
      clearCredentials();
      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setMessage(`单条 ${forwardingMethod} TCP 转发任务已创建。`);
      await loadTask(result.data.task_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "创建中转规则任务失败。");
    }
  }

  async function diagnoseRoute(route: TransitRouteData) {
    const hasTextKey = diagnosticPrivateKeyText.trim().length > 0;
    const hasFileKey = Boolean(diagnosticFileInputRef.current?.files?.[0]);
    if (!hasTextKey && !hasFileKey) {
      setDiagnosticMessage("请先粘贴或选择中转服务器 SSH 私钥。");
      return;
    }

    try {
      setDiagnosticRouteId(route.id);
      setDiagnosticTask(null);
      setDiagnosticLogs([]);
      setDiagnosticMessage("正在创建中转线路只读诊断任务。");
      const csrfToken = await ensureCsrfToken();
      const result = await apiFormFetch<TransitRouteDiagnoseResult>(
        `/api/transit-routes/${route.id}/diagnose`,
        buildDiagnosticForm(),
        {
          headers: { "X-CSRF-Token": csrfToken },
        },
      );
      clearDiagnosticCredentials();
      if (!result.success) {
        setDiagnosticMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setDiagnosticMessage("中转线路只读诊断任务已创建。");
      await loadDiagnosticTask(result.data.task_id);
    } catch (error) {
      setDiagnosticMessage(error instanceof Error ? error.message : "中转线路只读诊断任务创建失败。");
    }
  }

  async function restartSocatRoute(route: TransitRouteData) {
    if (!isSocatTestRoute(route)) {
      setDiagnosticMessage("只允许重启 socat 18443 测试链路。");
      return;
    }
    const hasTextKey = diagnosticPrivateKeyText.trim().length > 0;
    const hasFileKey = Boolean(diagnosticFileInputRef.current?.files?.[0]);
    if (!hasTextKey && !hasFileKey) {
      setDiagnosticMessage("请先粘贴或选择中转服务器 SSH 私钥。");
      return;
    }
    const confirmed = window.confirm("仅重启 socat 测试链路，不会修改 gost 8443 正式链路。");
    if (!confirmed) {
      return;
    }

    try {
      setDiagnosticRouteId(route.id);
      setDiagnosticTask(null);
      setDiagnosticLogs([]);
      setDiagnosticMessage("正在创建 socat 测试链路重启任务。");
      const csrfToken = await ensureCsrfToken();
      const result = await apiFormFetch<TransitRouteRestartSocatResult>(
        `/api/transit-routes/${route.id}/restart-socat`,
        buildDiagnosticForm(),
        {
          headers: { "X-CSRF-Token": csrfToken },
        },
      );
      clearDiagnosticCredentials();
      if (!result.success) {
        setDiagnosticMessage(`${result.error_code}: ${result.message}`);
        return;
      }
      setDiagnosticMessage("socat 测试链路重启任务已创建。");
      await loadDiagnosticTask(result.data.task_id);
    } catch (error) {
      setDiagnosticMessage(error instanceof Error ? error.message : "socat 测试链路重启任务创建失败。");
    }
  }

  async function copyTransitLink() {
    const shareLink = stringValue(objectValue(task?.result_data?.["route"]), "share_link");
    if (shareLink === "-") {
      return;
    }
    await navigator.clipboard.writeText(shareLink);
    setCopied(true);
  }

  async function copyRouteLink(route: TransitRouteData) {
    if (!route.share_link) {
      return;
    }
    await navigator.clipboard.writeText(route.share_link);
    setCopiedRouteId(route.id);
  }

  async function copySocatTestLink(route: TransitRouteData) {
    const derivedLink = derivedSocatTestLinkForRoute(route);
    if (!derivedLink) {
      setDiagnosticMessage("当前页面缺少 node.share_link，暂不能生成派生链接。");
      return;
    }
    const confirmed = window.confirm(
      "这是测试链路，尚未正式 cutover。复制后仅用于测试客户端导入，不会修改正式节点链接。",
    );
    if (!confirmed) {
      return;
    }
    await navigator.clipboard.writeText(derivedLink);
    setCopiedSocatTestRouteId(route.id);
  }

  async function copyDiagnostics(route: TransitRouteData) {
    await navigator.clipboard.writeText(diagnosticTextForRoute(route));
    setCopiedDiagnosticsRouteId(route.id);
  }

  function transitHostForRoute(route: TransitRouteData) {
    const resource = resources.find((item) => item.id === route.transit_resource_id);
    return resource?.entry_host || resource?.ssh_host || null;
  }

  function processCheckCommand(route: TransitRouteData) {
    if (route.forwarding_method === "socat") {
      return "ps -ef | grep '[s]ocat'";
    }
    if (route.forwarding_method === "gost") {
      return "ps -ef | grep '[g]ost'";
    }
    return `ps -ef | grep '[${route.forwarding_method.slice(0, 1)}]${route.forwarding_method.slice(1)}'`;
  }

  function diagnosticCommandsForRoute(route: TransitRouteData) {
    const transitHost = displayValue(transitHostForRoute(route));
    const commands = [
      {
        label: "本地连通性",
        command: `nc -vz ${transitHost} ${route.listen_port}`,
      },
      {
        label: "中转机监听检查",
        command: `ss -lntp | grep ${route.listen_port}`,
      },
      {
        label: "中转机转发进程检查",
        command: processCheckCommand(route),
      },
      {
        label: "systemd 服务状态",
        command: route.service_name ? `systemctl status ${route.service_name}` : "-",
      },
      {
        label: "目标连通性",
        command: `nc -vz ${route.target_host} ${route.target_port}`,
      },
    ];
    return commands;
  }

  function diagnosticTextForRoute(route: TransitRouteData) {
    return diagnosticCommandsForRoute(route)
      .map((item) => `${item.label}: ${item.command}`)
      .join("\n");
  }

  function diagnosticCheckFor(key: string) {
    const result = diagnosticTask?.result_data;
    const checks = objectValue(result?.["checks"]);
    return objectValue(checks?.[key]);
  }

  function checkOutput(check: Record<string, unknown> | null) {
    const output = check?.["raw_output"];
    return typeof output === "string" && output ? output : "-";
  }

  function routeBadge(route: TransitRouteData) {
    if (route.forwarding_method === "socat" && route.listen_port === 18443) {
      return "测试可用链路 / 待正式 cutover";
    }
    if (route.forwarding_method === "gost" && route.listen_port === 8443) {
      return "回退链路 / 保留";
    }
    return "只读线路";
  }

  function isSocatTestRoute(route: TransitRouteData) {
    return route.forwarding_method === "socat" && route.listen_port === 18443;
  }

  function activeNodeForRoute(route: TransitRouteData) {
    return nodes.find((node) => node.id === route.node_id && node.status === "active") ?? null;
  }

  function derivedSocatTestLinkForRoute(route: TransitRouteData) {
    if (!isSocatTestRoute(route)) {
      return null;
    }
    const node = activeNodeForRoute(route);
    const shareLink = node?.share_link;
    const transitHost = transitHostForRoute(route);
    if (!shareLink || !transitHost) {
      return null;
    }

    try {
      const url = new URL(shareLink);
      url.hostname = transitHost;
      url.port = String(route.listen_port);
      return url.toString();
    } catch {
      return shareLink.replace(/@([^:/?#]+)(?::\d+)?/, `@${transitHost}:${route.listen_port}`);
    }
  }

  const selectedResource = resources.find((resource) => resource.id === selectedResourceId) ?? null;
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? null;
  const selectableResources =
    forwardingMethod === "socat" ? resources.filter((resource) => resource.id === SOCAT_RESOURCE_ID) : resources;
  const result = task?.result_data ?? null;
  const resultRoute = objectValue(result?.["route"]);
  const resultGost = objectValue(result?.["gost"]);
  const resultSocat = objectValue(result?.["socat"]);
  const resultVerify = objectValue(result?.["verify"]);
  const resultShareLink = stringValue(resultRoute, "share_link");
  const resultMethod = stringValue(resultRoute, "forwarding_method");
  const resultListenPort = scalarValue(resultRoute, "listen_port");
  const resultTargetHost = stringValue(resultRoute, "target_host");
  const resultTargetPort = scalarValue(resultRoute, "target_port");
  const resultTransitHost = selectedResource?.entry_host ?? selectedResource?.ssh_host ?? null;
  const shouldShowSocatTestHint =
    resultMethod === "socat" && resultTransitHost !== null && resultListenPort !== "-";
  const failures = Array.isArray(result?.["failures"])
    ? result["failures"].filter((item) => typeof item === "string")
    : [];
  const warnings = Array.isArray(result?.["warnings"])
    ? result["warnings"].filter((item) => typeof item === "string")
    : [];

  return (
    <section className="panel wide">
      <div className="status-row">
        <h2>创建单条转发</h2>
        <button className="secondary" type="button" onClick={() => void loadData()}>
          刷新数据
        </button>
      </div>

      <div className="warning-box">
        <strong>⚠️ Cutover 状态：socat 18443 已通过客户端连通性测试，但尚未正式 cutover。</strong>
        <span>gost 8443 保留作为回退链路。当前不会修改正式节点链接。</span>
      </div>

      {forwardingMethod === "socat" ? (
        <div className="warning-box">
          <strong>Stage 3.3.3-fix-b1：只创建 socat 测试转发。</strong>
          <span>创建前请先在云服务器安全组/云防火墙放行 TCP {listenPort}。</span>
          <span>同时确认服务器防火墙允许 TCP {listenPort}。</span>
          <span>禁止使用 22 / 8443 / 20575。</span>
          <span>不替换 gost，不修改现有节点链接。</span>
          <span>本模式不生成 share_link；真实客户端链接仍需单独验收。</span>
        </div>
      ) : (
        <div className="warning-box">
          <strong>Stage 3.3.3 只创建一条 gost TCP 转发规则。</strong>
          <span>会在香港服务器创建 systemd 转发服务，并监听一个新端口。</span>
          <span>不会自动开放云安全组，不会修改防火墙，不会写 iptables。</span>
          <span>不会连接或修改落地 VPS，不会影响现有直连链接。</span>
          <span>20575 是 SSH 端口，不能作为中转监听端口。删除功能不在本阶段。</span>
        </div>
      )}

      <div className="route-layout">
        <div className="form route-form">
          <label>
            中转资源
            <select value={selectedResourceId} onChange={(event) => setSelectedResourceId(event.target.value)}>
              {selectableResources.length === 0 ? <option value="">暂无可用 active server 资源</option> : null}
              {selectableResources.map((resource) => (
                <option key={resource.id} value={resource.id}>
                  {resource.name} / {displayValue(resource.entry_host)}
                </option>
              ))}
            </select>
          </label>
          <label>
            active 节点
            <select value={selectedNodeId} onChange={(event) => setSelectedNodeId(event.target.value)}>
              {nodes.length === 0 ? <option value="">暂无 active 节点</option> : null}
              {nodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.node_name} / {displayValue(node.vps_ip)}:{displayValue(node.port)}
                </option>
              ))}
            </select>
          </label>
          <label>
            转发方式
            <select
              value={forwardingMethod}
              onChange={(event) => setForwardingMethod(event.target.value as ForwardingMethod)}
            >
              <option value="gost">gost</option>
              <option value="socat">socat</option>
            </select>
          </label>
          <label>
            规则名称
            <input value={routeName} onChange={(event) => setRouteName(event.target.value)} />
          </label>
          <label>
            监听端口
            <input
              min={1}
              max={65535}
              type="number"
              value={listenPort}
              onChange={(event) => setListenPort(event.target.value)}
            />
          </label>
          <label className="check-row">
            <input checked={confirm} type="checkbox" onChange={(event) => setConfirm(event.target.checked)} />
            <span>
              {forwardingMethod === "socat"
                ? `我确认已在云服务器安全组/云防火墙放行 TCP ${listenPort}，并确认服务器防火墙允许该端口。`
                : "我确认会创建远端 systemd 转发服务，且云安全组需手动放行。"}
            </span>
          </label>
          <label className="wide-field">
            SSH Key
            <textarea
              value={privateKeyText}
              onChange={(event) => setPrivateKeyText(event.target.value)}
              placeholder="粘贴香港服务器 SSH 私钥，仅临时加密写入 Redis。"
            />
          </label>
          <label>
            SSH Key 文件
            <input ref={fileInputRef} type="file" />
          </label>
          <label>
            Passphrase
            <input
              type="password"
              value={passphrase}
              onChange={(event) => setPassphrase(event.target.value)}
              placeholder="可选"
            />
          </label>
          <div className="wide-field">
            <button disabled={!confirm} type="button" onClick={() => void createTransitRoute()}>
              {forwardingMethod === "socat" ? "创建单条 socat 测试转发" : "创建单条 gost 转发"}
            </button>
          </div>
        </div>

        <div className="route-summary">
          <h3>本次目标</h3>
          <div className="detail-grid">
            <span>中转入口</span>
            <strong>
              {displayValue(selectedResource?.entry_host)}:{displayValue(listenPort)}
            </strong>
            <span>目标节点</span>
            <strong>{selectedNode?.node_name ?? "-"}</strong>
            <span>落地目标</span>
            <strong>
              {displayValue(selectedNode?.vps_ip)}:{displayValue(selectedNode?.port)}
            </strong>
            <span>限制</span>
            <strong>单条 / {forwardingMethod} / 不改防火墙</strong>
          </div>
        </div>
      </div>

      {routes.length > 0 ? (
        <div className="route-management">
          <div className="status-row">
            <div>
              <h3>中转线路管理</h3>
              <p className="message">只读查看现有 gost / socat 转发线路；本区域不停止、不删除、不重启线路。</p>
            </div>
          </div>
          <div className="diagnostic-credentials">
            <h4>诊断 / 重启 SSH 凭据</h4>
            <p className="message">只用于本次诊断或重启任务，临时加密写入 Redis；不会落库、不会回显、不会写入日志。</p>
            <div className="form route-form">
              <label className="wide-field">
                SSH Key
                <textarea
                  value={diagnosticPrivateKeyText}
                  onChange={(event) => setDiagnosticPrivateKeyText(event.target.value)}
                  placeholder="粘贴中转服务器 SSH 私钥，仅用于运行只读诊断。"
                />
              </label>
              <label>
                SSH Key 文件
                <input ref={diagnosticFileInputRef} type="file" />
              </label>
              <label>
                Passphrase
                <input
                  type="password"
                  value={diagnosticPassphrase}
                  onChange={(event) => setDiagnosticPassphrase(event.target.value)}
                  placeholder="可选"
                />
              </label>
            </div>
            <div className="warning-box">
              <span>运行只读诊断只会执行白名单诊断命令；重启按钮只对 socat 18443 测试链路开放。</span>
              <span>不提供停止、删除、创建入口，不允许操作 gost 8443 正式链路。</span>
            </div>
            <p className="message">{diagnosticMessage}</p>
          </div>
          {routes.map((route) => {
            const routeDiagnosticActive = diagnosticRouteId === route.id;
            const listenCheck = routeDiagnosticActive ? diagnosticCheckFor("listen_check") : null;
            const serviceStatus = routeDiagnosticActive ? diagnosticCheckFor("service_status") : null;
            const targetConnectivity = routeDiagnosticActive ? diagnosticCheckFor("target_connectivity") : null;
            const processCheck = routeDiagnosticActive ? diagnosticCheckFor("process_check") : null;
            const derivedSocatTestLink = derivedSocatTestLinkForRoute(route);
            return (
            <div className="route-card" key={route.id}>
              <div className="status-row">
                <div>
                  <h4>{route.name}</h4>
                  <p className="message">{routeBadge(route)}</p>
                </div>
                <div className="route-card-actions">
                  <span className={`pill ${route.status === "active" ? "ok" : "bad"}`}>{route.status}</span>
                  <button className="secondary compact" type="button" onClick={() => void diagnoseRoute(route)}>
                    运行只读诊断
                  </button>
                  {isSocatTestRoute(route) ? (
                    <button className="secondary compact" type="button" onClick={() => void restartSocatRoute(route)}>
                      重启测试链路
                    </button>
                  ) : null}
                </div>
              </div>
              <div className="detail-grid">
                <span>route_name</span>
                <strong>{route.name}</strong>
                <span>method</span>
                <strong>{route.forwarding_method}</strong>
                <span>listen_ip / transit_ip</span>
                <strong>{displayValue(transitHostForRoute(route))}</strong>
                <span>listen_port</span>
                <strong>{route.listen_port}</strong>
                <span>target_host</span>
                <strong>{route.target_host}</strong>
                <span>target_port</span>
                <strong>{route.target_port}</strong>
                <span>systemd service</span>
                <strong>{route.service_name}</strong>
                <span>本地测试命令</span>
                <strong>
                  nc -vz {displayValue(transitHostForRoute(route))} {route.listen_port}
                </strong>
              </div>
              <div className="warning-box">
                <span>请确认云服务器安全组/云防火墙已放行 TCP {route.listen_port}。</span>
                <span>如果本地 nc timeout，优先检查云安全组/云防火墙和本机代理测试路径。</span>
                {route.forwarding_method === "socat" ? (
                  <span>socat 测试新增仍禁止使用 22 / 8443 / 20575。</span>
                ) : null}
                {route.forwarding_method === "gost" && route.listen_port === 8443 ? (
                  <span>此链路保留为回退链路。此前与 Xray Reality 兼容性存在问题，不建议作为当前优先测试入口。</span>
                ) : null}
              </div>
              {isSocatTestRoute(route) ? (
                <div className="diagnostic-box">
                  <h5>socat 测试链接</h5>
                  <p className="message">
                    此链接由当前直连 Reality 节点派生，仅将 server 改为 {displayValue(transitHostForRoute(route))}，
                    port 改为 {route.listen_port}。不会写入数据库，也不会替换正式节点链接。
                  </p>
                  {derivedSocatTestLink ? (
                    <div className="route-copy-row">
                      <span className="route-share-link">{maskLink(derivedSocatTestLink)}</span>
                      <button
                        className="secondary compact"
                        type="button"
                        onClick={() => void copySocatTestLink(route)}
                      >
                        {copiedSocatTestRouteId === route.id ? "已复制" : "复制 socat 中转测试链接"}
                      </button>
                    </div>
                  ) : (
                    <div className="warning-box">
                      <span>当前页面缺少 node.share_link，暂不能生成派生链接。</span>
                    </div>
                  )}
                </div>
              ) : null}
              <div className="diagnostic-box">
                <div className="status-row">
                  <h5>诊断命令</h5>
                  <button className="secondary compact" type="button" onClick={() => void copyDiagnostics(route)}>
                    {copiedDiagnosticsRouteId === route.id ? "已复制" : "复制诊断命令"}
                  </button>
                </div>
                <div className="diagnostic-list">
                  {diagnosticCommandsForRoute(route).map((item) => (
                    <div className="diagnostic-row" key={`${route.id}-${item.label}`}>
                      <span>{item.label}</span>
                      <code>{item.command}</code>
                    </div>
                  ))}
                </div>
                <div className="warning-box">
                  <span>nc timeout：优先检查云安全组/云防火墙 TCP {route.listen_port} 是否放行。</span>
                  <span>ss 没有监听：说明转发服务未启动或已退出。</span>
                  <span>目标 nc 不通：说明中转机到落地机不通。</span>
                  <span>本机开代理客户端时，nc/curl 测试路径可能被代理规则污染。</span>
                </div>
              </div>
              {routeDiagnosticActive && diagnosticTask ? (
                <div className="diagnostic-result">
                  <h5>只读诊断结果</h5>
                  <div className="detail-grid">
                    <span>任务状态</span>
                    <strong>{diagnosticTask.status}</strong>
                    <span>当前步骤</span>
                    <strong>{diagnosticTask.current_step ?? "-"}</strong>
                    <span>进度</span>
                    <strong>{diagnosticTask.progress}%</strong>
                    <span>错误码</span>
                    <strong>{diagnosticTask.error_code ?? "-"}</strong>
                  </div>
                  {(diagnosticTask.result_data?.["classification"] === "restart_socat_route"
                    ? [
                        ["restart_result", diagnosticCheckFor("restart_result")],
                        ["service_status", serviceStatus],
                        ["listen_check", listenCheck],
                        ["target_connectivity", targetConnectivity],
                      ]
                    : [
                        ["listen_check", listenCheck],
                        ["service_status", serviceStatus],
                        ["target_connectivity", targetConnectivity],
                        ["process_check", processCheck],
                      ]
                  ).map(([key, check]) => {
                    const checkRecord = objectValue(check);
                    return (
                      <div className="diagnostic-output" key={String(key)}>
                        <div className="status-row">
                          <strong>{String(key)}</strong>
                          <span className={`pill ${checkRecord?.["ok"] === true ? "ok" : "bad"}`}>
                            {checkRecord ? String(checkRecord["ok"]) : "-"}
                          </span>
                        </div>
                        <code>{typeof checkRecord?.["command"] === "string" ? checkRecord["command"] : "-"}</code>
                        <pre>{checkOutput(checkRecord)}</pre>
                      </div>
                    );
                  })}
                  {diagnosticLogs.length > 0 ? (
                    <div className="log-list">
                      {diagnosticLogs.map((log) => (
                        <div className="log-row" key={log.id}>
                          <span>{log.level}</span>
                          <span>{log.step ?? "-"}</span>
                          <span>{log.message}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {route.share_link ? (
                <div className="route-copy-row">
                  <span className="route-share-link">{maskLink(route.share_link)}</span>
                  <button
                    className="secondary compact"
                    disabled={!route.share_link}
                    type="button"
                    onClick={() => void copyRouteLink(route)}
                  >
                    {copiedRouteId === route.id ? "已复制" : "复制中转链接"}
                  </button>
                </div>
              ) : null}
            </div>
            );
          })}
        </div>
      ) : null}

      {task ? (
        <div className="task-card">
          <div className="detail-grid">
            <span>任务类型</span>
            <strong>{task.task_type}</strong>
            <span>任务状态</span>
            <strong>{task.status}</strong>
            <span>当前步骤</span>
            <strong>{task.current_step ?? "-"}</strong>
            <span>进度</span>
            <strong>{task.progress}%</strong>
            <span>错误码</span>
            <strong>{task.error_code ?? "-"}</strong>
            <span>错误信息</span>
            <strong>{task.error_message ?? "-"}</strong>
          </div>

          {failures.length > 0 ? (
            <div className="failure-box">
              {failures.map((failure) => (
                <div key={failure}>{failure}</div>
              ))}
            </div>
          ) : null}
          {warnings.length > 0 ? (
            <div className="warning-box">
              {warnings.map((warning) => (
                <div key={warning}>{warning}</div>
              ))}
            </div>
          ) : null}

          {resultRoute ? (
            <div className="transit-read-result">
              <h4>中转规则结果</h4>
              <div className="detail-grid">
                <span>route_name</span>
                <strong>{stringValue(resultRoute, "name")}</strong>
                <span>method</span>
                <strong>{resultMethod}</strong>
                <span>listen_port</span>
                <strong>{resultListenPort}</strong>
                <span>target</span>
                <strong>
                  {resultTargetHost}:{resultTargetPort}
                </strong>
                <span>service</span>
                <strong>{stringValue(resultRoute, "service_name")}</strong>
                <span>status</span>
                <strong>{stringValue(resultRoute, "status")}</strong>
                <span>gost</span>
                <strong>{stringValue(resultGost, "version")}</strong>
                <span>socat</span>
                <strong>{stringValue(resultSocat, "version")}</strong>
                <span>service active</span>
                <strong>{String(resultVerify?.["service_active"] ?? "-")}</strong>
                <span>listening</span>
                <strong>{String(resultVerify?.["listening"] ?? "-")}</strong>
              </div>
              {resultShareLink !== "-" ? (
                <>
                  <label className="share-export">
                    中转版分享链接
                    <textarea className="share-link-value" readOnly value={maskLink(resultShareLink)} />
                  </label>
                  <div className="transit-actions">
                    <button type="button" onClick={() => void copyTransitLink()}>
                      复制中转链接
                    </button>
                  </div>
                </>
              ) : null}
              {shouldShowSocatTestHint ? (
                <div className="warning-box">
                  <strong>创建后本地连通性校验</strong>
                  <span>在本机终端执行：</span>
                  <code>
                    nc -vz {resultTransitHost} {resultListenPort}
                  </code>
                  <span>如果 nc timeout，优先检查云安全组/云防火墙 TCP {resultListenPort} 是否放行。</span>
                  <span>如果本机开启代理客户端，请先确认测试路径没有被代理规则污染。</span>
                </div>
              ) : null}
              <p className="message">本阶段不提供删除转发入口，删除功能将在后续阶段实现。</p>
              {copied ? <p className="message">已复制中转版 vless:// 链接。</p> : null}
            </div>
          ) : null}

          {logs.length > 0 ? (
            <div className="log-list">
              {logs.map((log) => (
                <div className="log-row" key={log.id}>
                  <span>{log.level}</span>
                  <span>{log.step ?? "-"}</span>
                  <span>{log.message}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <p className="message">{message}</p>
    </section>
  );
}
