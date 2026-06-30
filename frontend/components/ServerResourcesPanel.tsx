"use client";

import { useEffect, useMemo, useState } from "react";

import { AddLandingServerModal, AddTransitServerModal, CreateDirectNodeModal, CreateTransitLineModal } from "@/components/ProductDemoModals";
import { ProductIcon } from "@/components/ProductIcons";
import {
  apiFetch,
  type NodeData,
  type NodeListResult,
  type TransitResourceData,
  type TransitResourceListResult,
  type VpsServerData,
  type VpsServerListResult,
} from "@/lib/api";

type ServerModal = "landing" | "transit" | "direct" | "transitLine" | null;
type DetailTarget = { kind: "landing"; data: VpsServerData } | { kind: "transit"; data: TransitResourceData } | null;
type ResourceTab = "landing" | "transit" | "provider";

function helperStatusLabel(resource: { worker_online?: boolean; worker_display_status?: string | null; display_status?: string | null }) {
  if (resource.worker_online) {
    return "运行正常";
  }
  const displayStatus = resource.worker_display_status ?? resource.display_status;
  if (displayStatus === "stale") {
    return "心跳过期";
  }
  if (displayStatus === "deleted") {
    return "已删除";
  }
  return "等待助手";
}

function statusTone(resource: { worker_online?: boolean; worker_display_status?: string | null; display_status?: string | null }) {
  if (resource.worker_online) {
    return "success";
  }
  const displayStatus = resource.worker_display_status ?? resource.display_status;
  if (displayStatus === "stale") {
    return "warning";
  }
  if (displayStatus === "deleted") {
    return "danger";
  }
  return "info";
}

function heartbeat(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "未返回";
}

function endpoint(host: string | null | undefined, port: number | null | undefined) {
  if (!host) {
    return "未返回";
  }
  return port ? `${host}:${port}` : host;
}

export function ServerResourcesPanel() {
  const [servers, setServers] = useState<VpsServerData[]>([]);
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [activeModal, setActiveModal] = useState<ServerModal>(null);
  const [detailTarget, setDetailTarget] = useState<DetailTarget>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<ResourceTab>("landing");
  const [message, setMessage] = useState("正在读取服务器资源。");

  async function loadData() {
    const [serverResult, nodeResult, resourceResult] = await Promise.all([
      apiFetch<VpsServerListResult>("/api/vps"),
      apiFetch<NodeListResult>("/api/nodes"),
      apiFetch<TransitResourceListResult>("/api/transit-resources"),
    ]);
    if (serverResult.success) {
      setServers(serverResult.data.servers);
    }
    if (nodeResult.success) {
      setNodes(nodeResult.data.nodes);
    }
    if (resourceResult.success) {
      setResources(resourceResult.data.resources);
    }
    setMessage(serverResult.success && nodeResult.success && resourceResult.success ? "服务器资源已刷新。" : "部分资源暂时无法读取。");
  }

  useEffect(() => {
    void loadData();
  }, []);

  const visibleServers = useMemo(() => servers.filter((server) => server.status !== "deleted"), [servers]);
  const selfTransitResources = useMemo(
    () => resources.filter((resource) => resource.resource_type === "server" && !resource.deleted_at),
    [resources],
  );
  const providerTransitResources = useMemo(
    () => resources.filter((resource) => resource.resource_type !== "server" && !resource.deleted_at),
    [resources],
  );

  function openModal(nextModal: ServerModal) {
    setMenuOpen(false);
    setActiveModal(nextModal);
  }

  return (
    <section className="server-resources-page wide">
      <div className="resource-page-actions">
        <div className="resource-add-menu">
          <button type="button" onClick={() => setMenuOpen((open) => !open)}>
            添加服务器
          </button>
          {menuOpen ? (
            <div className="resource-add-dropdown">
              <button type="button" onClick={() => openModal("landing")}>
                添加落地服务器
              </button>
              <button type="button" onClick={() => openModal("transit")}>
                添加中转服务器
              </button>
              <button disabled type="button">
                添加商家中转入口
              </button>
            </div>
          ) : null}
        </div>
      </div>

      <div className="resource-overview-strip">
        <ResourceMiniStat label="落地服务器" value={`${visibleServers.length} 台`} />
        <ResourceMiniStat label="在线落地助手" value={`${visibleServers.filter((server) => server.worker_online).length} 台`} />
        <ResourceMiniStat label="自建中转" value={`${selfTransitResources.length} 台`} />
        <ResourceMiniStat label="商家中转入口" value={`${providerTransitResources.length} 个`} />
      </div>

      <div className="product-tab-strip">
        <button className={activeTab === "landing" ? "selected" : ""} type="button" onClick={() => setActiveTab("landing")}>
          落地服务器
        </button>
        <button className={activeTab === "transit" ? "selected" : ""} type="button" onClick={() => setActiveTab("transit")}>
          中转服务器
        </button>
        <button className={activeTab === "provider" ? "selected" : ""} type="button" onClick={() => setActiveTab("provider")}>
          商家中转入口
        </button>
      </div>

      {activeTab === "landing" ? (
      <section className="product-section-card">
        <div className="product-section-head">
          <h3>落地服务器</h3>
          <span className="product-badge info">可创建直连节点</span>
        </div>
        {visibleServers.length ? (
          <div className="resource-management-grid">
            {visibleServers.map((server) => (
              <article className="resource-management-card" key={server.id}>
                <div className="resource-card-top">
                  <span className="resource-region-icon">落</span>
                  <div>
                    <strong>{server.name}</strong>
                    <small>{server.ip}</small>
                  </div>
                  <span className={`product-badge ${statusTone(server)}`}><span className="status-dot" />{helperStatusLabel(server)}</span>
                </div>
                <div className="resource-facts">
                  <span>地区</span>
                  <strong>{server.notes?.split(/\s+/)[0] ?? "未填写"}</strong>
                  <span>IP</span>
                  <strong>{server.ip}</strong>
                  <span>可创建节点数量</span>
                  <strong>{server.worker_online ? "可创建" : "等待助手"}</strong>
                  <span>最近心跳</span>
                  <strong>{heartbeat(server.worker_last_heartbeat_at)}</strong>
                </div>
                <div className="resource-card-actions">
                  <button className="secondary" type="button" onClick={() => setDetailTarget({ kind: "landing", data: server })}>
                    查看
                  </button>
                  <button type="button" onClick={() => setActiveModal("direct")}>
                    新建直连节点
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="product-empty-state inline">
            <ProductIcon name="server" tone="blue" />
            <strong>暂无落地服务器</strong>
            <p>你可以先添加一台落地服务器，再创建直连节点。</p>
            <button type="button" onClick={() => setActiveModal("landing")}>添加落地服务器</button>
          </div>
        )}
      </section>
      ) : null}

      {activeTab === "transit" ? (
      <section className="product-section-card">
        <div className="product-section-head">
          <h3>中转服务器</h3>
          <span className="product-badge info">自建中转</span>
        </div>
        {selfTransitResources.length ? (
          <div className="resource-management-grid">
            {selfTransitResources.map((resource) => (
              <TransitResourceCard
                key={resource.id}
                resource={resource}
                typeLabel="自建中转服务器"
                onOpenDetail={() => setDetailTarget({ kind: "transit", data: resource })}
                onOpenTransitLine={() => setActiveModal("transitLine")}
              />
            ))}
          </div>
        ) : (
          <div className="product-empty-state inline">
            <ProductIcon name="servers" tone="orange" />
            <strong>暂无中转服务器</strong>
            <p>你可以先添加一台中转服务器，再创建中转线路。</p>
            <button type="button" onClick={() => setActiveModal("transit")}>添加中转服务器</button>
          </div>
        )}
      </section>
      ) : null}

      {activeTab === "provider" ? (
      <section className="product-section-card">
        <div className="product-section-head">
          <h3>商家中转入口</h3>
          <span className="product-badge info">后续接入</span>
        </div>
        {providerTransitResources.length ? (
          <div className="resource-management-grid">
            {providerTransitResources.map((resource) => (
              <TransitResourceCard
                key={resource.id}
                resource={resource}
                typeLabel="商家中转入口"
                onOpenDetail={() => setDetailTarget({ kind: "transit", data: resource })}
                onOpenTransitLine={() => setActiveModal("transitLine")}
              />
            ))}
          </div>
        ) : (
          <div className="product-empty-state inline">
            <ProductIcon name="route" tone="purple" />
            <strong>暂无商家中转入口</strong>
            <p>后续可以在这里添加线路商提供的中转入口。</p>
            <button disabled type="button">添加商家中转入口</button>
          </div>
        )}
      </section>
      ) : null}

      <p className="message">{message}</p>

      {activeModal === "landing" ? <AddLandingServerModal onClose={() => setActiveModal(null)} onCompleted={loadData} /> : null}
      {activeModal === "transit" ? <AddTransitServerModal onClose={() => setActiveModal(null)} onCompleted={loadData} /> : null}
      {activeModal === "direct" ? <CreateDirectNodeModal servers={servers} onClose={() => setActiveModal(null)} onCompleted={loadData} /> : null}
      {activeModal === "transitLine" ? (
        <CreateTransitLineModal nodes={nodes.filter((node) => node.status === "active")} resources={resources.filter((resource) => !resource.deleted_at)} onClose={() => setActiveModal(null)} />
      ) : null}
      {detailTarget ? <ResourceDetailModal target={detailTarget} onClose={() => setDetailTarget(null)} /> : null}
    </section>
  );
}

function ResourceMiniStat({ label, value }: { label: string; value: string }) {
  return (
    <article className="resource-mini-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function TransitResourceCard({
  onOpenDetail,
  onOpenTransitLine,
  resource,
  typeLabel,
}: {
  onOpenDetail: () => void;
  onOpenTransitLine: () => void;
  resource: TransitResourceData;
  typeLabel: string;
}) {
  return (
    <article className="resource-management-card">
      <div className="resource-card-top">
        <span className="resource-region-icon"><ProductIcon name="route" tone="orange" /></span>
        <div>
          <strong>{resource.name}</strong>
          <small>{endpoint(resource.entry_host, resource.entry_port)}</small>
        </div>
        <span className={`product-badge ${statusTone(resource)}`}><span className="status-dot" />{helperStatusLabel(resource)}</span>
      </div>
      <div className="resource-facts">
        <span>类型</span>
        <strong>{typeLabel}</strong>
        <span>客户连接IP</span>
        <strong>{resource.entry_host ?? "未填写"}</strong>
        <span>出口地区</span>
        <strong>{resource.exit_region ?? "未填写"}</strong>
        <span>最近心跳</span>
        <strong>{heartbeat(resource.worker_last_heartbeat_at)}</strong>
      </div>
      <div className="resource-card-actions">
        <button className="secondary" type="button" onClick={onOpenDetail}>
          查看
        </button>
        <button type="button" onClick={onOpenTransitLine}>
          新建中转线路
        </button>
      </div>
    </article>
  );
}

function ResourceDetailModal({ onClose, target }: { onClose: () => void; target: DetailTarget }) {
  if (!target) {
    return null;
  }
  const isLanding = target.kind === "landing";
  const name = isLanding ? target.data.name : target.data.name;
  const endpointText = isLanding ? endpoint(target.data.ip, 22) : endpoint(target.data.entry_host, target.data.entry_port);
  return (
    <div className="modal-backdrop" role="presentation">
      <div className="modal-card customer-line-modal">
        <div className="modal-header">
          <h3>{name}</h3>
          <button className="modal-close-button" type="button" onClick={onClose}>×</button>
        </div>
        <div className="business-detail-grid">
          <span>资源类型</span>
          <strong>{isLanding ? "落地服务器" : "中转服务器"}</strong>
          <span>入口地址</span>
          <strong>{endpointText}</strong>
          <span>当前状态</span>
          <strong>{helperStatusLabel(target.data)}</strong>
          <span>最近心跳</span>
          <strong>{heartbeat(isLanding ? target.data.worker_last_heartbeat_at : target.data.worker_last_heartbeat_at)}</strong>
        </div>
        <p className="message">当前详情仅用于查看资源信息，不会保存数据、不会安装助手、不会创建任务。</p>
      </div>
    </div>
  );
}
