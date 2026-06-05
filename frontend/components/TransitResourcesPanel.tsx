"use client";

import { useEffect, useRef, useState } from "react";

import {
  apiFetch,
  apiFormFetch,
  type CsrfResult,
  type TaskData,
  type TaskLogData,
  type TransitGostInstallResult,
  type TransitResourceData,
  type TransitResourceListResult,
  type TransitResourcePayload,
  type TransitServerReadResult,
  type TransitSocatInstallResult,
} from "@/lib/api";

const terminalStatuses = new Set(["success", "failed", "cancelled", "timeout"]);

const resourceTypeLabels: Record<string, string> = {
  server: "普通中转服务器",
  iepl: "IEPL 线路",
  iplc: "IPLC 线路",
  other: "其他",
};

const protocolLabels: Record<string, string> = {
  tcp: "TCP",
  udp: "UDP",
  tcp_udp: "TCP + UDP",
  unknown: "未知",
};

const statusLabels: Record<string, string> = {
  active: "启用",
  disabled: "禁用",
};

const defaultForm: TransitResourcePayload = {
  name: "",
  resource_type: "server",
  provider: null,
  entry_host: null,
  entry_port: null,
  entry_region: null,
  exit_region: null,
  bandwidth_mbps: null,
  traffic_limit_gb: null,
  traffic_used_gb: null,
  protocol_hint: "unknown",
  has_ssh: false,
  ssh_host: null,
  ssh_port: null,
  ssh_username: null,
  status: "active",
  expires_at: null,
  notes: null,
};

function cleanText(value: string) {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function numberOrNull(value: string) {
  if (!value.trim()) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function localInputToIso(value: string) {
  if (!value) {
    return null;
  }
  return new Date(value).toISOString();
}

function isoToLocalInput(value: string | null) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function displayDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "-";
}

function displayValue(value: string | number | null) {
  return value === null || value === "" ? "-" : String(value);
}

function displayBoolean(value: unknown) {
  return value === true ? "是" : "否";
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

function numberListValue(value: unknown) {
  return Array.isArray(value)
    ? value.filter((item) => typeof item === "number").join(", ") || "-"
    : "-";
}

function stringListValue(value: unknown) {
  return Array.isArray(value)
    ? value.filter((item) => typeof item === "string").join(" / ") || "-"
    : "-";
}

function maskHost(value: string | null) {
  if (!value) {
    return "-";
  }
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(value)) {
    const parts = value.split(".");
    return `${parts[0]}.${parts[1]}.*.*`;
  }
  if (value.length <= 10) {
    return value;
  }
  return `${value.slice(0, 4)}...${value.slice(-4)}`;
}

function resourceToForm(resource: TransitResourceData): TransitResourcePayload {
  return {
    name: resource.name,
    resource_type: resource.resource_type,
    provider: resource.provider,
    entry_host: resource.entry_host,
    entry_port: resource.entry_port,
    entry_region: resource.entry_region,
    exit_region: resource.exit_region,
    bandwidth_mbps: resource.bandwidth_mbps,
    traffic_limit_gb: resource.traffic_limit_gb,
    traffic_used_gb: resource.traffic_used_gb,
    protocol_hint: resource.protocol_hint,
    has_ssh: resource.has_ssh,
    ssh_host: resource.ssh_host,
    ssh_port: resource.ssh_port,
    ssh_username: resource.ssh_username,
    status: resource.status,
    expires_at: resource.expires_at,
    notes: resource.notes,
  };
}

export function TransitResourcesPanel() {
  const readFileInputRef = useRef<HTMLInputElement | null>(null);
  const installFileInputRef = useRef<HTMLInputElement | null>(null);
  const socatFileInputRef = useRef<HTMLInputElement | null>(null);
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [selectedResource, setSelectedResource] = useState<TransitResourceData | null>(null);
  const [form, setForm] = useState<TransitResourcePayload>(defaultForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [message, setMessage] = useState("中转资源只会写入本地数据库，不会连接远端。");
  const [loading, setLoading] = useState(false);
  const [readPrivateKeyText, setReadPrivateKeyText] = useState("");
  const [readPassphrase, setReadPassphrase] = useState("");
  const [readTask, setReadTask] = useState<TaskData | null>(null);
  const [readLogs, setReadLogs] = useState<TaskLogData[]>([]);
  const [installPrivateKeyText, setInstallPrivateKeyText] = useState("");
  const [installPassphrase, setInstallPassphrase] = useState("");
  const [installTask, setInstallTask] = useState<TaskData | null>(null);
  const [installLogs, setInstallLogs] = useState<TaskLogData[]>([]);
  const [socatPrivateKeyText, setSocatPrivateKeyText] = useState("");
  const [socatPassphrase, setSocatPassphrase] = useState("");
  const [socatTask, setSocatTask] = useState<TaskData | null>(null);
  const [socatLogs, setSocatLogs] = useState<TaskLogData[]>([]);

  async function ensureCsrfToken() {
    const csrf = await apiFetch<CsrfResult>("/api/auth/csrf");
    if (!csrf.success) {
      throw new Error(csrf.message);
    }
    return csrf.data.csrf_token;
  }

  async function loadResources(nextSelectedId?: string) {
    const result = await apiFetch<TransitResourceListResult>("/api/transit-resources");
    if (!result.success) {
      setMessage(result.message);
      return;
    }
    setResources(result.data.resources);
    const nextSelected =
      result.data.resources.find((item) => item.id === nextSelectedId) ??
      result.data.resources.find((item) => item.id === selectedResource?.id) ??
      result.data.resources[0] ??
      null;
    if (nextSelected) {
      await loadResource(nextSelected.id);
    } else {
      setSelectedResource(null);
    }
  }

  async function loadResource(resourceId: string) {
    const result = await apiFetch<TransitResourceData>(`/api/transit-resources/${resourceId}`);
    if (result.success) {
      setSelectedResource(result.data);
    } else {
      setMessage(result.message);
    }
  }

  useEffect(() => {
    void loadResources();
  }, []);

  useEffect(() => {
    setReadTask(null);
    setReadLogs([]);
    setReadPrivateKeyText("");
    setReadPassphrase("");
    setInstallTask(null);
    setInstallLogs([]);
    setInstallPrivateKeyText("");
    setInstallPassphrase("");
    setSocatTask(null);
    setSocatLogs([]);
    setSocatPrivateKeyText("");
    setSocatPassphrase("");
    if (readFileInputRef.current) {
      readFileInputRef.current.value = "";
    }
    if (installFileInputRef.current) {
      installFileInputRef.current.value = "";
    }
    if (socatFileInputRef.current) {
      socatFileInputRef.current.value = "";
    }
  }, [selectedResource?.id]);

  useEffect(() => {
    if (!readTask?.id || terminalStatuses.has(readTask.status)) {
      return;
    }

    const timer = window.setTimeout(() => {
      void loadReadTask(readTask.id);
    }, 2000);

    return () => window.clearTimeout(timer);
  }, [readTask]);

  useEffect(() => {
    if (!installTask?.id || terminalStatuses.has(installTask.status)) {
      return;
    }

    const timer = window.setTimeout(() => {
      void loadInstallTask(installTask.id);
    }, 2000);

    return () => window.clearTimeout(timer);
  }, [installTask]);

  useEffect(() => {
    if (!socatTask?.id || terminalStatuses.has(socatTask.status)) {
      return;
    }

    const timer = window.setTimeout(() => {
      void loadSocatTask(socatTask.id);
    }, 2000);

    return () => window.clearTimeout(timer);
  }, [socatTask]);

  function updateForm<K extends keyof TransitResourcePayload>(
    key: K,
    value: TransitResourcePayload[K],
  ) {
    setForm((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function resetForm() {
    setForm(defaultForm);
    setEditingId(null);
  }

  function startEdit(resource: TransitResourceData) {
    setEditingId(resource.id);
    setForm(resourceToForm(resource));
    setMessage("正在编辑中转资源。本阶段仍不会测试连接或配置中转。");
  }

  function buildPayload(): TransitResourcePayload {
    return {
      ...form,
      name: form.name.trim(),
      provider: cleanText(form.provider ?? ""),
      entry_host: cleanText(form.entry_host ?? ""),
      entry_region: cleanText(form.entry_region ?? ""),
      exit_region: cleanText(form.exit_region ?? ""),
      ssh_host: form.has_ssh ? cleanText(form.ssh_host ?? "") : null,
      ssh_port: form.has_ssh ? form.ssh_port : null,
      ssh_username: form.has_ssh ? cleanText(form.ssh_username ?? "") : null,
      notes: cleanText(form.notes ?? ""),
    };
  }

  async function submitForm() {
    const payload = buildPayload();
    if (!payload.name) {
      setMessage("请填写中转资源名称。");
      return;
    }

    setLoading(true);
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await apiFetch<TransitResourceData>(
        editingId ? `/api/transit-resources/${editingId}` : "/api/transit-resources",
        {
          method: editingId ? "PATCH" : "POST",
          headers: { "X-CSRF-Token": csrfToken },
          body: JSON.stringify(payload),
        },
      );
      if (!result.success) {
        setMessage(result.message);
        return;
      }
      setMessage(result.message);
      resetForm();
      await loadResources(result.data.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存中转资源失败。");
    } finally {
      setLoading(false);
    }
  }

  async function toggleResource(resource: TransitResourceData, nextAction: "enable" | "disable") {
    setLoading(true);
    try {
      const csrfToken = await ensureCsrfToken();
      const result = await apiFetch<TransitResourceData>(
        `/api/transit-resources/${resource.id}/${nextAction}`,
        {
          method: "POST",
          headers: { "X-CSRF-Token": csrfToken },
          body: JSON.stringify({}),
        },
      );
      if (!result.success) {
        setMessage(result.message);
        return;
      }
      setMessage(result.message);
      await loadResources(result.data.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "更新中转资源状态失败。");
    } finally {
      setLoading(false);
    }
  }

  async function loadReadTask(taskId: string) {
    const [taskResult, logsResult] = await Promise.all([
      apiFetch<TaskData>(`/api/tasks/${taskId}`),
      apiFetch<{ logs: TaskLogData[] }>(`/api/tasks/${taskId}/logs`),
    ]);

    if (taskResult.success) {
      setReadTask(taskResult.data);
      const taskMessage = taskResult.data.result_data?.["message"];
      if (typeof taskMessage === "string") {
        setMessage(taskMessage);
      } else if (taskResult.data.error_message) {
        setMessage(taskResult.data.error_message);
      }
    } else {
      setMessage(taskResult.message);
    }

    if (logsResult.success) {
      setReadLogs(logsResult.data.logs);
    }
  }

  function buildReadForm() {
    const formData = new FormData();
    formData.append("ssh_key_passphrase", readPassphrase);
    if (readPrivateKeyText.trim()) {
      formData.append("private_key_text", readPrivateKeyText);
    }
    const file = readFileInputRef.current?.files?.[0];
    if (file) {
      formData.append("private_key_file", file);
    }
    return formData;
  }

  function buildInstallForm() {
    const formData = new FormData();
    formData.append("ssh_key_passphrase", installPassphrase);
    if (installPrivateKeyText.trim()) {
      formData.append("private_key_text", installPrivateKeyText);
    }
    const file = installFileInputRef.current?.files?.[0];
    if (file) {
      formData.append("private_key_file", file);
    }
    return formData;
  }

  function buildSocatForm() {
    const formData = new FormData();
    formData.append("ssh_key_passphrase", socatPassphrase);
    if (socatPrivateKeyText.trim()) {
      formData.append("private_key_text", socatPrivateKeyText);
    }
    const file = socatFileInputRef.current?.files?.[0];
    if (file) {
      formData.append("private_key_file", file);
    }
    return formData;
  }

  function clearReadCredentials() {
    setReadPrivateKeyText("");
    setReadPassphrase("");
    if (readFileInputRef.current) {
      readFileInputRef.current.value = "";
    }
  }

  function clearInstallCredentials() {
    setInstallPrivateKeyText("");
    setInstallPassphrase("");
    if (installFileInputRef.current) {
      installFileInputRef.current.value = "";
    }
  }

  function clearSocatCredentials() {
    setSocatPrivateKeyText("");
    setSocatPassphrase("");
    if (socatFileInputRef.current) {
      socatFileInputRef.current.value = "";
    }
  }

  async function runReadTransitServer() {
    if (!selectedResource) {
      setMessage("请先选择中转资源。");
      return;
    }

    try {
      setMessage("正在创建中转服务器只读检查任务。");
      const csrfToken = await ensureCsrfToken();
      const result = await apiFormFetch<TransitServerReadResult>(
        `/api/transit-resources/${selectedResource.id}/read-server`,
        buildReadForm(),
        {
          headers: { "X-CSRF-Token": csrfToken },
        },
      );
      clearReadCredentials();

      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }

      setMessage("中转服务器只读检查任务已创建。");
      await loadReadTask(result.data.task_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "中转服务器只读检查任务创建失败。");
    }
  }

  async function loadInstallTask(taskId: string) {
    const [taskResult, logsResult] = await Promise.all([
      apiFetch<TaskData>(`/api/tasks/${taskId}`),
      apiFetch<{ logs: TaskLogData[] }>(`/api/tasks/${taskId}/logs`),
    ]);

    if (taskResult.success) {
      setInstallTask(taskResult.data);
      const taskMessage = taskResult.data.result_data?.["message"];
      if (typeof taskMessage === "string") {
        setMessage(taskMessage);
      } else if (taskResult.data.error_message) {
        setMessage(taskResult.data.error_message);
      }
    } else {
      setMessage(taskResult.message);
    }

    if (logsResult.success) {
      setInstallLogs(logsResult.data.logs);
    }
  }

  async function loadSocatTask(taskId: string) {
    const [taskResult, logsResult] = await Promise.all([
      apiFetch<TaskData>(`/api/tasks/${taskId}`),
      apiFetch<{ logs: TaskLogData[] }>(`/api/tasks/${taskId}/logs`),
    ]);

    if (taskResult.success) {
      setSocatTask(taskResult.data);
      const taskMessage = taskResult.data.result_data?.["message"];
      if (typeof taskMessage === "string") {
        setMessage(taskMessage);
      } else if (taskResult.data.error_message) {
        setMessage(taskResult.data.error_message);
      }
    } else {
      setMessage(taskResult.message);
    }

    if (logsResult.success) {
      setSocatLogs(logsResult.data.logs);
    }
  }

  async function runInstallGost() {
    if (!selectedResource) {
      setMessage("请先选择中转资源。");
      return;
    }

    try {
      setMessage("正在创建 gost binary 安装任务。");
      const csrfToken = await ensureCsrfToken();
      const result = await apiFormFetch<TransitGostInstallResult>(
        `/api/transit-resources/${selectedResource.id}/install-gost`,
        buildInstallForm(),
        {
          headers: { "X-CSRF-Token": csrfToken },
        },
      );
      clearInstallCredentials();

      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }

      setMessage("gost binary 安装任务已创建。");
      await loadInstallTask(result.data.task_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "gost binary 安装任务创建失败。");
    }
  }

  async function runInstallSocat() {
    if (!selectedResource) {
      setMessage("请先选择中转资源。");
      return;
    }

    try {
      setMessage("正在创建 socat 安装/检查任务。");
      const csrfToken = await ensureCsrfToken();
      const result = await apiFormFetch<TransitSocatInstallResult>(
        `/api/transit-resources/${selectedResource.id}/install-socat`,
        buildSocatForm(),
        {
          headers: { "X-CSRF-Token": csrfToken },
        },
      );
      clearSocatCredentials();

      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }

      setMessage("socat 安装/检查任务已创建。");
      await loadSocatTask(result.data.task_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "socat 安装/检查任务创建失败。");
    }
  }

  const canReadTransitServer =
    selectedResource?.resource_type === "server" &&
    selectedResource.has_ssh &&
    selectedResource.status === "active";
  const readResult = readTask?.result_data ?? null;
  const readSystem = objectValue(readResult?.["system"]);
  const readTools = objectValue(readResult?.["tools"]);
  const readPorts = objectValue(readResult?.["ports"]);
  const readFirewall = objectValue(readResult?.["firewall"]);
  const readFailures = Array.isArray(readResult?.["failures"])
    ? readResult["failures"].filter((item) => typeof item === "string")
    : [];
  const readWarnings = Array.isArray(readResult?.["warnings"])
    ? readResult["warnings"].filter((item) => typeof item === "string")
    : [];
  const canInstallGost = canReadTransitServer;
  const installResult = installTask?.result_data ?? null;
  const installGost = objectValue(installResult?.["gost"]);
  const installSystem = objectValue(installResult?.["system"]);
  const installFailures = Array.isArray(installResult?.["failures"])
    ? installResult["failures"].filter((item) => typeof item === "string")
    : [];
  const installWarnings = Array.isArray(installResult?.["warnings"])
    ? installResult["warnings"].filter((item) => typeof item === "string")
    : [];
  const canInstallSocat = canReadTransitServer;
  const socatResult = socatTask?.result_data ?? null;
  const installSocat = objectValue(socatResult?.["socat"]);
  const socatSystem = objectValue(socatResult?.["system"]);
  const socatFailures = Array.isArray(socatResult?.["failures"])
    ? socatResult["failures"].filter((item) => typeof item === "string")
    : [];
  const socatWarnings = Array.isArray(socatResult?.["warnings"])
    ? socatResult["warnings"].filter((item) => typeof item === "string")
    : [];

  return (
    <section className="panel wide">
      <h2>中转资源</h2>
      <div className="warning-box">
        <strong>中转资源管理不会配置真实中转。</strong>
        <span>Stage 3.3.1 仅对 server 资源提供只读检查；不会连接落地 VPS，不会安装工具或修改防火墙。</span>
        <span>不要在备注中填写密码、私钥、后台账号或专线密钥。</span>
      </div>

      <div className="transit-layout">
        <div>
          {resources.length === 0 ? (
            <div className="empty">还没有中转资源。可以先录入普通服务器、IEPL 或 IPLC 信息。</div>
          ) : (
            <div className="transit-table">
              {resources.map((resource) => (
                <button
                  className={`transit-row-button ${
                    selectedResource?.id === resource.id ? "active" : ""
                  }`}
                  key={resource.id}
                  onClick={() => void loadResource(resource.id)}
                  type="button"
                >
                  <span>{resource.name}</span>
                  <span>{resourceTypeLabels[resource.resource_type] ?? resource.resource_type}</span>
                  <span>{statusLabels[resource.status] ?? resource.status}</span>
                  <span>{displayValue(resource.provider)}</span>
                  <span>{displayValue(resource.entry_region)}</span>
                  <span>{displayValue(resource.exit_region)}</span>
                  <span>{maskHost(resource.entry_host)}</span>
                  <span>{displayValue(resource.entry_port)}</span>
                  <span>{displayValue(resource.bandwidth_mbps)}</span>
                  <span>{displayDate(resource.expires_at)}</span>
                </button>
              ))}
            </div>
          )}

          {selectedResource && (
            <div className="transit-detail">
              <h3>{selectedResource.name}</h3>
              <div className="detail-grid">
                <span>类型</span>
                <strong>
                  {resourceTypeLabels[selectedResource.resource_type] ??
                    selectedResource.resource_type}
                </strong>
                <span>状态</span>
                <strong>{statusLabels[selectedResource.status] ?? selectedResource.status}</strong>
                <span>服务商</span>
                <strong>{displayValue(selectedResource.provider)}</strong>
                <span>入口</span>
                <strong>
                  {displayValue(selectedResource.entry_host)}:{displayValue(selectedResource.entry_port)}
                </strong>
                <span>地区</span>
                <strong>
                  {displayValue(selectedResource.entry_region)} → {displayValue(selectedResource.exit_region)}
                </strong>
                <span>协议提示</span>
                <strong>
                  {protocolLabels[selectedResource.protocol_hint] ?? selectedResource.protocol_hint}
                </strong>
                <span>带宽</span>
                <strong>{displayValue(selectedResource.bandwidth_mbps)} Mbps</strong>
                <span>流量</span>
                <strong>
                  {displayValue(selectedResource.traffic_used_gb)} /{" "}
                  {displayValue(selectedResource.traffic_limit_gb)} GB
                </strong>
                <span>SSH 元数据</span>
                <strong>
                  {selectedResource.has_ssh
                    ? `${displayValue(selectedResource.ssh_username)}@${displayValue(
                        selectedResource.ssh_host,
                      )}:${displayValue(selectedResource.ssh_port)}`
                    : "未记录"}
                </strong>
                <span>到期时间</span>
                <strong>{displayDate(selectedResource.expires_at)}</strong>
                <span>备注</span>
                <strong>{displayValue(selectedResource.notes)}</strong>
              </div>
              <div className="transit-actions">
                <button type="button" onClick={() => startEdit(selectedResource)}>
                  编辑资源
                </button>
                {selectedResource.status === "active" ? (
                  <button
                    className="secondary"
                    disabled={loading}
                    onClick={() => void toggleResource(selectedResource, "disable")}
                    type="button"
                  >
                    禁用
                  </button>
                ) : (
                  <button
                    disabled={loading}
                    onClick={() => void toggleResource(selectedResource, "enable")}
                    type="button"
                  >
                    启用
                  </button>
                )}
              </div>

              {canReadTransitServer ? (
                <div className="transit-read-panel">
                  <h3>读取中转服务器</h3>
                  <div className="warning-box">
                    <div>Stage 3.3.1 只做只读检查。</div>
                    <div>不安装 gost，不配置转发，不修改防火墙，不连接落地 VPS。</div>
                  </div>

                  <div className="form credential-grid">
                    <label>
                      SSH Key
                      <textarea
                        value={readPrivateKeyText}
                        onChange={(event) => setReadPrivateKeyText(event.target.value)}
                        placeholder="粘贴 SSH 私钥，仅临时加密写入 Redis。"
                      />
                    </label>
                    <label>
                      SSH Key 文件
                      <input ref={readFileInputRef} type="file" />
                    </label>
                    <label>
                      Passphrase
                      <input
                        type="password"
                        value={readPassphrase}
                        onChange={(event) => setReadPassphrase(event.target.value)}
                        placeholder="可选"
                      />
                    </label>
                  </div>
                  <div className="transit-actions">
                    <button type="button" onClick={() => void runReadTransitServer()}>
                      读取中转服务器
                    </button>
                  </div>

                  {readTask ? (
                    <div className="task-card">
                      <div className="detail-grid">
                        <span>任务类型</span>
                        <strong>{readTask.task_type}</strong>
                        <span>任务状态</span>
                        <strong>{readTask.status}</strong>
                        <span>当前步骤</span>
                        <strong>{readTask.current_step ?? "-"}</strong>
                        <span>进度</span>
                        <strong>{readTask.progress}%</strong>
                        <span>错误码</span>
                        <strong>{readTask.error_code ?? "-"}</strong>
                        <span>错误信息</span>
                        <strong>{readTask.error_message ?? "-"}</strong>
                      </div>

                      {readFailures.length > 0 ? (
                        <div className="failure-box">
                          {readFailures.map((failure) => (
                            <div key={failure}>{failure}</div>
                          ))}
                        </div>
                      ) : null}
                      {readWarnings.length > 0 ? (
                        <div className="warning-box">
                          {readWarnings.map((warning) => (
                            <div key={warning}>{warning}</div>
                          ))}
                        </div>
                      ) : null}

                      {readResult ? (
                        <div className="transit-read-result">
                          <h4>只读检查结果</h4>
                          <div className="detail-grid">
                            <span>系统</span>
                            <strong>
                              {stringValue(readSystem, "name")} / {stringValue(readSystem, "version_id")}
                            </strong>
                            <span>架构</span>
                            <strong>{stringValue(readSystem, "architecture")}</strong>
                            <span>whoami</span>
                            <strong>{stringValue(readSystem, "whoami")}</strong>
                            <span>root</span>
                            <strong>{displayBoolean(readSystem?.["is_root"])}</strong>
                            <span>systemd</span>
                            <strong>{displayBoolean(readSystem?.["systemd_available"])}</strong>
                            <span>监听端口</span>
                            <strong>{numberListValue(readPorts?.["listening_tcp"])}</strong>
                          </div>

                          <div className="tool-grid">
                            {["gost", "nginx", "socat", "xray"].map((name) => {
                              const tool = objectValue(readTools?.[name]);
                              return (
                                <div key={name}>
                                  <span>{name}</span>
                                  <strong>
                                    {displayBoolean(tool?.["available"])} / {stringValue(tool, "path")}
                                  </strong>
                                </div>
                              );
                            })}
                          </div>

                          <div className="detail-grid">
                            <span>ufw</span>
                            <strong>
                              {displayBoolean(objectValue(readFirewall?.["ufw"])?.["available"])} /{" "}
                              {stringListValue(objectValue(readFirewall?.["ufw"])?.["summary"])}
                            </strong>
                            <span>iptables</span>
                            <strong>
                              {displayBoolean(objectValue(readFirewall?.["iptables"])?.["available"])} /{" "}
                              {stringListValue(objectValue(readFirewall?.["iptables"])?.["summary"])}
                            </strong>
                            <span>firewalld</span>
                            <strong>
                              {displayBoolean(objectValue(readFirewall?.["firewalld"])?.["available"])} /{" "}
                              {stringValue(objectValue(readFirewall?.["firewalld"]), "state")}
                            </strong>
                          </div>
                        </div>
                      ) : null}

                      {readLogs.length > 0 ? (
                        <div className="log-list">
                          {readLogs.map((log) => (
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
                </div>
              ) : null}

              {canInstallGost ? (
                <div className="transit-read-panel">
                  <h3>安装 gost</h3>
                  <div className="warning-box">
                    <div>Stage 3.3.2 只安装 gost binary。</div>
                    <div>不创建转发，不监听新端口，不开放端口，不修改防火墙，不连接落地 VPS。</div>
                    <div>20575 当前为 SSH 端口，后续不得作为中转监听端口。</div>
                  </div>

                  <div className="form credential-grid">
                    <label>
                      SSH Key
                      <textarea
                        value={installPrivateKeyText}
                        onChange={(event) => setInstallPrivateKeyText(event.target.value)}
                        placeholder="粘贴 SSH 私钥，仅临时加密写入 Redis。"
                      />
                    </label>
                    <label>
                      SSH Key 文件
                      <input ref={installFileInputRef} type="file" />
                    </label>
                    <label>
                      Passphrase
                      <input
                        type="password"
                        value={installPassphrase}
                        onChange={(event) => setInstallPassphrase(event.target.value)}
                        placeholder="可选"
                      />
                    </label>
                  </div>
                  <div className="transit-actions">
                    <button type="button" onClick={() => void runInstallGost()}>
                      安装 gost
                    </button>
                  </div>

                  {installTask ? (
                    <div className="task-card">
                      <div className="detail-grid">
                        <span>任务类型</span>
                        <strong>{installTask.task_type}</strong>
                        <span>任务状态</span>
                        <strong>{installTask.status}</strong>
                        <span>当前步骤</span>
                        <strong>{installTask.current_step ?? "-"}</strong>
                        <span>进度</span>
                        <strong>{installTask.progress}%</strong>
                        <span>错误码</span>
                        <strong>{installTask.error_code ?? "-"}</strong>
                        <span>错误信息</span>
                        <strong>{installTask.error_message ?? "-"}</strong>
                      </div>

                      {installFailures.length > 0 ? (
                        <div className="failure-box">
                          {installFailures.map((failure) => (
                            <div key={failure}>{failure}</div>
                          ))}
                        </div>
                      ) : null}
                      {installWarnings.length > 0 ? (
                        <div className="warning-box">
                          {installWarnings.map((warning) => (
                            <div key={warning}>{warning}</div>
                          ))}
                        </div>
                      ) : null}

                      {installResult ? (
                        <div className="transit-read-result">
                          <h4>安装结果</h4>
                          <div className="detail-grid">
                            <span>installed</span>
                            <strong>{displayBoolean(installResult["installed"])}</strong>
                            <span>already_installed</span>
                            <strong>{displayBoolean(installResult["already_installed"])}</strong>
                            <span>gost path</span>
                            <strong>{stringValue(installGost, "path")}</strong>
                            <span>gost version</span>
                            <strong>{stringValue(installGost, "version")}</strong>
                            <span>sha256</span>
                            <strong>{displayBoolean(installGost?.["sha256_verified"])}</strong>
                            <span>系统</span>
                            <strong>
                              {stringValue(installSystem, "name")} /{" "}
                              {stringValue(installSystem, "version_id")}
                            </strong>
                            <span>架构</span>
                            <strong>{stringValue(installSystem, "architecture")}</strong>
                            <span>whoami</span>
                            <strong>{stringValue(installSystem, "whoami")}</strong>
                          </div>
                        </div>
                      ) : null}

                      {installLogs.length > 0 ? (
                        <div className="log-list">
                          {installLogs.map((log) => (
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
                </div>
              ) : null}

              {canInstallSocat ? (
                <div className="transit-read-panel">
                  <h3>安装/检查 socat</h3>
                  <div className="warning-box">
                    <div>Stage 3.3.3-fix-a 只安装或检查 socat。</div>
                    <div>不创建 socat 转发，不监听新端口，不修改防火墙，不写 iptables。</div>
                    <div>不修改落地 VPS，不影响现有 gost route，不生成新的中转链接。</div>
                  </div>

                  <div className="form credential-grid">
                    <label>
                      SSH Key
                      <textarea
                        value={socatPrivateKeyText}
                        onChange={(event) => setSocatPrivateKeyText(event.target.value)}
                        placeholder="粘贴 SSH 私钥，仅临时加密写入 Redis。"
                      />
                    </label>
                    <label>
                      SSH Key 文件
                      <input ref={socatFileInputRef} type="file" />
                    </label>
                    <label>
                      Passphrase
                      <input
                        type="password"
                        value={socatPassphrase}
                        onChange={(event) => setSocatPassphrase(event.target.value)}
                        placeholder="可选"
                      />
                    </label>
                  </div>
                  <div className="transit-actions">
                    <button type="button" onClick={() => void runInstallSocat()}>
                      安装/检查 socat
                    </button>
                  </div>

                  {socatTask ? (
                    <div className="task-card">
                      <div className="detail-grid">
                        <span>任务类型</span>
                        <strong>{socatTask.task_type}</strong>
                        <span>任务状态</span>
                        <strong>{socatTask.status}</strong>
                        <span>当前步骤</span>
                        <strong>{socatTask.current_step ?? "-"}</strong>
                        <span>进度</span>
                        <strong>{socatTask.progress}%</strong>
                        <span>错误码</span>
                        <strong>{socatTask.error_code ?? "-"}</strong>
                        <span>错误信息</span>
                        <strong>{socatTask.error_message ?? "-"}</strong>
                      </div>

                      {socatFailures.length > 0 ? (
                        <div className="failure-box">
                          {socatFailures.map((failure) => (
                            <div key={failure}>{failure}</div>
                          ))}
                        </div>
                      ) : null}
                      {socatWarnings.length > 0 ? (
                        <div className="warning-box">
                          {socatWarnings.map((warning) => (
                            <div key={warning}>{warning}</div>
                          ))}
                        </div>
                      ) : null}

                      {socatResult ? (
                        <div className="transit-read-result">
                          <h4>socat 安装/检查结果</h4>
                          <div className="detail-grid">
                            <span>installed</span>
                            <strong>{displayBoolean(socatResult["installed"])}</strong>
                            <span>already_installed</span>
                            <strong>{displayBoolean(socatResult["already_installed"])}</strong>
                            <span>socat path</span>
                            <strong>{stringValue(installSocat, "path")}</strong>
                            <span>socat version</span>
                            <strong>{stringValue(installSocat, "version")}</strong>
                            <span>系统</span>
                            <strong>
                              {stringValue(socatSystem, "name")} /{" "}
                              {stringValue(socatSystem, "version_id")}
                            </strong>
                            <span>架构</span>
                            <strong>{stringValue(socatSystem, "architecture")}</strong>
                            <span>whoami</span>
                            <strong>{stringValue(socatSystem, "whoami")}</strong>
                          </div>
                        </div>
                      ) : null}

                      {socatLogs.length > 0 ? (
                        <div className="log-list">
                          {socatLogs.map((log) => (
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
                </div>
              ) : null}
            </div>
          )}
        </div>

        <div className="transit-form-card">
          <h3>{editingId ? "编辑中转资源" : "新增中转资源"}</h3>
          <div className="form transit-form">
            <label>
              名称
              <input
                value={form.name}
                onChange={(event) => updateForm("name", event.target.value)}
                placeholder="hk-relay-01 / iepl-line-a"
              />
            </label>
            <label>
              类型
              <select
                value={form.resource_type}
                onChange={(event) => updateForm("resource_type", event.target.value)}
              >
                <option value="server">普通中转服务器</option>
                <option value="iepl">IEPL 线路</option>
                <option value="iplc">IPLC 线路</option>
                <option value="other">其他</option>
              </select>
            </label>
            <label>
              状态
              <select
                value={form.status}
                onChange={(event) => updateForm("status", event.target.value)}
              >
                <option value="active">启用</option>
                <option value="disabled">禁用</option>
              </select>
            </label>
            <label>
              服务商
              <input
                value={form.provider ?? ""}
                onChange={(event) => updateForm("provider", cleanText(event.target.value))}
                placeholder="可选"
              />
            </label>
            <label>
              入口 Host
              <input
                value={form.entry_host ?? ""}
                onChange={(event) => updateForm("entry_host", cleanText(event.target.value))}
                placeholder="域名或 IP，不填凭据"
              />
            </label>
            <label>
              入口端口
              <input
                min={1}
                max={65535}
                type="number"
                value={form.entry_port ?? ""}
                onChange={(event) => updateForm("entry_port", numberOrNull(event.target.value))}
              />
            </label>
            <label>
              入口地区
              <input
                value={form.entry_region ?? ""}
                onChange={(event) => updateForm("entry_region", cleanText(event.target.value))}
                placeholder="Hong Kong"
              />
            </label>
            <label>
              出口地区
              <input
                value={form.exit_region ?? ""}
                onChange={(event) => updateForm("exit_region", cleanText(event.target.value))}
                placeholder="US / Japan / Singapore"
              />
            </label>
            <label>
              带宽 Mbps
              <input
                min={0}
                type="number"
                value={form.bandwidth_mbps ?? ""}
                onChange={(event) =>
                  updateForm("bandwidth_mbps", numberOrNull(event.target.value))
                }
              />
            </label>
            <label>
              流量上限 GB
              <input
                min={0}
                step="0.01"
                type="number"
                value={form.traffic_limit_gb ?? ""}
                onChange={(event) =>
                  updateForm("traffic_limit_gb", numberOrNull(event.target.value))
                }
              />
            </label>
            <label>
              已用流量 GB
              <input
                min={0}
                step="0.01"
                type="number"
                value={form.traffic_used_gb ?? ""}
                onChange={(event) =>
                  updateForm("traffic_used_gb", numberOrNull(event.target.value))
                }
              />
            </label>
            <label>
              协议提示
              <select
                value={form.protocol_hint}
                onChange={(event) => updateForm("protocol_hint", event.target.value)}
              >
                <option value="unknown">未知</option>
                <option value="tcp">TCP</option>
                <option value="udp">UDP</option>
                <option value="tcp_udp">TCP + UDP</option>
              </select>
            </label>
            <label>
              到期时间
              <input
                type="datetime-local"
                value={isoToLocalInput(form.expires_at)}
                onChange={(event) => updateForm("expires_at", localInputToIso(event.target.value))}
              />
            </label>
            <label className="check-row">
              <input
                checked={form.has_ssh}
                onChange={(event) => updateForm("has_ssh", event.target.checked)}
                type="checkbox"
              />
              记录 SSH 元数据
            </label>
            {form.has_ssh && (
              <>
                <label>
                  SSH Host
                  <input
                    value={form.ssh_host ?? ""}
                    onChange={(event) => updateForm("ssh_host", cleanText(event.target.value))}
                    placeholder="只填主机，不填私钥或密码"
                  />
                </label>
                <label>
                  SSH 端口
                  <input
                    min={1}
                    max={65535}
                    type="number"
                    value={form.ssh_port ?? ""}
                    onChange={(event) => updateForm("ssh_port", numberOrNull(event.target.value))}
                  />
                </label>
                <label>
                  SSH 用户名
                  <input
                    value={form.ssh_username ?? ""}
                    onChange={(event) =>
                      updateForm("ssh_username", cleanText(event.target.value))
                    }
                    placeholder="root / ubuntu，仅元数据"
                  />
                </label>
              </>
            )}
            <label className="wide-field">
              备注
              <textarea
                value={form.notes ?? ""}
                onChange={(event) => updateForm("notes", cleanText(event.target.value))}
                placeholder="不要填写密码、私钥、后台账号、专线密钥。"
              />
            </label>
            <div className="transit-actions wide-field">
              <button disabled={loading} onClick={() => void submitForm()} type="button">
                {editingId ? "保存修改" : "新增资源"}
              </button>
              <button className="secondary" onClick={resetForm} type="button">
                清空表单
              </button>
            </div>
            <p className="message wide-field">{message}</p>
          </div>
        </div>
      </div>
    </section>
  );
}
