"use client";

import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";

import { ProductIcon } from "@/components/ProductIcons";
import {
  apiFetch,
  createLandingNodeExecution,
  createLandingNodePlan,
  createTransitWorkerBootstrap,
  createVpsWorkerBootstrap,
  type CsrfResult,
  type LandingNodeCreateResponse,
  type LandingNodePlanResponse,
  type NodeData,
  type TransitResourceData,
  type TransitWorkerBootstrapResult,
  type VpsServerData,
  type VpsWorkerBootstrapResult,
} from "@/lib/api";

type ModalProps = {
  onClose: () => void;
  onCompleted?: () => void | Promise<void>;
};

type StepDefinition = {
  label: string;
  detail: string;
};

const serverSteps: StepDefinition[] = [
  { label: "填写信息", detail: "录入服务器基础信息" },
  { label: "安装助手", detail: "生成安装助手命令" },
  { label: "等待上线", detail: "等待服务器助手心跳" },
  { label: "完成", detail: "完成接入确认" },
];

const transitLineSteps: StepDefinition[] = [
  { label: "选择中转服务器", detail: "选择客户连接入口" },
  { label: "选择落地节点", detail: "选择最终出口节点" },
  { label: "设置客户连接端口", detail: "填写客户使用的端口" },
  { label: "端口放行", detail: "人工确认防火墙放行" },
  { label: "创建完成", detail: "完成本页展示" },
];

const directNodeSteps: StepDefinition[] = [
  { label: "选择服务器", detail: "选择在线落地 Worker" },
  { label: "填写节点参数", detail: "填写端口和 Reality 参数" },
  { label: "创建计划", detail: "生成受保护计划" },
  { label: "安全确认", detail: "确认端口和风险" },
  { label: "创建命令", detail: "创建 Worker command" },
  { label: "等待执行", detail: "等待 Worker 轮询执行" },
];

function ModalShell({
  children,
  onClose,
  title,
  wide = false,
}: {
  children: ReactNode;
  onClose: () => void;
  title: string;
  wide?: boolean;
}) {
  return (
    <div className="modal-backdrop" role="presentation">
      <div className={wide ? "modal-card product-modal product-modal-wide" : "modal-card product-modal"}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button aria-label="关闭" className="modal-close-button" type="button" onClick={onClose}>
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function ProductSteps({ activeStep, steps }: { activeStep: number; steps: StepDefinition[] }) {
  return (
    <div className="product-stepper" aria-label="流程步骤">
      {steps.map((step, index) => (
        <div className={index <= activeStep ? "product-step active" : "product-step"} key={step.label}>
          <span>{index + 1}</span>
          <strong>{step.label}</strong>
          <small>{step.detail}</small>
        </div>
      ))}
    </div>
  );
}

function InfoCard({ children, title }: { children: ReactNode; title: string }) {
  return (
    <aside className="product-side-note">
      <strong>{title}</strong>
      <ul>{children}</ul>
    </aside>
  );
}

const bootstrapExpiryOptions = [30, 60, 120, 1440];

function formatExpiresAt(value: string | null | undefined) {
  if (!value) {
    return "未返回";
  }
  return new Date(value).toLocaleString();
}

async function copyText(value: string) {
  if (!navigator.clipboard) {
    return false;
  }
  await navigator.clipboard.writeText(value);
  return true;
}

async function fetchCsrfToken() {
  const csrfResult = await apiFetch<CsrfResult>("/api/auth/csrf");
  return csrfResult.success ? csrfResult.data.csrf_token : null;
}

function BootstrapCommandPanel({
  command,
  expiresAt,
  host,
  message,
  name,
  onCopy,
  roleLabel,
}: {
  command: string;
  expiresAt: string;
  host: string;
  message: string;
  name: string;
  onCopy: () => void;
  roleLabel: string;
}) {
  return (
    <section className="product-bootstrap-result">
      <div className="product-bootstrap-meta">
        <span>
          <small>{roleLabel}</small>
          <strong>{name}</strong>
        </span>
        <span>
          <small>公网 IP</small>
          <strong>{host}</strong>
        </span>
        <span>
          <small>命令有效期</small>
          <strong>{formatExpiresAt(expiresAt)}</strong>
        </span>
      </div>
      <label className="product-form-wide product-command-field">
        安装命令
        <textarea readOnly value={command} />
      </label>
      <div className="product-command-actions">
        <button type="button" onClick={onCopy}>
          复制安装命令
        </button>
        <small>{message}</small>
      </div>
      <p className="demo-safety-note compact">
        命令包含一次性 token，只在当前弹窗临时展示；请勿写入文档、PR、聊天记录、日志或浏览器存储。
      </p>
    </section>
  );
}

export function AddLandingServerModal({ onClose, onCompleted }: ModalProps) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [ip, setIp] = useState("");
  const [interfaceName, setInterfaceName] = useState("ens17");
  const [expiresInMinutes, setExpiresInMinutes] = useState(60);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("填写信息后生成一次性 Worker 安装命令。");
  const [bootstrapResult, setBootstrapResult] = useState<VpsWorkerBootstrapResult | null>(null);
  const [copied, setCopied] = useState(false);

  function resetForm() {
    setStep(0);
    setBootstrapResult(null);
    setCopied(false);
    setMessage("填写信息后生成一次性 Worker 安装命令。");
  }

  function closeModal() {
    setBootstrapResult(null);
    setCopied(false);
    onClose();
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextName = name.trim();
    const nextIp = ip.trim();
    const nextInterfaceName = interfaceName.trim();
    if (!nextName || !nextIp || !nextInterfaceName) {
      setMessage("请填写服务器名称、公网 IP 和网卡名。");
      return;
    }

    setSubmitting(true);
    setCopied(false);
    setMessage("正在生成落地服务器安装命令。");
    try {
      const csrfToken = await fetchCsrfToken();
      if (!csrfToken) {
        setMessage("登录状态或安全校验失败，请刷新后重试。");
        return;
      }
      const result = await createVpsWorkerBootstrap(
        {
          name: nextName,
          ip: nextIp,
          interface_name: nextInterfaceName,
          expires_in_minutes: expiresInMinutes,
        },
        csrfToken,
      );
      if (!result.success) {
        setMessage(result.message || "生成安装命令失败。");
        return;
      }
      setBootstrapResult(result.data);
      setStep(1);
      setMessage("安装命令已生成，请复制到对应落地 VPS 手动执行。");
      await onCompleted?.();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "生成安装命令失败。");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCopyCommand() {
    if (!bootstrapResult?.install_command) {
      setMessage("请先生成安装命令。");
      return;
    }
    try {
      const copiedToClipboard = await copyText(bootstrapResult.install_command);
      setCopied(copiedToClipboard);
      setStep(2);
      setMessage(
        copiedToClipboard
          ? "安装命令已复制，请立即在对应落地 VPS 手动执行。"
          : "浏览器未允许自动复制，请手动选择命令复制。",
      );
    } catch {
      setCopied(false);
      setMessage("复制失败，请手动选择命令复制。");
    }
  }

  return (
    <ModalShell onClose={closeModal} title="添加落地服务器" wide>
      <ProductSteps activeStep={step} steps={serverSteps} />
      <div className="product-modal-layout">
        <form className="product-form" onSubmit={handleSubmit}>
          <p className="required-hint">带 <span>*</span> 的为必填项。</p>
          <label>
            <span>服务器名称 <em>*</em></span>
            <input disabled={!!bootstrapResult || submitting} placeholder="例如：香港落地15m" value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            <span>服务器公网 IP <em>*</em></span>
            <input disabled={!!bootstrapResult || submitting} placeholder="例如：64.90.13.19" value={ip} onChange={(event) => setIp(event.target.value)} />
          </label>
          <label>
            <span>网卡名 <em>*</em></span>
            <small>常见为 ens17 / eth0，请以 VPS 实际网卡为准。</small>
            <input disabled={!!bootstrapResult || submitting} placeholder="例如：ens17、eth0、enp1s0" value={interfaceName} onChange={(event) => setInterfaceName(event.target.value)} />
          </label>
          <label>
            <span>命令有效期 <em>*</em></span>
            <select disabled={!!bootstrapResult || submitting} value={expiresInMinutes} onChange={(event) => setExpiresInMinutes(Number(event.target.value))}>
              {bootstrapExpiryOptions.map((minutes) => (
                <option key={minutes} value={minutes}>{minutes} 分钟</option>
              ))}
            </select>
          </label>
          {!bootstrapResult ? (
            <button className="product-form-submit" disabled={submitting} type="submit">
              {submitting ? "生成中..." : "生成安装命令"}
            </button>
          ) : null}
          {bootstrapResult ? (
            <BootstrapCommandPanel
              command={bootstrapResult.install_command}
              expiresAt={bootstrapResult.expires_at}
              host={bootstrapResult.server.ip}
              message={copied ? "已复制。请勿把命令写入文档、日志或 Git。" : message}
              name={bootstrapResult.server.name}
              roleLabel="落地服务器"
              onCopy={handleCopyCommand}
            />
          ) : null}
        </form>
        <InfoCard title="这一步要做什么？">
          <li>本阶段只生成安装命令，不会自动 SSH。</li>
          <li>请复制命令到对应落地 VPS 手动执行。</li>
          <li>命令包含一次性 token，请勿发到文档、PR、聊天记录或日志。</li>
          <li>安装 Worker 不会创建节点，不会开放客户端口。</li>
        </InfoCard>
      </div>
      <p className="demo-safety-note">{message}</p>
      <div className="modal-actions">
        <button className="secondary" type="button" onClick={closeModal}>
          关闭
        </button>
        {bootstrapResult ? (
          <button className="secondary" type="button" onClick={resetForm}>
            重新填写
          </button>
        ) : null}
      </div>
    </ModalShell>
  );
}

export function AddTransitServerModal({ onClose, onCompleted }: ModalProps) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [ip, setIp] = useState("");
  const [interfaceName, setInterfaceName] = useState("ens17");
  const [expiresInMinutes, setExpiresInMinutes] = useState(60);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("填写信息后生成一次性中转 Worker 安装命令。");
  const [bootstrapResult, setBootstrapResult] = useState<TransitWorkerBootstrapResult | null>(null);
  const [copied, setCopied] = useState(false);

  function resetForm() {
    setStep(0);
    setBootstrapResult(null);
    setCopied(false);
    setMessage("填写信息后生成一次性中转 Worker 安装命令。");
  }

  function closeModal() {
    setBootstrapResult(null);
    setCopied(false);
    onClose();
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextName = name.trim();
    const nextIp = ip.trim();
    const nextInterfaceName = interfaceName.trim();
    if (!nextName || !nextIp || !nextInterfaceName) {
      setMessage("请填写中转服务器名称、公网 IP 和网卡名。");
      return;
    }

    setSubmitting(true);
    setCopied(false);
    setMessage("正在生成中转服务器安装命令。");
    try {
      const csrfToken = await fetchCsrfToken();
      if (!csrfToken) {
        setMessage("登录状态或安全校验失败，请刷新后重试。");
        return;
      }
      const result = await createTransitWorkerBootstrap(
        {
          name: nextName,
          ip: nextIp,
          interface_name: nextInterfaceName,
          expires_in_minutes: expiresInMinutes,
        },
        csrfToken,
      );
      if (!result.success) {
        setMessage(result.message || "生成安装命令失败。");
        return;
      }
      setBootstrapResult(result.data);
      setStep(1);
      setMessage("安装命令已生成，请复制到对应中转 VPS 手动执行。");
      await onCompleted?.();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "生成安装命令失败。");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCopyCommand() {
    if (!bootstrapResult?.install_command) {
      setMessage("请先生成安装命令。");
      return;
    }
    try {
      const copiedToClipboard = await copyText(bootstrapResult.install_command);
      setCopied(copiedToClipboard);
      setStep(2);
      setMessage(
        copiedToClipboard
          ? "安装命令已复制，请立即在对应中转 VPS 手动执行。"
          : "浏览器未允许自动复制，请手动选择命令复制。",
      );
    } catch {
      setCopied(false);
      setMessage("复制失败，请手动选择命令复制。");
    }
  }

  return (
    <ModalShell onClose={closeModal} title="添加中转服务器" wide>
      <ProductSteps activeStep={step} steps={serverSteps} />
      <div className="product-modal-layout">
        <form className="product-form" onSubmit={handleSubmit}>
          <p className="required-hint">带 <span>*</span> 的为必填项。</p>
          <div className="form-group-title">基础信息</div>
          <label>
            <span>中转服务器名称 <em>*</em></span>
            <input disabled={!!bootstrapResult || submitting} placeholder="例如：mk香港中转 / 香港中转01" value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            <span>中转 VPS 公网 IP <em>*</em></span>
            <input disabled={!!bootstrapResult || submitting} placeholder="例如：109.244.79.147" value={ip} onChange={(event) => setIp(event.target.value)} />
          </label>
          <label>
            <span>网卡名 <em>*</em></span>
            <small>常见为 ens17 / eth0，请以 VPS 实际网卡为准。</small>
            <input disabled={!!bootstrapResult || submitting} placeholder="例如：ens17、eth0、enp1s0" value={interfaceName} onChange={(event) => setInterfaceName(event.target.value)} />
          </label>
          <label>
            <span>命令有效期 <em>*</em></span>
            <select disabled={!!bootstrapResult || submitting} value={expiresInMinutes} onChange={(event) => setExpiresInMinutes(Number(event.target.value))}>
              {bootstrapExpiryOptions.map((minutes) => (
                <option key={minutes} value={minutes}>{minutes} 分钟</option>
              ))}
            </select>
          </label>
          {!bootstrapResult ? (
            <button className="product-form-submit" disabled={submitting} type="submit">
              {submitting ? "生成中..." : "生成安装命令"}
            </button>
          ) : null}
          {bootstrapResult ? (
            <BootstrapCommandPanel
              command={bootstrapResult.install_command}
              expiresAt={bootstrapResult.expires_at}
              host={bootstrapResult.resource.entry_host ?? ip}
              message={copied ? "已复制。请勿把命令写入文档、日志或 Git。" : message}
              name={bootstrapResult.resource.name}
              roleLabel="中转服务器"
              onCopy={handleCopyCommand}
            />
          ) : null}
        </form>
        <InfoCard title="这一步要做什么？">
          <li>本阶段只接入中转服务器助手。</li>
          <li>不会创建 HAProxy 转发规则。</li>
          <li>不会新增客户连接端口。</li>
          <li>不会修改防火墙 / 云安全组 / 云防火墙。</li>
          <li>后续中转线路创建将在 Stage 3.4.18 接入。</li>
        </InfoCard>
      </div>
      <p className="demo-safety-note">{message}</p>
      <div className="modal-actions">
        <button className="secondary" type="button" onClick={closeModal}>
          关闭
        </button>
        {bootstrapResult ? (
          <button className="secondary" type="button" onClick={resetForm}>
            重新填写
          </button>
        ) : null}
      </div>
    </ModalShell>
  );
}

function endpoint(host: string | null | undefined, port: number | null | undefined) {
  if (!host) {
    return "未返回";
  }
  return port ? `${host}:${port}` : host;
}

export function CreateTransitLineModal({
  nodes,
  onClose,
  resources,
}: ModalProps & {
  nodes: NodeData[];
  resources: TransitResourceData[];
}) {
  const [step, setStep] = useState(0);
  const [lineMode, setLineMode] = useState<"self" | "provider">("self");
  const [selectedResourceId, setSelectedResourceId] = useState(resources[0]?.id ?? "");
  const [selectedNodeId, setSelectedNodeId] = useState(nodes[0]?.id ?? "");
  const [port, setPort] = useState("29833");
  const [checks, setChecks] = useState({
    cloudSecurityGroup: false,
    cloudFirewall: false,
    serverFirewall: false,
  });
  const selectedResource = resources.find((resource) => resource.id === selectedResourceId) ?? resources[0] ?? null;
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? nodes[0] ?? null;

  return (
    <ModalShell onClose={onClose} title="新建中转线路" wide>
      <div className="product-segmented">
        <button className={lineMode === "self" ? "selected" : ""} type="button" onClick={() => setLineMode("self")}>
          自建中转
        </button>
        <button className={lineMode === "provider" ? "selected" : ""} type="button" onClick={() => setLineMode("provider")}>
          商家中转
        </button>
      </div>
      <ProductSteps activeStep={step} steps={transitLineSteps} />
      {lineMode === "provider" ? (
        <div className="product-modal-layout">
          <div className="product-empty-state">
            <ProductIcon name="route" tone="purple" />
            <strong>商家中转入口将在后续阶段接入</strong>
            <p>本阶段先保留入口位置，后续会支持填写商家入口、绑定落地节点和设置客户用途。</p>
          </div>
          <InfoCard title="商家中转是什么？">
            <li>由线路商提供客户入口。</li>
            <li>你只需要绑定落地节点和客户用途。</li>
            <li>当前不会保存数据，也不会创建正式线路。</li>
          </InfoCard>
        </div>
      ) : (
      <div className="transit-line-wizard">
        <section className="transit-line-main">
          <div className="wizard-card-list">
            <h4>选择中转服务器</h4>
            {resources.length ? (
              resources.map((resource) => (
                <button
                  className={selectedResourceId === resource.id ? "wizard-select-card selected" : "wizard-select-card"}
                  key={resource.id}
                  type="button"
                  onClick={() => setSelectedResourceId(resource.id)}
                >
                  <ProductIcon name="servers" tone="orange" />
                  <strong>{resource.name}</strong>
                  <span>{endpoint(resource.entry_host, resource.entry_port)}</span>
                  <small>{resource.entry_region ?? "入口地区未填写"} → {resource.exit_region ?? "出口地区未填写"}</small>
                  <i aria-hidden="true" />
                </button>
              ))
            ) : (
              <div className="empty">暂无可选中转服务器。</div>
            )}
          </div>

          <div className="wizard-card-list">
            <h4>选择落地节点</h4>
            {nodes.length ? (
              nodes.map((node) => (
                <button
                  className={selectedNodeId === node.id ? "wizard-select-card selected" : "wizard-select-card"}
                  key={node.id}
                  type="button"
                  onClick={() => setSelectedNodeId(node.id)}
                >
                  <ProductIcon name="builder" tone="green" />
                  <strong>{node.node_name}</strong>
                  <span>{endpoint(node.vps_ip, node.port)}</span>
                  <small>{node.reality_server_name ?? "域名信息未返回"}</small>
                  <i aria-hidden="true" />
                </button>
              ))
            ) : (
              <div className="empty">暂无可选落地节点。</div>
            )}
          </div>

          <label className="product-port-field">
            客户连接端口
            <input value={port} onChange={(event) => setPort(event.target.value)} />
          </label>
        </section>

        <aside className="transit-line-preview">
          <strong>线路预览</strong>
          <div className="preview-chain">
            <span><ProductIcon name="dashboard" tone="slate" /><small>客户入口</small>客户 / OBS</span>
            <span><ProductIcon name="servers" tone="orange" /><small>中转服务器</small>{endpoint(selectedResource?.entry_host, Number(port) || null)}</span>
            <span><ProductIcon name="builder" tone="green" /><small>落地节点</small>{selectedNode?.node_name ?? "请选择落地节点"} / {endpoint(selectedNode?.vps_ip, selectedNode?.port)}</span>
            <span><ProductIcon name="route" tone="purple" /><small>目标平台</small>Facebook / TikTok</span>
          </div>
          <strong>请确认端口已放行 <em>*</em></strong>
          <div className="port-confirm-list">
            <label>
              <input
                checked={checks.cloudSecurityGroup}
                type="checkbox"
                onChange={(event) => setChecks((current) => ({ ...current, cloudSecurityGroup: event.target.checked }))}
              />
              <span><strong>云安全组已放行</strong><small>云厂商控制台里的端口已开放。</small></span>
            </label>
            <label>
              <input
                checked={checks.cloudFirewall}
                type="checkbox"
                onChange={(event) => setChecks((current) => ({ ...current, cloudFirewall: event.target.checked }))}
              />
              <span><strong>云防火墙已放行</strong><small>云平台防火墙已允许。</small></span>
            </label>
            <label>
              <input
                checked={checks.serverFirewall}
                type="checkbox"
                onChange={(event) => setChecks((current) => ({ ...current, serverFirewall: event.target.checked }))}
              />
              <span><strong>服务器防火墙已放行</strong><small>服务器系统内部已允许。</small></span>
            </label>
          </div>
          <p>新增或变更客户连接端口后，请务必同步检查云服务器安全组、云防火墙、服务器防火墙是否放行。</p>
        </aside>
      </div>
      )}
      <p className="demo-safety-note">
        {lineMode === "provider" ? "商家中转当前仅展示入口位置，不会保存数据或创建正式线路。" : "当前仅展示流程，不会触发真实创建或 Worker 任务。"}
      </p>
      <div className="modal-actions">
        <button className="secondary" type="button" onClick={() => setStep((current) => Math.max(current - 1, 0))}>
          上一步
        </button>
        <button className="secondary" type="button" onClick={() => setStep((current) => Math.min(current + 1, transitLineSteps.length - 1))}>
          下一步
        </button>
        <button disabled={lineMode === "provider" || step < transitLineSteps.length - 2} type="button" onClick={() => setStep(transitLineSteps.length - 1)}>
          {lineMode === "provider" ? "后续接入" : "完成演示流程"}
        </button>
      </div>
    </ModalShell>
  );
}

const DIRECT_NODE_CONFIRM_TEXT = "CONFIRM_CREATE_DIRECT_NODE";
const RESERVED_DIRECT_NODE_PORTS = new Set([22, 80, 443, 5432, 6379, 8000, 8200, 3000, 3200, 15432, 16379]);

type DirectNodeConfirmationKey =
  | "cloudSecurityGroup"
  | "cloudFirewall"
  | "serverFirewall"
  | "realListener"
  | "noCloudFirewallChange"
  | "noCutover"
  | "rollbackOnly";

const directNodeConfirmationItems: Array<{ key: DirectNodeConfirmationKey; label: string; detail: string }> = [
  {
    key: "cloudSecurityGroup",
    label: "我已在云服务器安全组放行该 TCP 端口",
    detail: "云厂商安全组需允许客户连接端口入站。",
  },
  {
    key: "cloudFirewall",
    label: "我已在云防火墙放行该 TCP 端口",
    detail: "如云平台有额外防火墙，也需要同步放行。",
  },
  {
    key: "serverFirewall",
    label: "我已确认服务器系统防火墙允许该 TCP 端口",
    detail: "系统不会替你修改云安全组或云防火墙。",
  },
  {
    key: "realListener",
    label: "我理解本操作会新增真实客户端监听端口",
    detail: "Worker 执行成功后会在落地 VPS 上创建 VLESS Reality 入口。",
  },
  {
    key: "noCloudFirewallChange",
    label: "我理解系统不会自动修改云安全组 / 云防火墙",
    detail: "云侧放行必须由管理员提前确认。",
  },
  {
    key: "noCutover",
    label: "我确认本次不会 cutover，不会影响现有节点链接",
    detail: "本次只创建新的直连节点命令，不切换正式线路。",
  },
  {
    key: "rollbackOnly",
    label: "我确认失败时只回滚本次新增内容",
    detail: "不会清理历史节点或既有配置。",
  },
];

const initialDirectNodeConfirmations: Record<DirectNodeConfirmationKey, boolean> = {
  cloudSecurityGroup: false,
  cloudFirewall: false,
  serverFirewall: false,
  realListener: false,
  noCloudFirewallChange: false,
  noCutover: false,
  rollbackOnly: false,
};

function validateDirectNodePort(value: string) {
  const parsed = Number(value);
  if (!/^\d+$/.test(value.trim())) {
    return "端口必须是数字。";
  }
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535) {
    return "端口必须在 1-65535 之间。";
  }
  if (RESERVED_DIRECT_NODE_PORTS.has(parsed)) {
    return "该端口属于系统 / 控制台常用端口，请换用 10000-30000 范围内的端口。";
  }
  return null;
}

function allDirectNodeConfirmationsChecked(confirmations: Record<DirectNodeConfirmationKey, boolean>) {
  return directNodeConfirmationItems.every((item) => confirmations[item.key]);
}

function safePlanValue(value: unknown) {
  if (typeof value === "string") {
    return value || "未返回";
  }
  if (typeof value === "number") {
    return String(value);
  }
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (value === null || value === undefined) {
    return "未返回";
  }
  if (Array.isArray(value)) {
    return `${value.length} 项`;
  }
  return "已返回";
}

function DirectNodePlanSummary({ plan }: { plan: LandingNodePlanResponse }) {
  const preflightEntries = Object.entries(plan.preflight_summary ?? {}).slice(0, 8);
  return (
    <section className="direct-node-result-card">
      <div className="product-section-head">
        <h4>创建计划</h4>
        <span className={plan.ready && plan.blocked_reasons.length === 0 ? "product-badge success" : "product-badge warning"}>
          {plan.ready && plan.blocked_reasons.length === 0 ? "ready" : "需要处理"}
        </span>
      </div>
      <div className="direct-node-plan-grid">
        <span>监听端口</span>
        <strong>{plan.listen_port}</strong>
        <span>Reality SNI</span>
        <strong>{plan.server_name}</strong>
        <span>Reality dest</span>
        <strong>{plan.dest}</strong>
        <span>fingerprint</span>
        <strong>{plan.fingerprint}</strong>
        <span>安装 / 更新 Xray</span>
        <strong>{plan.will_install_xray ? "可能需要" : "不需要"}</strong>
        <span>创建配置</span>
        <strong>{plan.will_create_config ? "是" : "否"}</strong>
        <span>本机防火墙</span>
        <strong>{plan.will_open_local_firewall ? "可能调整" : "不调整"}</strong>
        <span>云安全组</span>
        <strong>{plan.will_modify_cloud_security_group ? "会修改" : "不会修改"}</strong>
      </div>
      <PlanTextList title="warnings" items={plan.warnings} emptyText="无警告。" />
      <PlanTextList title="blocked_reasons" items={plan.blocked_reasons} emptyText="无阻断。" />
      <PlanTextList title="required_user_confirmations" items={plan.required_user_confirmations} emptyText="无额外确认。" />
      <PlanTextList title="safety_boundary" items={plan.safety_boundary} emptyText="未返回。" />
      {preflightEntries.length ? (
        <div className="direct-node-preflight">
          <strong>preflight_summary</strong>
          {preflightEntries.map(([key, value]) => (
            <span key={key}>
              <small>{key}</small>
              <em>{safePlanValue(value)}</em>
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function DirectNodeCreateSummary({ result }: { result: LandingNodeCreateResponse }) {
  return (
    <section className="direct-node-result-card success">
      <div className="product-section-head">
        <h4>正式创建命令已创建</h4>
        <span className="product-badge success">{result.status}</span>
      </div>
      <div className="direct-node-plan-grid">
        <span>command_id</span>
        <strong>{result.command_id}</strong>
        <span>approved_port</span>
        <strong>{result.approved_port}</strong>
        <span>target_worker_id</span>
        <strong>{result.target_worker_id}</strong>
        <span>target_worker_version</span>
        <strong>{result.target_worker_version ?? "未返回"}</strong>
        <span>next_action</span>
        <strong>{result.next_action}</strong>
      </div>
      <PlanTextList title="safety_boundary" items={result.safety_boundary} emptyText="未返回。" />
      <p className="demo-safety-note compact">
        正式创建命令已创建，等待落地 Worker 轮询执行。创建成功后可在任务记录 / 客户端信息导出流程中查看结果。
      </p>
    </section>
  );
}

function PlanTextList({ emptyText, items, title }: { emptyText: string; items: string[]; title: string }) {
  return (
    <div className="direct-node-text-list">
      <strong>{title}</strong>
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <span>{emptyText}</span>
      )}
    </div>
  );
}

export function CreateDirectNodeModal({
  onClose,
  onCompleted,
  servers,
}: ModalProps & {
  servers: VpsServerData[];
}) {
  const onlineServers = useMemo(
    () => servers.filter((server) => server.worker_online && server.status !== "deleted"),
    [servers],
  );
  const [step, setStep] = useState(0);
  const [selectedServerId, setSelectedServerId] = useState(onlineServers[0]?.id ?? "");
  const [nodeName, setNodeName] = useState("");
  const [port, setPort] = useState("28917");
  const [serverName, setServerName] = useState("www.cloudflare.com");
  const [dest, setDest] = useState("www.cloudflare.com:443");
  const [fingerprint, setFingerprint] = useState("chrome");
  const [confirmations, setConfirmations] = useState<Record<DirectNodeConfirmationKey, boolean>>(initialDirectNodeConfirmations);
  const [planResult, setPlanResult] = useState<LandingNodePlanResponse | null>(null);
  const [createResult, setCreateResult] = useState<LandingNodeCreateResponse | null>(null);
  const [exactConfirm, setExactConfirm] = useState("");
  const [submitting, setSubmitting] = useState<"plan" | "create" | null>(null);
  const [message, setMessage] = useState("请选择在线落地服务器，填写端口，并完成端口放行确认。");

  useEffect(() => {
    if (onlineServers[0] && (!selectedServerId || !onlineServers.some((server) => server.id === selectedServerId))) {
      setSelectedServerId(onlineServers[0].id);
    }
  }, [onlineServers, selectedServerId]);

  const selectedServer = onlineServers.find((server) => server.id === selectedServerId) ?? onlineServers[0] ?? null;
  const resolvedNodeName = nodeName.trim() || (selectedServer ? `${selectedServer.name} 直连节点` : "香港直连15m");
  const portError = validateDirectNodePort(port);
  const parsedPort = Number(port);
  const realityConfigMissing = !serverName.trim() || !dest.trim() || !fingerprint.trim();
  const confirmationsComplete = allDirectNodeConfirmationsChecked(confirmations);
  const planReady = !!planResult?.ready && (planResult.blocked_reasons?.length ?? 0) === 0;
  const canRequestPlan = !!selectedServer && !portError && !realityConfigMissing && confirmationsComplete && submitting === null && !createResult;
  const canCreate =
    !!selectedServer &&
    !!planResult &&
    planReady &&
    !portError &&
    confirmationsComplete &&
    exactConfirm === DIRECT_NODE_CONFIRM_TEXT &&
    submitting === null &&
    !createResult;

  function markConfigDirty() {
    if (planResult || createResult) {
      setPlanResult(null);
      setCreateResult(null);
      setExactConfirm("");
      setStep(1);
      setMessage("配置已变更，请重新生成创建计划。");
    }
  }

  function closeModal() {
    setPlanResult(null);
    setCreateResult(null);
    setExactConfirm("");
    onClose();
  }

  async function handlePlan() {
    if (!selectedServer) {
      setMessage("暂无在线落地服务器，请先添加落地服务器并安装 Worker。");
      return;
    }
    if (portError) {
      setMessage(portError);
      return;
    }
    if (realityConfigMissing) {
      setMessage("请填写 Reality SNI、dest 和 fingerprint。");
      return;
    }
    if (!confirmationsComplete) {
      setMessage("请先完成全部端口放行与安全确认。");
      return;
    }
    setSubmitting("plan");
    setMessage("正在生成创建计划，不会创建 Worker command。");
    try {
      const csrfToken = await fetchCsrfToken();
      if (!csrfToken) {
        setMessage("登录状态或安全校验失败，请刷新后重试。");
        return;
      }
      const result = await createLandingNodePlan(
        selectedServer.id,
        {
          listen_port: parsedPort,
          protocol: "vless",
          security: "reality",
          flow: "xtls-rprx-vision",
          server_name: serverName.trim(),
          dest: dest.trim(),
          fingerprint: fingerprint.trim(),
          remark: resolvedNodeName,
          allow_install_xray: true,
          allow_modify_firewall: true,
          allow_generate_share_link: true,
          allow_overwrite_existing_config: false,
          cloud_security_group_confirmed: confirmations.cloudSecurityGroup,
          cloud_firewall_confirmed: confirmations.cloudFirewall,
          server_firewall_confirmed: confirmations.serverFirewall,
          require_manual_cloud_firewall_confirmation: true,
          require_preflight_success: true,
        },
        csrfToken,
      );
      if (!result.success) {
        setMessage(result.message || "生成创建计划失败。");
        return;
      }
      setPlanResult(result.data);
      setCreateResult(null);
      setStep(result.data.ready && result.data.blocked_reasons.length === 0 ? 3 : 2);
      setMessage(
        result.data.ready && result.data.blocked_reasons.length === 0
          ? "预检计划已生成。确认无误后输入确认文本创建正式 Worker command。"
          : "预检计划已生成，但存在阻断项，不能正式创建。",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "生成创建计划失败。");
    } finally {
      setSubmitting(null);
    }
  }

  async function handleCreate() {
    if (!selectedServer || !planResult || !planReady) {
      setMessage("请先生成 ready 状态的创建计划。");
      return;
    }
    if (planResult.listen_port !== parsedPort) {
      setMessage("端口已变更，请重新生成创建计划。");
      return;
    }
    if (exactConfirm !== DIRECT_NODE_CONFIRM_TEXT) {
      setMessage(`请输入 ${DIRECT_NODE_CONFIRM_TEXT} 后再创建。`);
      return;
    }
    setSubmitting("create");
    setMessage("正在创建正式 landing_node_create Worker command。");
    try {
      const csrfToken = await fetchCsrfToken();
      if (!csrfToken) {
        setMessage("登录状态或安全校验失败，请刷新后重试。");
        return;
      }
      const result = await createLandingNodeExecution(
        selectedServer.id,
        {
          approved_port: parsedPort,
          node_name: resolvedNodeName,
          server_name: serverName.trim(),
          dest: dest.trim(),
          fingerprint: fingerprint.trim(),
          confirm_firewall_open: true,
          confirm_generate_share_link: true,
          confirm_write_share_link_after_success: true,
          confirm_no_existing_xray: false,
          confirm_rollback_new_artifacts_only: true,
        },
        csrfToken,
      );
      if (!result.success) {
        setMessage(result.message || "创建正式命令失败。");
        return;
      }
      setCreateResult(result.data);
      setStep(5);
      setMessage("正式创建命令已创建，等待落地 Worker 轮询执行。");
      await onCompleted?.();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "创建正式命令失败。");
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <ModalShell onClose={closeModal} title="新建直连节点" wide>
      <ProductSteps activeStep={step} steps={directNodeSteps} />
      {!onlineServers.length ? (
        <div className="product-empty-state direct-node-empty">
          <ProductIcon name="server" tone="blue" />
          <strong>暂无在线落地服务器</strong>
          <p>请先添加落地服务器并安装 Worker。未上线 Worker 的服务器不能创建直连节点。</p>
        </div>
      ) : (
        <>
          <div className="product-modal-layout">
            <form className="product-form" onSubmit={(event) => event.preventDefault()}>
              <div className="form-group-title">选择落地服务器</div>
              <label className="product-form-wide">
                <span>在线落地服务器 <em>*</em></span>
                <select
                  disabled={!!createResult || submitting !== null}
                  value={selectedServer?.id ?? ""}
                  onChange={(event) => {
                    setSelectedServerId(event.target.value);
                    markConfigDirty();
                  }}
                >
                  {onlineServers.map((server) => (
                    <option key={server.id} value={server.id}>
                      {server.name} / {server.ip} / Worker {server.worker_version ?? "未返回版本"}
                    </option>
                  ))}
                </select>
              </label>

              <div className="form-group-title">填写节点参数</div>
              <label>
                <span>节点名称</span>
                <input
                  disabled={!!createResult || submitting !== null}
                  placeholder="香港直连15m"
                  value={nodeName}
                  onChange={(event) => {
                    setNodeName(event.target.value);
                    markConfigDirty();
                  }}
                />
              </label>
              <label>
                <span>客户连接端口 <em>*</em></span>
                <small>推荐 10000-30000，请避开控制台和系统常用端口。</small>
                <input
                  disabled={!!createResult || submitting !== null}
                  value={port}
                  onChange={(event) => {
                    setPort(event.target.value);
                    markConfigDirty();
                  }}
                />
              </label>
              <label>
                <span>Reality SNI <em>*</em></span>
                <input
                  disabled={!!createResult || submitting !== null}
                  value={serverName}
                  onChange={(event) => {
                    setServerName(event.target.value);
                    markConfigDirty();
                  }}
                />
              </label>
              <label>
                <span>Reality dest <em>*</em></span>
                <input
                  disabled={!!createResult || submitting !== null}
                  value={dest}
                  onChange={(event) => {
                    setDest(event.target.value);
                    markConfigDirty();
                  }}
                />
              </label>
              <label>
                <span>fingerprint <em>*</em></span>
                <select
                  disabled={!!createResult || submitting !== null}
                  value={fingerprint}
                  onChange={(event) => {
                    setFingerprint(event.target.value);
                    markConfigDirty();
                  }}
                >
                  <option value="chrome">chrome</option>
                  <option value="firefox">firefox</option>
                  <option value="safari">safari</option>
                  <option value="edge">edge</option>
                </select>
              </label>
              <div className="direct-node-protection-card product-form-wide">
                <strong>端口放行与安全确认</strong>
                <p>生成计划前，请先确认客户连接 TCP 端口已经在云服务器安全组、云防火墙和服务器防火墙放行。</p>
                <div className="port-confirm-list direct-node-confirm-list">
                  {directNodeConfirmationItems.map((item) => (
                    <label key={item.key}>
                      <input
                        checked={confirmations[item.key]}
                        disabled={!!createResult || submitting !== null}
                        type="checkbox"
                        onChange={(event) => {
                          setConfirmations((current) => ({ ...current, [item.key]: event.target.checked }));
                          markConfigDirty();
                        }}
                      />
                      <span>
                        <strong>{item.label}</strong>
                        <small>{item.detail}</small>
                      </span>
                    </label>
                  ))}
                </div>
              </div>
              {portError ? <p className="direct-node-form-error product-form-wide">{portError}</p> : null}
              <button className="product-form-submit" disabled={!canRequestPlan} type="button" onClick={() => void handlePlan()}>
                {submitting === "plan" ? "生成中..." : "生成创建计划"}
              </button>
            </form>
            <InfoCard title="正式创建提醒">
              <li>这是正式创建直连节点流程。</li>
              <li>Worker 执行成功后会新增客户端监听端口。</li>
              <li>系统不会修改云安全组 / 云防火墙。</li>
              <li>本次不会 cutover，不会影响现有节点链接。</li>
              <li>失败只允许回滚本次新增内容。</li>
            </InfoCard>
          </div>

          <div className="direct-node-flow-results">
            {planResult ? <DirectNodePlanSummary plan={planResult} /> : null}
            {planResult ? (
              <section className="direct-node-create-confirm">
                <strong>正式创建确认</strong>
                <p>
                  输入 <code>{DIRECT_NODE_CONFIRM_TEXT}</code> 后，才会创建受保护的 landing_node_create Worker command。
                </p>
                <input
                  disabled={!planReady || !!createResult || submitting !== null}
                  placeholder={DIRECT_NODE_CONFIRM_TEXT}
                  value={exactConfirm}
                  onChange={(event) => setExactConfirm(event.target.value)}
                />
                <button disabled={!canCreate} type="button" onClick={() => void handleCreate()}>
                  {submitting === "create" ? "创建中..." : "创建正式命令"}
                </button>
              </section>
            ) : null}
            {createResult ? <DirectNodeCreateSummary result={createResult} /> : null}
          </div>
        </>
      )}
      <p className="demo-safety-note">{message}</p>
      <div className="modal-actions">
        <button className="secondary" type="button" onClick={closeModal}>
          关闭
        </button>
      </div>
    </ModalShell>
  );
}
