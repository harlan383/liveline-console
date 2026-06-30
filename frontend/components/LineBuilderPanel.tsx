"use client";

import { useEffect, useMemo, useState } from "react";

import {
  AddLandingServerModal,
  AddTransitServerModal,
  CreateDirectNodeModal,
  CreateTransitLineModal,
} from "@/components/ProductDemoModals";
import { ProductIcon } from "@/components/ProductIcons";
import {
  apiFetch,
  type NodeData,
  type NodeListResult,
  type TaskData,
  type TaskListResult,
  type TransitResourceData,
  type TransitResourceListResult,
  type TransitRouteData,
  type TransitRouteListResult,
  type VpsServerData,
  type VpsServerListResult,
} from "@/lib/api";

type BuilderModal = "landing" | "transit" | "direct" | "transitLine" | null;

function endpoint(host: string | null | undefined, port: number | null | undefined) {
  if (!host) {
    return "未返回";
  }
  return port ? `${host}:${port}` : host;
}

function taskName(task: TaskData | null) {
  if (!task) {
    return "暂无记录";
  }
  const labels: Record<string, string> = {
    landing_node_create: "创建直连节点",
    transit_route_create: "创建中转线路",
    cleanup_landing_node: "删除节点",
    cleanup_landing_server: "清理落地服务器",
    cleanup_transit_route: "清理中转线路",
    cleanup_transit_resource: "清理中转服务器",
  };
  return labels[task.task_type] ?? "系统操作";
}

export function LineBuilderPanel() {
  const [servers, setServers] = useState<VpsServerData[]>([]);
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [routes, setRoutes] = useState<TransitRouteData[]>([]);
  const [tasks, setTasks] = useState<TaskData[]>([]);
  const [activeModal, setActiveModal] = useState<BuilderModal>(null);
  const [message, setMessage] = useState("正在读取线路搭建数据。");

  async function loadData() {
    const [serverResult, nodeResult, resourceResult, routeResult, taskResult] = await Promise.all([
      apiFetch<VpsServerListResult>("/api/vps"),
      apiFetch<NodeListResult>("/api/nodes"),
      apiFetch<TransitResourceListResult>("/api/transit-resources"),
      apiFetch<TransitRouteListResult>("/api/transit-routes"),
      apiFetch<TaskListResult>("/api/tasks?limit=8"),
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
    if (routeResult.success) {
      setRoutes(routeResult.data.routes);
    }
    if (taskResult.success) {
      setTasks(taskResult.data.tasks);
    }

    setMessage(
      [serverResult, nodeResult, resourceResult, routeResult, taskResult].every((result) => result.success)
        ? "线路搭建数据已刷新。"
        : "部分数据暂时无法读取，请稍后刷新。",
    );
  }

  useEffect(() => {
    void loadData();
  }, []);

  const activeNodes = useMemo(() => nodes.filter((node) => node.status === "active"), [nodes]);
  const activeRoutes = useMemo(
    () => routes.filter((route) => route.status === "active" && !route.deleted_at),
    [routes],
  );
  const onlineLandingServers = useMemo(
    () => servers.filter((server) => server.worker_online && server.status !== "deleted"),
    [servers],
  );
  const onlineTransitResources = useMemo(
    () => resources.filter((resource) => resource.worker_online && !resource.deleted_at && resource.resource_type === "server"),
    [resources],
  );
  const visibleTransitResources = useMemo(
    () => resources.filter((resource) => !resource.deleted_at && resource.resource_type === "server"),
    [resources],
  );
  const recentCreated = useMemo(() => {
    const items = [
      ...activeNodes.map((node) => ({
        createdAt: node.created_at,
        title: node.node_name,
        detail: `直连节点 / ${endpoint(node.vps_ip, node.port)}`,
      })),
      ...activeRoutes.map((route) => ({
        createdAt: route.created_at,
        title: route.name,
        detail: `中转线路 / ${endpoint(route.target_host, route.target_port)}`,
      })),
      ...visibleTransitResources.map((resource) => ({
        createdAt: resource.created_at,
        title: resource.name,
        detail: `中转服务器 / ${endpoint(resource.entry_host, resource.entry_port)}`,
      })),
    ];
    return items
      .sort((a, b) => new Date(b.createdAt ?? 0).getTime() - new Date(a.createdAt ?? 0).getTime())
      .slice(0, 4);
  }, [activeNodes, activeRoutes, visibleTransitResources]);

  return (
    <section className="line-builder-product wide">
      <div className="builder-product-layout">
        <main className="builder-flow">
          <section className="builder-stage-card">
            <div className="builder-stage-title">
              <span>1</span>
              <div>
                <h3>第一步：准备服务器</h3>
                <p>先把落地服务器或中转服务器接入控制台。</p>
              </div>
            </div>
            <div className="builder-action-grid">
              <BuilderActionCard
                buttonLabel="添加落地服务器"
                detail="用于创建直连节点，也可以作为中转线路的目标。"
                icon="server"
                tone="blue"
                title="添加落地服务器"
                onClick={() => setActiveModal("landing")}
              />
              <BuilderActionCard
                buttonLabel="添加中转服务器"
                detail="用于给客户提供更稳定的入口，再转到落地节点。"
                icon="servers"
                tone="orange"
                title="添加中转服务器"
                onClick={() => setActiveModal("transit")}
              />
            </div>
          </section>

          <section className="builder-stage-card">
            <div className="builder-stage-title">
              <span>2</span>
              <div>
                <h3>第二步：创建线路</h3>
                <p>根据业务用途选择直连或中转，确认端口安全提醒。</p>
              </div>
            </div>
            <div className="builder-action-grid">
              <BuilderActionCard
                buttonLabel="新建直连节点"
                detail="适合看视频、日常使用或客户备用线路。"
                icon="builder"
                tone="green"
                title="新建直连节点"
                onClick={() => setActiveModal("direct")}
              />
              <BuilderActionCard
                buttonLabel="新建中转线路"
                detail="适合直播主线或需要更稳定入口的客户。"
                icon="route"
                tone="purple"
                title="新建中转线路"
                onClick={() => setActiveModal("transitLine")}
              />
            </div>
          </section>
        </main>

        <aside className="builder-aside">
          <section className="product-section-card">
            <div className="product-section-head">
              <h3>准备情况</h3>
              <span className="product-badge info">当前可用</span>
            </div>
            <div className="builder-resource-metrics">
              <ResourceMetric icon="server" label="落地服务器" value={`${onlineLandingServers.length} 台可用`} />
              <ResourceMetric icon="servers" label="中转服务器" value={`${onlineTransitResources.length} 台可用`} />
              <ResourceMetric icon="builder" label="直连节点" value={`${activeNodes.length} 个`} />
              <ResourceMetric icon="route" label="中转线路" value={`${activeRoutes.length} 条`} />
            </div>
          </section>

          <section className="product-section-card">
            <div className="product-section-head">
              <h3>适合我选哪个？</h3>
              <span className="product-badge warning">新手提示</span>
            </div>
            <ul className="product-tip-list">
              <li>看视频 / 日常使用：优先选择新建直连节点。</li>
              <li>客户直播主线：优先选择新建中转线路。</li>
              <li>还没有服务器：先添加落地服务器或中转服务器。</li>
              <li>新增或变更客户连接端口后，请务必检查云安全组、云防火墙、服务器防火墙是否放行。</li>
            </ul>
          </section>

          <section className="product-section-card">
            <div className="product-section-head">
              <h3>最近创建</h3>
              <span className="product-badge muted">{taskName(tasks[0] ?? null)}</span>
            </div>
            {recentCreated.length ? (
              <div className="recent-create-list compact">
                {recentCreated.map((item) => (
                  <div className="recent-create-row" key={`${item.title}-${item.detail}`}>
                    <ProductIcon name="route" tone="blue" />
                    <strong>{item.title}</strong>
                    <span>{item.detail}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty compact-empty">暂无创建记录。</div>
            )}
          </section>
        </aside>
      </div>

      <p className="message">{message}</p>

      {activeModal === "landing" ? <AddLandingServerModal onClose={() => setActiveModal(null)} onCompleted={loadData} /> : null}
      {activeModal === "transit" ? <AddTransitServerModal onClose={() => setActiveModal(null)} onCompleted={loadData} /> : null}
      {activeModal === "direct" ? <CreateDirectNodeModal servers={servers} onClose={() => setActiveModal(null)} onCompleted={loadData} /> : null}
      {activeModal === "transitLine" ? (
        <CreateTransitLineModal nodes={activeNodes} resources={visibleTransitResources} onClose={() => setActiveModal(null)} />
      ) : null}
    </section>
  );
}

function BuilderActionCard({
  buttonLabel,
  detail,
  icon,
  onClick,
  tone,
  title,
}: {
  buttonLabel: string;
  detail: string;
  icon: string;
  onClick: () => void;
  tone: "blue" | "green" | "orange" | "red" | "purple" | "slate";
  title: string;
}) {
  return (
    <article className="builder-action-card">
      <div>
        <ProductIcon name={icon} tone={tone} />
        <strong>{title}</strong>
        <p>{detail}</p>
      </div>
      <button type="button" onClick={onClick}>
        {buttonLabel}
      </button>
    </article>
  );
}

function ResourceMetric({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <div className="builder-resource-metric">
      <ProductIcon name={icon} tone="blue" />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
