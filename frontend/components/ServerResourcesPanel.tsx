"use client";

import { useEffect, useMemo, useState } from "react";

import {
  apiFetch,
  type TransitResourceData,
  type TransitResourceListResult,
  type VpsServerData,
  type VpsServerListResult,
} from "@/lib/api";

type ResourceTab = "landing" | "selfTransit" | "providerTransit";

function helperStatusLabel(resource: { worker_online?: boolean; worker_display_status?: string | null; display_status?: string | null }) {
  if (resource.worker_online) {
    return "服务器助手在线";
  }
  const displayStatus = resource.worker_display_status ?? resource.display_status;
  if (displayStatus === "stale") {
    return "服务器助手心跳过期";
  }
  if (displayStatus === "deleted") {
    return "已删除";
  }
  return "等待服务器助手";
}

function serverStatusLabel(status: string | null | undefined) {
  const labels: Record<string, string> = {
    active: "可用",
    online: "在线",
    worker_online: "助手在线",
    pending_worker: "等待助手",
    disabled: "停用",
    deleted: "已删除",
  };
  return status ? labels[status] ?? status : "未返回";
}

function endpoint(host: string | null | undefined, port: number | null | undefined) {
  if (!host) {
    return "未返回";
  }
  return port ? `${host}:${port}` : host;
}

export function ServerResourcesPanel() {
  const [activeTab, setActiveTab] = useState<ResourceTab>("landing");
  const [servers, setServers] = useState<VpsServerData[]>([]);
  const [resources, setResources] = useState<TransitResourceData[]>([]);
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

  const selfTransitResources = useMemo(
    () => resources.filter((resource) => resource.resource_type === "server" && !resource.deleted_at),
    [resources],
  );
  const providerTransitResources = useMemo(
    () => resources.filter((resource) => resource.resource_type !== "server" && !resource.deleted_at),
    [resources],
  );
  const visibleServers = servers.filter((server) => server.status !== "deleted");

  return (
    <section className="customer-workspace wide">
      <div className="workspace-hero">
        <div>
          <h2>服务器资源</h2>
          <p>集中查看落地服务器、自建中转服务器和商家入口。真实新增和删除仍在高级调试中保留。</p>
        </div>
        <button className="secondary" type="button" onClick={() => void loadData()}>
          刷新
        </button>
      </div>

      <div className="resource-tabs" role="tablist" aria-label="服务器资源分类">
        <button className={activeTab === "landing" ? "selected" : ""} type="button" onClick={() => setActiveTab("landing")}>
          落地服务器
        </button>
        <button
          className={activeTab === "selfTransit" ? "selected" : ""}
          type="button"
          onClick={() => setActiveTab("selfTransit")}
        >
          中转服务器（自建）
        </button>
        <button
          className={activeTab === "providerTransit" ? "selected" : ""}
          type="button"
          onClick={() => setActiveTab("providerTransit")}
        >
          商家中转入口
        </button>
      </div>

      {activeTab === "landing" ? (
        <div className="resource-card-grid">
          {visibleServers.length ? (
            visibleServers.map((server) => (
              <article className="resource-card" key={server.id}>
                <div className="line-card-title">
                  <div>
                    <strong>{server.name}</strong>
                    <span>{server.ip}</span>
                  </div>
                  <span className={`pill ${server.worker_online ? "ok" : "warn"}`}>{helperStatusLabel(server)}</span>
                </div>
                <div className="business-detail-grid compact">
                  <span>用途</span>
                  <strong>落地节点服务</strong>
                  <span>入口</span>
                  <strong>{server.ip}</strong>
                  <span>状态</span>
                  <strong>{serverStatusLabel(server.display_status ?? server.status)}</strong>
                  <span>节点数量</span>
                  <strong>{server.nodes.length}</strong>
                </div>
                <div className="line-card-actions">
                  <button disabled type="button">
                    添加资源
                  </button>
                  <button disabled type="button">
                    安装服务器助手
                  </button>
                </div>
              </article>
            ))
          ) : (
            <div className="empty">暂无落地服务器记录。</div>
          )}
        </div>
      ) : null}

      {activeTab === "selfTransit" ? (
        <div className="resource-card-grid">
          {selfTransitResources.length ? (
            selfTransitResources.map((resource) => (
              <TransitResourceCard key={resource.id} resource={resource} typeLabel="自建中转服务器" />
            ))
          ) : (
            <div className="empty">暂无自建中转服务器记录。</div>
          )}
        </div>
      ) : null}

      {activeTab === "providerTransit" ? (
        <div className="resource-card-grid">
          {providerTransitResources.length ? (
            providerTransitResources.map((resource) => (
              <TransitResourceCard key={resource.id} resource={resource} typeLabel="商家中转入口" />
            ))
          ) : (
            <div className="empty">暂无商家中转入口记录。</div>
          )}
        </div>
      ) : null}

      <p className="message">{message}</p>
    </section>
  );
}

function TransitResourceCard({ resource, typeLabel }: { resource: TransitResourceData; typeLabel: string }) {
  return (
    <article className="resource-card">
      <div className="line-card-title">
        <div>
          <strong>{resource.name}</strong>
          <span>{endpoint(resource.entry_host, resource.entry_port)}</span>
        </div>
        <span className={`pill ${resource.worker_online ? "ok" : "warn"}`}>{helperStatusLabel(resource)}</span>
      </div>
      <div className="business-detail-grid compact">
        <span>类型</span>
        <strong>{typeLabel}</strong>
        <span>入口地区</span>
        <strong>{resource.entry_region ?? "未填写"}</strong>
        <span>出口地区</span>
        <strong>{resource.exit_region ?? "未填写"}</strong>
        <span>状态</span>
        <strong>{serverStatusLabel(resource.display_status ?? resource.status)}</strong>
      </div>
      <div className="line-card-actions">
        <button disabled type="button">
          添加资源
        </button>
        <button disabled type="button">
          安装服务器助手
        </button>
      </div>
    </article>
  );
}
