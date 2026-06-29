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
  { label: "设置端口", detail: "填写客户连接端口" },
  { label: "端口放行", detail: "人工确认防火墙放行" },
  { label: "创建完成", detail: "后续阶段接入真实创建" },
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
          <label>
            <span>服务器名称 <em>必填</em></span>
            <input placeholder="例如：香港落地15m" />
          </label>
          <label>
            <span>服务器IP <em>必填</em></span>
            <input placeholder="例如：64.90.13.19" />
          </label>
          <label>
            <span>SSH端口 <em>必填</em></span>
            <input placeholder="22" />
          </label>
          <label>
            <span>SSH用户 <em>必填</em></span>
            <input placeholder="root" />
          </label>
          <label className="product-form-wide">
            备注
            <textarea placeholder="填写地区、用途或客户备注。本阶段不会保存到后端。" />
          </label>
        </form>
        <InfoCard title="这一步要做什么？">
          <li>填写要接入的落地服务器信息。</li>
          <li>添加完成后可继续创建直连节点。</li>
          <li>这里只是产品化流程展示，不会立即创建节点。</li>
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
          <label>
            <span>中转名称 <em>必填</em></span>
            <input placeholder="例如：广州IEPL-香港出口01" />
          </label>
          <label>
            <span>客户连接IP <em>必填</em></span>
            <input placeholder="客户最终连接的入口 IP" />
          </label>
          <label>
            <span>SSH登录IP <em>必填</em></span>
            <input placeholder="用于安装助手的管理 IP" />
          </label>
          <label>
            <span>SSH端口 <em>必填</em></span>
            <input placeholder="22" />
          </label>
          <label>
            <span>SSH用户 <em>必填</em></span>
            <input placeholder="root" />
          </label>
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
          <li>客户先连接到这台服务器。</li>
          <li>它会把流量转发到落地节点。</li>
          <li>添加成功后可继续创建中转线路。</li>
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
      <ProductSteps activeStep={step} steps={transitLineSteps} />
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
                  <small>{node.reality_server_name ?? "SNI 未返回"}</small>
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
            <span><ProductIcon name="dashboard" tone="slate" />本地 / OBS</span>
            <span><ProductIcon name="servers" tone="orange" />中转服务器：{endpoint(selectedResource?.entry_host, Number(port) || null)}</span>
            <span><ProductIcon name="builder" tone="green" />落地节点：{endpoint(selectedNode?.vps_ip, selectedNode?.port)}</span>
            <span><ProductIcon name="route" tone="purple" />Facebook / TikTok</span>
          </div>
          <strong>请确认端口已放行 <em>必填</em></strong>
          <div className="port-confirm-list">
            <label>
              <input
                checked={checks.cloudSecurityGroup}
                type="checkbox"
                onChange={(event) => setChecks((current) => ({ ...current, cloudSecurityGroup: event.target.checked }))}
              />
              云安全组已放行
            </label>
            <label>
              <input
                checked={checks.cloudFirewall}
                type="checkbox"
                onChange={(event) => setChecks((current) => ({ ...current, cloudFirewall: event.target.checked }))}
              />
              云防火墙已放行
            </label>
            <label>
              <input
                checked={checks.serverFirewall}
                type="checkbox"
                onChange={(event) => setChecks((current) => ({ ...current, serverFirewall: event.target.checked }))}
              />
              服务器防火墙已放行
            </label>
          </div>
          <p>新增或变更客户连接端口后，请务必同步检查云服务器安全组、云防火墙、服务器防火墙是否放行。</p>
        </aside>
      </div>
      <div className="modal-actions">
        <button className="secondary" type="button" onClick={() => setStep((current) => Math.max(current - 1, 0))}>
          上一步
        </button>
        <button className="secondary" type="button" onClick={() => setStep((current) => Math.min(current + 1, transitLineSteps.length - 1))}>
          下一步
        </button>
        <button disabled={step < transitLineSteps.length - 2} type="button" onClick={() => setStep(transitLineSteps.length - 1)}>
          创建中转线路（演示）
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
  const defaultServer = useMemo(() => servers.find((server) => server.worker_online) ?? servers[0] ?? null, [servers]);

  return (
    <ModalShell onClose={onClose} title="新建直连节点" wide>
      <ProductSteps
        activeStep={step}
        steps={[
          { label: "选择服务器", detail: "选择落地服务器" },
          { label: "配置端口", detail: "填写客户连接端口" },
          { label: "创建确认", detail: "人工确认安全边界" },
          { label: "完成", detail: "后续阶段接入真实创建" },
        ]}
      />
      <div className="product-modal-layout">
        <form className="product-form">
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
            节点名称
            <input placeholder="例如：客户A-Facebook越南主线" />
          </label>
          <label>
            客户连接端口
            <input placeholder="例如：28917" />
          </label>
          <label>
            直播平台
            <select defaultValue="Facebook">
              <option>Facebook</option>
              <option>TikTok</option>
              <option>YouTube</option>
              <option>日常使用</option>
            </select>
          </label>
          <label>
            线路用途
            <select defaultValue="主线">
              <option>主线</option>
              <option>备用线</option>
              <option>测试线</option>
            </select>
          </label>
        </form>
        <InfoCard title="创建前确认">
          <li>直连节点会使用落地服务器作为客户入口。</li>
          <li>真实创建会在后续阶段接入，本弹窗不会发起后台任务。</li>
          <li>端口变更前仍需人工确认云安全组、云防火墙和服务器防火墙。</li>
        </InfoCard>
      </div>
      <div className="modal-actions">
        <button className="secondary" type="button" onClick={onClose}>
          取消
        </button>
        <button className="secondary" type="button" onClick={() => setStep((current) => Math.min(current + 1, 3))}>
          下一步
        </button>
        <button disabled type="button">
          创建直连节点（演示）
        </button>
      </div>
    </ModalShell>
  );
}
