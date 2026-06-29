"use client";

import { type ReactNode, useMemo, useState } from "react";

import { ProductIcon } from "@/components/ProductIcons";
import { type NodeData, type TransitResourceData, type VpsServerData } from "@/lib/api";

type ModalProps = {
  onClose: () => void;
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
  { label: "这条线给谁用", detail: "选择客户和用途" },
  { label: "选择服务器和端口", detail: "选择落地服务器" },
  { label: "创建前确认", detail: "核对入口信息" },
  { label: "完成", detail: "完成本页展示" },
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

export function AddLandingServerModal({ onClose }: ModalProps) {
  const [step, setStep] = useState(0);

  return (
    <ModalShell onClose={onClose} title="添加落地服务器" wide>
      <ProductSteps activeStep={step} steps={serverSteps} />
      <div className="product-modal-layout">
        <form className="product-form">
          <p className="required-hint">带 <span>*</span> 的为必填项。</p>
          <label>
            <span>服务器名称 <em>*</em></span>
            <input placeholder="例如：香港落地15m" />
          </label>
          <label>
            <span>服务器 IP <em>*</em></span>
            <input placeholder="例如：64.90.13.19" />
          </label>
          <label>
            <span>SSH 端口 <em>*</em></span>
            <input placeholder="22" />
          </label>
          <label>
            <span>SSH 用户 <em>*</em></span>
            <input placeholder="root" />
          </label>
          <label className="product-form-wide">
            备注
            <textarea placeholder="填写地区、用途或客户备注。本阶段不会保存到后端。" />
          </label>
        </form>
        <InfoCard title="这一步要做什么？">
          <li>填写你要接入的落地服务器信息。</li>
          <li>添加完成后，系统会引导你安装服务器助手。</li>
          <li>这里只是接入服务器，不会立即创建线路。</li>
        </InfoCard>
      </div>
      <div className="modal-actions">
        <button className="secondary" type="button" onClick={onClose}>
          取消
        </button>
        <button type="button" onClick={() => setStep((current) => Math.min(current + 1, serverSteps.length - 1))}>
          {step >= serverSteps.length - 1 ? "完成" : "下一步"}
        </button>
      </div>
    </ModalShell>
  );
}

export function AddTransitServerModal({ onClose }: ModalProps) {
  const [step, setStep] = useState(0);

  return (
    <ModalShell onClose={onClose} title="添加中转服务器" wide>
      <ProductSteps activeStep={step} steps={serverSteps} />
      <div className="product-modal-layout">
        <form className="product-form">
          <p className="required-hint">带 <span>*</span> 的为必填项。</p>
          <div className="form-group-title">基础信息</div>
          <label>
            <span>中转名称 <em>*</em></span>
            <input placeholder="例如：广州IEPL-香港出口01" />
          </label>
          <label>
            <span>客户连接 IP <em>*</em></span>
            <small>客户或 OBS 最终连接的地址。</small>
            <input placeholder="客户最终连接的入口 IP" />
          </label>
          <label>
            <span>SSH 登录 IP <em>*</em></span>
            <small>系统连接这台中转服务器使用的管理地址。</small>
            <input placeholder="用于安装助手的管理 IP" />
          </label>
          <label>
            <span>SSH 端口 <em>*</em></span>
            <input placeholder="22" />
          </label>
          <label>
            <span>SSH 用户 <em>*</em></span>
            <input placeholder="root" />
          </label>
          <div className="form-group-title optional">补充信息（可选）</div>
          <label>
            入口地区
            <input placeholder="广州 / 香港 / 新加坡" />
          </label>
          <label>
            出口地区
            <input placeholder="香港 / 美国 / 越南" />
          </label>
          <label>
            带宽
            <input placeholder="例如：100 Mbps" />
          </label>
          <label>
            月流量
            <input placeholder="例如：1000 GB" />
          </label>
          <label className="product-form-wide">
            备注
            <textarea placeholder="填写线路商、客户用途或到期提醒。本阶段不会保存到后端。" />
          </label>
        </form>
        <InfoCard title="这一步要做什么？">
          <li>客户会先连接到这台中转服务器。</li>
          <li>它再把流量转发到落地节点。</li>
          <li>添加完成后，才能继续创建中转线路。</li>
        </InfoCard>
      </div>
      <div className="modal-actions">
        <button className="secondary" type="button" onClick={onClose}>
          取消
        </button>
        <button type="button" onClick={() => setStep((current) => Math.min(current + 1, serverSteps.length - 1))}>
          {step >= serverSteps.length - 1 ? "完成" : "下一步"}
        </button>
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
      <div className="modal-actions">
        <button className="secondary" type="button" onClick={() => setStep((current) => Math.max(current - 1, 0))}>
          上一步
        </button>
        <button className="secondary" type="button" onClick={() => setStep((current) => Math.min(current + 1, transitLineSteps.length - 1))}>
          下一步
        </button>
        <button disabled={lineMode === "provider" || step < transitLineSteps.length - 2} type="button" onClick={() => setStep(transitLineSteps.length - 1)}>
          创建中转线路
        </button>
      </div>
    </ModalShell>
  );
}

export function CreateDirectNodeModal({
  onClose,
  servers,
}: ModalProps & {
  servers: VpsServerData[];
}) {
  const [step, setStep] = useState(0);
  const [customer, setCustomer] = useState("客户A");
  const [purpose, setPurpose] = useState("Facebook 主线");
  const [port, setPort] = useState("28917");
  const defaultServer = useMemo(() => servers.find((server) => server.worker_online) ?? servers[0] ?? null, [servers]);
  const suggestedName = `${customer}-${purpose.replace(/\s+/g, "")}-直连`;

  return (
    <ModalShell onClose={onClose} title="新建直连节点" wide>
      <ProductSteps activeStep={step} steps={directNodeSteps} />
      <div className="product-modal-layout">
        <form className="product-form">
          <div className="form-group-title">第 1 步：这条线给谁用？</div>
          <label>
            分配给谁
            <select value={customer} onChange={(event) => setCustomer(event.target.value)}>
              <option>自己使用</option>
              <option>客户A</option>
              <option>客户B</option>
              <option>未分配</option>
              <option>新建客户</option>
            </select>
          </label>
          <label>
            用途是什么
            <select value={purpose} onChange={(event) => setPurpose(event.target.value)}>
              <option>看视频 / 日常使用</option>
              <option>Facebook 主线</option>
              <option>Facebook 备用线</option>
              <option>TikTok 主线</option>
              <option>TikTok 备用线</option>
              <option>YouTube 主线</option>
              <option>测试线路</option>
            </select>
          </label>
          <div className="form-group-title">第 2 步：选择服务器和端口</div>
          <label className="product-form-wide">
            落地服务器
            <select defaultValue={defaultServer?.id ?? ""}>
              {servers.length ? (
                servers.map((server) => (
                  <option key={server.id} value={server.id}>
                    {server.name} / {server.ip}
                  </option>
                ))
              ) : (
                <option value="">暂无落地服务器</option>
              )}
            </select>
          </label>
          <label>
            客户连接端口
            <input value={port} onChange={(event) => setPort(event.target.value)} />
          </label>
          <label>
            系统建议名称
            <input readOnly value={suggestedName} />
          </label>
        </form>
        <InfoCard title="创建前确认">
          <li>线路名称：{suggestedName}</li>
          <li>接入方式：直连节点</li>
          <li>入口地址：{endpoint(defaultServer?.ip, Number(port) || null)}</li>
          <li>用途：{purpose}</li>
        </InfoCard>
      </div>
      <div className="modal-actions">
        <button className="secondary" type="button" onClick={onClose}>
          取消
        </button>
        <button className="secondary" type="button" onClick={() => setStep((current) => Math.min(current + 1, 3))}>
          下一步
        </button>
        <button type="button" onClick={() => setStep(3)}>
          创建直连节点
        </button>
      </div>
    </ModalShell>
  );
}
