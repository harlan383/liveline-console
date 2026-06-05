"use client";

import { useEffect, useRef, useState } from "react";
import {
  apiFetch,
  apiFormFetch,
  type CsrfResult,
  type ReadNodeResult,
  type TaskData,
  type TaskLogData,
} from "@/lib/api";

const terminalStatuses = new Set(["success", "failed", "cancelled", "timeout"]);

function resultMessage(task: TaskData | null) {
  const result = task?.result_data;
  if (!result) {
    return null;
  }
  const message = result["message"];
  return typeof message === "string" ? message : null;
}

function resultFailures(task: TaskData | null) {
  const result = task?.result_data;
  const failures = result?.["failures"];
  return Array.isArray(failures) ? failures.filter((item) => typeof item === "string") : [];
}

function resultWarnings(task: TaskData | null) {
  const result = task?.result_data;
  const warnings = result?.["warnings"];
  return Array.isArray(warnings) ? warnings.filter((item) => typeof item === "string") : [];
}

function resultPassed(task: TaskData | null) {
  const passed = task?.result_data?.["passed"];
  return typeof passed === "boolean" ? passed : null;
}

function resultInstalled(task: TaskData | null) {
  const installed = task?.result_data?.["installed"];
  return typeof installed === "boolean" ? installed : null;
}

function resultCreated(task: TaskData | null) {
  const created = task?.result_data?.["created"];
  return typeof created === "boolean" ? created : null;
}

function resultNode(task: TaskData | null) {
  const node = task?.result_data?.["node"];
  return node && typeof node === "object" ? (node as Record<string, unknown>) : null;
}

function canInstallXray(task: TaskData | null) {
  return (
    task?.task_type === "prepare_node" &&
    task.status === "success" &&
    resultPassed(task) === true &&
    task.result_data?.["xray"] instanceof Object &&
    (task.result_data["xray"] as Record<string, unknown>)["installed"] === false
  );
}

function canCreateDirectNode(task: TaskData | null) {
  return (
    task?.task_type === "install_xray" &&
    task.status === "success" &&
    resultInstalled(task) === true
  );
}

type ReadVpsPanelProps = {
  recreateVpsId?: string | null;
  onRecreateVpsConsumed?: () => void;
};

export function ReadVpsPanel({ recreateVpsId, onRecreateVpsConsumed }: ReadVpsPanelProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [vpsIp, setVpsIp] = useState("");
  const [sshPort, setSshPort] = useState("22");
  const [sshUsername, setSshUsername] = useState("root");
  const [privateKeyText, setPrivateKeyText] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [message, setMessage] = useState("读取 VPS、安装前检查和安装 Xray；当前不创建节点。");
  const [task, setTask] = useState<TaskData | null>(null);
  const [logs, setLogs] = useState<TaskLogData[]>([]);
  const [lastVpsId, setLastVpsId] = useState<string | null>(null);
  const [nodeName, setNodeName] = useState("直连 Reality 节点");
  const [listenPort, setListenPort] = useState("443");
  const [realityServerName, setRealityServerName] = useState("www.microsoft.com");
  const [recreateMode, setRecreateMode] = useState(false);

  async function ensureCsrfToken() {
    const csrf = await apiFetch<CsrfResult>("/api/auth/csrf");
    if (!csrf.success) {
      throw new Error(csrf.message);
    }
    return csrf.data.csrf_token;
  }

  async function loadTask(taskId: string) {
    const [taskResult, logsResult] = await Promise.all([
      apiFetch<TaskData>(`/api/tasks/${taskId}`),
      apiFetch<{ logs: TaskLogData[] }>(`/api/tasks/${taskId}/logs`),
    ]);

    if (taskResult.success) {
      setTask(taskResult.data);
      if (taskResult.data.vps_id) {
        setLastVpsId(taskResult.data.vps_id);
      }
      const readMessage = resultMessage(taskResult.data);
      if (readMessage) {
        setMessage(readMessage);
      } else if (taskResult.data.error_message) {
        setMessage(taskResult.data.error_message);
      }
      if (
        recreateMode &&
        taskResult.data.task_type === "create_direct_node" &&
        taskResult.data.status === "success" &&
        resultCreated(taskResult.data) === true
      ) {
        setRecreateMode(false);
        onRecreateVpsConsumed?.();
      }
    } else {
      setMessage(taskResult.message);
    }

    if (logsResult.success) {
      setLogs(logsResult.data.logs);
    }
  }

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
    if (!recreateVpsId) {
      return;
    }
    setLastVpsId(recreateVpsId);
    setRecreateMode(true);
    setNodeName("重新创建 Reality 节点");
    setMessage("VPS 已处于待重新配置状态，可以重新创建直连节点。");
  }, [recreateVpsId]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("正在创建读取任务。");

    try {
      const csrfToken = await ensureCsrfToken();
      const formData = new FormData();
      formData.append("vps_ip", vpsIp);
      formData.append("ssh_port", sshPort);
      formData.append("ssh_username", sshUsername);
      formData.append("ssh_key_passphrase", passphrase);
      if (privateKeyText.trim()) {
        formData.append("private_key_text", privateKeyText);
      }
      const file = fileInputRef.current?.files?.[0];
      if (file) {
        formData.append("private_key_file", file);
      }

      const result = await apiFormFetch<ReadNodeResult>("/api/nodes/read", formData, {
        headers: { "X-CSRF-Token": csrfToken },
      });

      setPrivateKeyText("");
      setPassphrase("");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }

      setMessage("读取任务已创建。");
      setLastVpsId(result.data.vps_id);
      await loadTask(result.data.task_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取任务创建失败。");
    }
  }

  async function prepare() {
    if (!lastVpsId) {
      setMessage("请先完成 VPS 读取。");
      return;
    }

    try {
      setMessage("正在创建安装前检查任务。");
      const csrfToken = await ensureCsrfToken();
      const formData = new FormData();
      formData.append("vps_id", lastVpsId);
      formData.append("ssh_key_passphrase", passphrase);
      if (privateKeyText.trim()) {
        formData.append("private_key_text", privateKeyText);
      }
      const file = fileInputRef.current?.files?.[0];
      if (file) {
        formData.append("private_key_file", file);
      }

      const result = await apiFormFetch<ReadNodeResult>("/api/nodes/prepare", formData, {
        headers: { "X-CSRF-Token": csrfToken },
      });

      setPrivateKeyText("");
      setPassphrase("");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }

      setMessage("安装前检查任务已创建。");
      await loadTask(result.data.task_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "安装前检查任务创建失败。");
    }
  }

  async function installXray() {
    if (!lastVpsId) {
      setMessage("请先完成安装前检查。");
      return;
    }

    try {
      setMessage("正在创建 Xray 安装任务。");
      const csrfToken = await ensureCsrfToken();
      const formData = new FormData();
      formData.append("vps_id", lastVpsId);
      formData.append("ssh_key_passphrase", passphrase);
      if (privateKeyText.trim()) {
        formData.append("private_key_text", privateKeyText);
      }
      const file = fileInputRef.current?.files?.[0];
      if (file) {
        formData.append("private_key_file", file);
      }

      const result = await apiFormFetch<ReadNodeResult>("/api/nodes/install-xray", formData, {
        headers: { "X-CSRF-Token": csrfToken },
      });

      setPrivateKeyText("");
      setPassphrase("");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }

      setMessage("Xray 安装任务已创建。");
      await loadTask(result.data.task_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Xray 安装任务创建失败。");
    }
  }

  async function createDirectNode() {
    if (!lastVpsId) {
      setMessage("请先完成 Xray 安装或选择待重新创建的 VPS。");
      return;
    }

    try {
      setMessage(recreateMode ? "正在创建重新创建任务。" : "正在创建直连节点任务。");
      const csrfToken = await ensureCsrfToken();
      const formData = new FormData();
      formData.append("vps_id", lastVpsId);
      formData.append("node_name", nodeName);
      formData.append("listen_port", listenPort);
      formData.append("reality_server_name", realityServerName);
      formData.append("reality_dest", `${realityServerName}:443`);
      formData.append("ssh_key_passphrase", passphrase);
      if (privateKeyText.trim()) {
        formData.append("private_key_text", privateKeyText);
      }
      const file = fileInputRef.current?.files?.[0];
      if (file) {
        formData.append("private_key_file", file);
      }

      const result = await apiFormFetch<ReadNodeResult>("/api/nodes/create-direct", formData, {
        headers: { "X-CSRF-Token": csrfToken },
      });

      setPrivateKeyText("");
      setPassphrase("");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      if (!result.success) {
        setMessage(`${result.error_code}: ${result.message}`);
        return;
      }

      setMessage(recreateMode ? "重新创建直连节点任务已创建。" : "直连节点创建任务已创建。");
      await loadTask(result.data.task_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "直连节点创建任务创建失败。");
    }
  }

  async function copyShareLink() {
    const shareLink = resultNode(task)?.["share_link"];
    if (typeof shareLink !== "string") {
      setMessage("没有可复制的分享链接。");
      return;
    }
    await navigator.clipboard.writeText(shareLink);
    setMessage("分享链接已复制。");
  }

  return (
    <section className="panel wide">
      <h2>读取 VPS</h2>
      <form className="form read-form" onSubmit={(event) => void submit(event)}>
        <label>
          VPS IP
          <input value={vpsIp} onChange={(event) => setVpsIp(event.target.value)} />
        </label>
        <label>
          SSH 端口
          <input
            inputMode="numeric"
            value={sshPort}
            onChange={(event) => setSshPort(event.target.value)}
          />
        </label>
        <label>
          SSH 用户名
          <input value={sshUsername} onChange={(event) => setSshUsername(event.target.value)} />
        </label>
        <label>
          上传 SSH 私钥
          <input ref={fileInputRef} type="file" />
        </label>
        <label className="wide-field">
          粘贴 SSH 私钥
          <textarea
            value={privateKeyText}
            onChange={(event) => setPrivateKeyText(event.target.value)}
          />
        </label>
        <label>
          SSH Key Passphrase
          <input
            type="password"
            value={passphrase}
            onChange={(event) => setPassphrase(event.target.value)}
          />
        </label>
        <button type="submit">读取</button>
        {lastVpsId && task?.status === "success" && task.task_type !== "install_xray" ? (
          <button className="secondary" type="button" onClick={() => void prepare()}>
            安装前检查
          </button>
        ) : null}
        {canInstallXray(task) ? (
          <button type="button" onClick={() => void installXray()}>
            安装 Xray
          </button>
        ) : null}
        {canCreateDirectNode(task) || recreateMode ? (
          <div className="direct-node-fields wide-field">
            {recreateMode ? (
              <div className="warning-box wide-field">
                <div>将生成新的 vless:// 链接，旧链接不会恢复。</div>
                <div>新链接需要重新导入客户端，操作会启动 Xray 并占用端口 443。</div>
              </div>
            ) : null}
            <label>
              节点名称
              <input value={nodeName} onChange={(event) => setNodeName(event.target.value)} />
            </label>
            <label>
              端口
              <input
                inputMode="numeric"
                value={listenPort}
                onChange={(event) => setListenPort(event.target.value)}
              />
            </label>
            <label>
              Reality 伪装域名
              <input
                value={realityServerName}
                onChange={(event) => setRealityServerName(event.target.value)}
              />
            </label>
            <button type="button" onClick={() => void createDirectNode()}>
              {recreateMode ? "重新创建直连节点" : "创建直连节点"}
            </button>
          </div>
        ) : null}
        <p className="message wide-field">{message}</p>
      </form>

      {task ? (
        <div className="task-card">
          <div className="status-row">
            <div>
              <strong>任务状态</strong>
              <p className="message">
                {task.status} / {task.current_step ?? "-"} / {task.progress}%
              </p>
            </div>
            <span className={`pill ${task.status === "success" ? "ok" : "bad"}`}>
              {task.error_code ?? task.status}
            </span>
          </div>

          {task.result_data ? (
            <>
              {resultPassed(task) === true ? (
                <p className="message">可以进入安装 Xray。</p>
              ) : null}
              {resultInstalled(task) === true ? (
                <p className="message">Xray 已安装，等待创建节点配置。</p>
              ) : null}
              {resultCreated(task) === true && resultNode(task) ? (
                <div className="node-result">
                  <strong>{String(resultNode(task)?.["name"] ?? nodeName)}</strong>
                  <span>协议：{String(resultNode(task)?.["protocol"] ?? "vless")}</span>
                  <span>端口：{String(resultNode(task)?.["port"] ?? "-")}</span>
                  <span>
                    Reality serverName：
                    {String(resultNode(task)?.["reality_server_name"] ?? "-")}
                  </span>
                  <button className="secondary" type="button" onClick={() => void copyShareLink()}>
                    复制分享链接
                  </button>
                </div>
              ) : null}
              {resultWarnings(task).length > 0 ? (
                <div className="warning-box">
                  {resultWarnings(task).map((warning) => (
                    <div key={warning}>{warning}</div>
                  ))}
                </div>
              ) : null}
              {resultPassed(task) === false ? (
                <div className="failure-box">
                  {resultFailures(task).map((failure) => (
                    <div key={failure}>{failure}</div>
                  ))}
                </div>
              ) : null}
              {resultInstalled(task) === false && resultFailures(task).length > 0 ? (
                <div className="failure-box">
                  {resultFailures(task).map((failure) => (
                    <div key={failure}>{failure}</div>
                  ))}
                </div>
              ) : null}
              <pre className="result-box">{JSON.stringify(task.result_data, null, 2)}</pre>
            </>
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
