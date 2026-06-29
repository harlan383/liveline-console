"use client";

import { useEffect, useMemo, useState } from "react";

import { AddLandingServerModal, AddTransitServerModal } from "@/components/ProductDemoModals";
import {
  apiFetch,
  type TransitResourceData,
  type TransitResourceListResult,
  type VpsServerData,
  type VpsServerListResult,
} from "@/lib/api";

type ServerModal = "landing" | "transit" | null;

function helperStatusLabel(resource: { worker_online?: boolean; worker_display_status?: string | null; display_status?: string | null }) {
  if (resource.worker_online) {
    return "在线";
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
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [activeModal, setActiveModal] = useState<ServerModal>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [message, setMessage] = useState("正在读取服务器资源。");

  async function loadData() {
    const [serverResult, resourceResult] = await Promise.all([
      apiFetch<VpsServerListResult>("/api/vps"),
      apiFetch<TransitResourceListResult>("/api/transit-resources"),
    ]);
    if (serverResult.success) {
      setServers(serverResult.data.servers);
    }
    if (resourceResult.success) {
      setResources(resourceResult.data.resources);
    }
    setMessage(serverResult.success && resourceResult.success ? "服务器资源已刷新。" : "部分资源暂时无法读取。");
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
      <div className="product-page-header">
        <div>
          <h2>服务器资源</h2>
          <p>集中管理落地服务器、自建中转服务器和商家中转入口。</p>
        </div>
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

      <section className="product-section-card">
        <div className="product-section-head">
          <h3>落地服务器</h3>
          <span className="product-badge info">服务器助手</span>
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
                  <span className={`product-badge ${statusTone(server)}`}>{helperStatusLabel(server)}</span>
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
                  <button className="secondary" disabled type="button">
                    查看
                  </button>
                  <button disabled type="button">
                    新建直连节点
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty">暂无落地服务器记录。</div>
        )}
      </section>

      <section className="product-section-card">
        <div className="product-section-head">
          <h3>中转服务器</h3>
          <span className="product-badge info">自建与商家入口</span>
        </div>
        {selfTransitResources.length || providerTransitResources.length ? (
          <div className="resource-management-grid">
            {selfTransitResources.map((resource) => (
              <TransitResourceCard key={resource.id} resource={resource} typeLabel="自建中转服务器" />
            ))}
            {providerTransitResources.map((resource) => (
              <TransitResourceCard key={resource.id} resource={resource} typeLabel="商家中转入口" />
            ))}
          </div>
        ) : (
          <div className="empty">暂无中转服务器或商家入口记录。</div>
        )}
      </section>

      <p className="message">{message}</p>

      {activeModal === "landing" ? <AddLandingServerModal onClose={() => setActiveModal(null)} /> : null}
      {activeModal === "transit" ? <AddTransitServerModal onClose={() => setActiveModal(null)} /> : null}
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

function TransitResourceCard({ resource, typeLabel }: { resource: TransitResourceData; typeLabel: string }) {
  return (
    <article className="resource-management-card">
      <div className="resource-card-top">
        <span className="resource-region-icon">中</span>
        <div>
          <strong>{resource.name}</strong>
          <small>{endpoint(resource.entry_host, resource.entry_port)}</small>
        </div>
        <span className={`product-badge ${statusTone(resource)}`}>{helperStatusLabel(resource)}</span>
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
        <button className="secondary" disabled type="button">
          查看
        </button>
        <button disabled type="button">
          新建中转线路
        </button>
      </div>
    </article>
  );
}
