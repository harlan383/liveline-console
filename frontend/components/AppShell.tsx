"use client";

import { useEffect, useMemo, useState } from "react";

import { AdvancedDebugPanel } from "@/components/AdvancedDebugPanel";
import { CustomerLinesPanel } from "@/components/CustomerLinesPanel";
import { LineBuilderPanel } from "@/components/LineBuilderPanel";
import { LoginScreen } from "@/components/LoginScreen";
import { ProductIcon } from "@/components/ProductIcons";
import { ServerResourcesPanel } from "@/components/ServerResourcesPanel";
import { TaskHistoryPanel } from "@/components/TaskHistoryPanel";
import {
  AUTH_EXPIRED_EVENT,
  apiFetch,
  type AuthUser,
  type CsrfResult,
  type HealthData,
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

type PanelId = "dashboard" | "lineBuilder" | "customerLines" | "serverResources" | "tasks" | "settings" | "advancedDebug";

const panels: Array<{
  id: PanelId;
  icon: string;
  tone: "blue" | "green" | "orange" | "red" | "purple" | "slate";
  label: string;
  title: string;
  subtitle: string;
}> = [
  {
    id: "dashboard",
    icon: "dashboard",
    tone: "blue",
    label: "总览",
    title: "总览",
    subtitle: "查看线路、服务器和待处理事项。",
  },
  {
    id: "lineBuilder",
    icon: "builder",
    tone: "green",
    label: "线路搭建",
    title: "线路搭建",
    subtitle: "按步骤准备服务器并规划直连或中转线路。",
  },
  {
    id: "customerLines",
    icon: "lines",
    tone: "purple",
    label: "我的线路",
    title: "我的线路",
    subtitle: "按客户、平台和用途查看当前线路。",
  },
  {
    id: "serverResources",
    icon: "servers",
    tone: "orange",
    label: "服务器资源",
    title: "服务器资源",
    subtitle: "管理落地服务器、自建中转和商家入口。",
  },
  {
    id: "tasks",
    icon: "tasks",
    tone: "green",
    label: "任务记录",
    title: "任务记录",
    subtitle: "查看创建、删除、检测等操作结果。",
  },
  {
    id: "settings",
    icon: "settings",
    tone: "slate",
    label: "设置",
    title: "设置",
    subtitle: "配置默认创建偏好和提醒方式。",
  },
  {
    id: "advancedDebug",
    icon: "debug",
    tone: "red",
    label: "高级调试",
    title: "高级调试",
    subtitle: "仅技术支持使用。",
  },
];

function taskStatusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: "等待中",
    running: "执行中",
    success: "成功",
    completed: "成功",
    failed: "失败",
    cancelled: "已取消",
    timeout: "超时",
    unknown: "未知",
  };
  return labels[status] ?? status;
}

function statusTone(status: string | null | undefined) {
  if (status === "active" || status === "success" || status === "completed" || status === "online" || status === "worker_online") {
    return "ok";
  }
  if (status === "failed" || status === "deleted" || status === "timeout") {
    return "bad";
  }
  return "warn";
}

function formatDate(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString();
}

function entryWithPort(host: string | null | undefined, port: number | null | undefined) {
  if (!host) {
    return "未返回";
  }
  return port ? `${host}:${port}` : host;
}

export function AppShell() {
  const [activePanel, setActivePanel] = useState<PanelId>("dashboard");
  const [currentAdmin, setCurrentAdmin] = useState<AuthUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [authMessage, setAuthMessage] = useState("");
  const activePanelMeta = panels.find((panel) => panel.id === activePanel) ?? panels[0];

  useEffect(() => {
    async function checkAuth() {
      const result = await apiFetch<AuthUser>("/api/auth/me");
      if (result.success) {
        setCurrentAdmin(result.data);
        setAuthMessage("");
      } else {
        setCurrentAdmin(null);
        setAuthMessage("");
      }
      setAuthChecked(true);
    }

    void checkAuth();
  }, []);

  useEffect(() => {
    function handleAuthExpired() {
      setCurrentAdmin(null);
      setAuthMessage("登录状态已过期，请重新登录。");
    }

    window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
  }, []);

  async function handleLogout() {
    const csrfResult = await apiFetch<CsrfResult>("/api/auth/csrf");
    if (csrfResult.success) {
      await apiFetch("/api/auth/logout", {
        method: "POST",
        headers: {
          "X-CSRF-Token": csrfResult.data.csrf_token,
        },
      });
    }

    setCurrentAdmin(null);
    setAuthMessage("已退出登录。");
  }

  if (!authChecked) {
    return (
      <main className="login-page">
        <section className="login-card" aria-label="登录状态检查">
          <div className="login-brand">
            <span className="login-kicker">LiveLine Console</span>
            <h1>正在检查登录状态</h1>
            <p>请稍候。</p>
          </div>
        </section>
      </main>
    );
  }

  if (!currentAdmin) {
    return <LoginScreen initialMessage={authMessage} onLogin={setCurrentAdmin} />;
  }

  return (
    <main className="page product-console">
      <aside className="sidebar product-sidebar">
        <div className="brand-lockup product-brand">
          <div className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" fill="none">
              <path d="M9.2 20.7 5 16.4 16.4 5l4.3 4.2-7.1 7.2 2.8 2.8 7.1-7.1 4.2 4.3L16.4 27.8l-7.2-7.1Z" />
              <path d="m22.8 11.3 4.2 4.3L15.6 27 11.3 22.8l7.1-7.2-2.8-2.8-7.1 7.1-4.2-4.3L15.6 4.2l7.2 7.1Z" opacity=".72" />
            </svg>
          </div>
          <div>
            <div className="brand">LiveLine Console</div>
          </div>
        </div>
        <nav className="nav product-nav">
          {panels.map((panel) => (
            <button
              aria-current={activePanel === panel.id ? "page" : undefined}
              className={`nav-item product-nav-item${activePanel === panel.id ? " active" : ""}${panel.id === "advancedDebug" ? " subdued" : ""}`}
              key={panel.id}
              type="button"
              onClick={() => setActivePanel(panel.id)}
            >
              <ProductIcon className="nav-icon" name={panel.icon} tone={panel.tone} />
              <span>{panel.label}</span>
            </button>
          ))}
        </nav>
        <button className="sidebar-health-card" type="button" onClick={() => setActivePanel("advancedDebug")}>
          <span className="health-dot" />
          <span>
            <strong>系统运行正常</strong>
            <small>最近更新：5分钟前</small>
          </span>
          <ProductIcon name="arrow" tone="slate" />
        </button>
      </aside>

      <section className="main product-main">
        <header className="topbar product-topbar">
          <div>
            <h1>{activePanelMeta.title}</h1>
          </div>
          <div className="topbar-actions product-topbar-actions">
            <button className="topbar-tool" aria-label="通知" type="button">
              <ProductIcon name="bell" tone="slate" />
              <span className="notification-dot" aria-hidden="true" />
            </button>
            <button className="topbar-tool" aria-label="帮助" type="button">
              <ProductIcon name="help" tone="slate" />
            </button>
            <span className="product-avatar" aria-hidden="true">
              张
            </span>
            <span className="admin-badge">{currentAdmin.username}</span>
            <span className="topbar-caret" aria-hidden="true">⌄</span>
            <button className="ghost-button" type="button" onClick={handleLogout}>
              退出
            </button>
          </div>
        </header>

        <div className="grid product-grid">
          {activePanel === "dashboard" ? <DashboardPanel onNavigate={setActivePanel} /> : null}
          {activePanel === "lineBuilder" ? <LineBuilderPanel /> : null}
          {activePanel === "customerLines" ? <CustomerLinesPanel /> : null}
          {activePanel === "serverResources" ? <ServerResourcesPanel /> : null}
          {activePanel === "tasks" ? <TaskHistoryPanel /> : null}
          {activePanel === "settings" ? <SettingsPanel /> : null}
          {activePanel === "advancedDebug" ? <AdvancedDebugPanel /> : null}
        </div>
      </section>
    </main>
  );
}

function latestCreatedLabel(items: Array<{ created_at: string | null; name: string; type: string }>) {
  const sorted = [...items].sort((a, b) => new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime());
  return sorted.slice(0, 3);
}

function DashboardPanel({ onNavigate }: { onNavigate: (panel: PanelId) => void }) {
  const [servers, setServers] = useState<VpsServerData[]>([]);
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [routes, setRoutes] = useState<TransitRouteData[]>([]);
  const [tasks, setTasks] = useState<TaskData[]>([]);
  const [healthOk, setHealthOk] = useState(false);
  const [message, setMessage] = useState("正在读取运营看板。");

  async function loadDashboard() {
    const [healthResult, vpsResult, nodeResult, resourceResult, routeResult, taskResult] = await Promise.all([
      apiFetch<HealthData>("/api/health"),
      apiFetch<VpsServerListResult>("/api/vps"),
      apiFetch<NodeListResult>("/api/nodes"),
      apiFetch<TransitResourceListResult>("/api/transit-resources"),
      apiFetch<TransitRouteListResult>("/api/transit-routes"),
      apiFetch<TaskListResult>("/api/tasks?limit=8"),
    ]);

    if (vpsResult.success) {
      setServers(vpsResult.data.servers);
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
    setHealthOk(
      healthResult.success &&
        Object.values(healthResult.data).every((component) => component.status === "ok"),
    );
    setMessage(
      [healthResult, vpsResult, nodeResult, resourceResult, routeResult, taskResult].every((result) => result.success)
        ? "运营看板已刷新。"
        : "部分看板数据暂时无法读取。",
    );
  }

  useEffect(() => {
    void loadDashboard();
  }, []);

  const activeNodes = nodes.filter((node) => node.status === "active");
  const activeRoutes = routes.filter((route) => route.status === "active" && !route.deleted_at);
  const failedTasks = tasks.filter((task) => task.status === "failed" || task.status === "timeout");
  const runningTasks = tasks.filter((task) => task.status === "pending" || task.status === "running");
  const staleResources = resources.filter((resource) => resource.worker_heartbeat_status === "stale" || resource.worker_is_heartbeat_stale);
  const normalLines = activeNodes.length + activeRoutes.length;
  const riskLines = staleResources.length + routes.filter((route) => route.status === "creating").length;
  const abnormalLines = failedTasks.length + routes.filter((route) => route.status === "failed").length;
  const pendingItems = runningTasks.length + (servers.length ? 0 : 1) + (activeNodes.length ? 0 : 1);
  const recentCreated = latestCreatedLabel([
    ...activeNodes.map((node) => ({ created_at: node.created_at, name: node.node_name, type: "直连节点" })),
    ...resources.filter((resource) => !resource.deleted_at).map((resource) => ({
      created_at: resource.created_at,
      name: resource.name,
      type: resource.resource_type === "server" ? "中转服务器" : "商家中转入口",
    })),
    ...activeRoutes.map((route) => ({ created_at: route.created_at, name: route.name, type: "中转线路" })),
  ]);
  const attentionItems = useMemo(() => {
    const items: Array<{ summary: string; time: string; tone: "warning" | "danger" | "success" }> = [];
    if (staleResources.length) {
      items.push({
        summary: `${staleResources[0].name}：服务器状态长时间未更新，建议检查服务器是否正常运行`,
        time: "10:15",
        tone: "warning",
      });
    }
    if (failedTasks.length) {
      items.push({
        summary: `${businessTaskTitle(failedTasks[0].task_type)}：最近一次操作失败，建议到任务记录查看处理建议`,
        time: "09:42",
        tone: "danger",
      });
    }
    if (!activeRoutes.length) {
      items.push({
        summary: "客户B - TikTok新加坡线：中转端口未通过检测，建议检查端口放行",
        time: "09:42",
        tone: "warning",
      });
    }
    if (!activeNodes.length) {
      items.push({
        summary: "客户A - Facebook越南主线：还没有可用直连节点，建议先添加落地服务器",
        time: "10:15",
        tone: "warning",
      });
    }
    if (!items.length) {
      items.push({
        summary: "当前线路整体正常：没有需要立即处理的问题，建议定期查看任务记录",
        time: "刚刚",
        tone: "success",
      });
    }
    return items.slice(0, 2);
  }, [activeNodes.length, activeRoutes.length, failedTasks, staleResources]);

  const nextStepTips = useMemo(() => {
    const tips: string[] = [];
    if (servers.length > 0 && !activeNodes.length) {
      tips.push("你已接入落地服务器，可以继续创建第一条直连节点。");
    }
    if (!resources.some((resource) => resource.resource_type === "server" && !resource.deleted_at)) {
      tips.push("如果要搭建中转线路，请先添加一台中转服务器。");
    }
    if (activeNodes.length > 0 && !activeRoutes.length) {
      tips.push("已有直连节点，客户直播主线可以继续规划中转线路。");
    }
    return tips.length ? tips : ["当前基础资源已就绪，可以在“我的线路”查看客户线路状态。"];
  }, [activeNodes.length, activeRoutes.length, resources, servers.length]);

  return (
    <section className="dashboard-panel product-dashboard wide">
      <div className="product-stat-grid four">
        <DashboardStat icon="shield" title="正常线路" value={`${normalLines}`} detail="当前可正常使用" tone="success" />
        <DashboardStat icon="alert" title="风险线路" value={`${riskLines}`} detail="建议尽快检查" tone="warning" />
        <DashboardStat icon="alert" title="异常线路" value={`${abnormalLines}`} detail="需要处理" tone="danger" />
        <DashboardStat icon="clock" title="待处理" value={`${pendingItems}`} detail={healthOk ? "暂无紧急待办" : "有待办事项"} tone="info" />
      </div>

      <div className="product-dashboard-layout">
        <section className="product-section-card attention-card">
          <div className="product-section-head">
            <h3><ProductIcon name="bell" tone="red" />今日需要关注</h3>
            <span className={`product-badge ${abnormalLines ? "danger" : riskLines ? "warning" : "success"}`}>
              {abnormalLines ? "异常" : riskLines ? "风险" : "正常"}
            </span>
          </div>
          <div className="attention-list">
            {attentionItems.map((item) => (
              <button className={`attention-item ${item.tone}`} key={`${item.summary}-${item.time}`} type="button" onClick={() => onNavigate("tasks")}>
                <ProductIcon name="alert" tone={item.tone === "danger" ? "red" : item.tone === "success" ? "green" : "orange"} />
                <div className="attention-copy">
                  <strong>{item.summary}</strong>
                  <small>发现时间：{item.time}</small>
                </div>
                <ProductIcon name="arrow" tone="slate" />
              </button>
            ))}
          </div>
        </section>

        <section className="product-section-card quick-actions-card">
          <div className="product-section-head">
            <h3><ProductIcon name="action" tone="blue" />常用操作</h3>
            <span className="product-badge info">快捷入口</span>
          </div>
          <div className="quick-action-grid">
            <button type="button" onClick={() => onNavigate("serverResources")}>
              <ProductIcon name="server" tone="blue" />
              <span>
                <strong>添加落地服务器</strong>
                <small>接入客户出口节点</small>
              </span>
            </button>
            <button type="button" onClick={() => onNavigate("serverResources")}>
              <ProductIcon name="servers" tone="green" />
              <span>
                <strong>添加中转服务器</strong>
                <small>准备自建中转入口</small>
              </span>
            </button>
            <button type="button" onClick={() => onNavigate("lineBuilder")}>
              <ProductIcon name="builder" tone="purple" />
              <span>
                <strong>新建直连节点</strong>
                <small>规划客户直连线路</small>
              </span>
            </button>
            <button type="button" onClick={() => onNavigate("lineBuilder")}>
              <ProductIcon name="lines" tone="orange" />
              <span>
                <strong>新建中转线路</strong>
                <small>规划中转访问路径</small>
              </span>
            </button>
          </div>
        </section>

        <section className="product-section-card">
          <div className="product-section-head">
            <h3><ProductIcon name="document" tone="slate" />最近创建</h3>
            <span className="product-badge muted">最新 3 条</span>
          </div>
          {recentCreated.length ? (
            <div className="recent-create-list">
              {recentCreated.map((item) => (
                <div className="recent-create-row" key={`${item.type}-${item.name}`}>
                  <ProductIcon name={item.type === "直连节点" ? "builder" : "route"} tone="blue" />
                  <strong>{item.name}</strong>
                  <span>{item.type}</span>
                  <small>创建人：admin</small>
                  <small>{formatDate(item.created_at)}</small>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty compact-empty">暂无创建记录。</div>
          )}
        </section>

        <section className="product-section-card">
          <div className="product-section-head">
            <h3><ProductIcon name="bulb" tone="orange" />使用提示</h3>
            <span className="product-badge info">帮助</span>
          </div>
          <ul className="product-tip-list">
            <li>通过“线路搭建”快速创建直连或中转线路。</li>
            <li>在“我的线路”中查看线路状态与质量。</li>
            <li>遇到问题时，先查看“任务记录”获取检测结果。</li>
            <li>如需帮助，可点击右上角“帮助”查看说明。</li>
            {nextStepTips.map((tip) => (
              <li key={tip}>{tip}</li>
            ))}
          </ul>
        </section>
      </div>
      <p className="message subtle-message">{message}</p>
    </section>
  );
}

function businessTaskTitle(taskType: string) {
  const labels: Record<string, string> = {
    landing_node_create: "创建直连节点",
    transit_route_create: "创建中转线路",
    cleanup_landing_node: "删除节点",
    cleanup_landing_server: "清理落地服务器",
    cleanup_transit_route: "清理中转线路",
    cleanup_transit_resource: "清理中转服务器",
  };
  return labels[taskType] ?? "系统操作";
}

function DashboardStat({
  detail,
  icon,
  title,
  tone,
  value,
}: {
  detail: string;
  icon: string;
  title: string;
  tone: "success" | "warning" | "danger" | "info";
  value: string;
}) {
  return (
    <article className={`product-stat-card ${tone}`}>
      <ProductIcon name={icon} tone={tone === "success" ? "green" : tone === "warning" ? "orange" : tone === "danger" ? "red" : "blue"} />
      <div>
        <span>{title}</span>
        <strong>{value}</strong>
      </div>
      <p>{detail}</p>
      <small className="stat-footnote"><span />点击对应模块查看详情</small>
    </article>
  );
}

function SettingsPanel() {
  const [activeSetting, setActiveSetting] = useState("默认创建配置");
  const [platform, setPlatform] = useState("Facebook");
  const [region, setRegion] = useState("香港");
  const [portRange, setPortRange] = useState("28000-39999");
  const [message, setMessage] = useState("设置只保存在当前浏览器会话中。");

  return (
    <section className="settings-product wide">
      <div className="settings-product-layout">
        <aside className="settings-menu">
          {["默认创建配置", "提醒设置", "界面设置"].map((item) => (
            <button className={activeSetting === item ? "active" : ""} key={item} type="button" onClick={() => setActiveSetting(item)}>
              {item}
            </button>
          ))}
        </aside>
        <section className="product-section-card settings-form-card">
          <h3>{activeSetting}</h3>
          <div className="settings-form-grid">
            <label>
              默认直播平台
              <small>创建线路时优先选择的平台。</small>
              <select value={platform} onChange={(event) => setPlatform(event.target.value)}>
                <option>Facebook</option>
                <option>TikTok</option>
                <option>YouTube</option>
                <option>日常使用</option>
              </select>
            </label>
            <label>
              默认落地地区
              <small>用于自动推荐服务器地区。</small>
              <select value={region} onChange={(event) => setRegion(event.target.value)}>
                <option>香港</option>
                <option>新加坡</option>
                <option>越南</option>
                <option>美国</option>
              </select>
            </label>
            <label>
              默认创建端口范围
              <small>创建线路时优先推荐的客户连接端口。</small>
              <input value={portRange} onChange={(event) => setPortRange(event.target.value)} />
            </label>
            <label className="settings-check product-switch">
              <input defaultChecked type="checkbox" />
              <span />
              <strong>默认开启端口放行提醒</strong>
              <small>创建线路时提醒你检查端口是否已开放。</small>
            </label>
            <label className="settings-check product-switch">
              <input type="checkbox" />
              <span />
              <strong>默认显示高级设置</strong>
              <small>关闭后，界面会更简洁，更适合新手。</small>
            </label>
            <label className="settings-check product-switch">
              <input defaultChecked type="checkbox" />
              <span />
              <strong>创建完成后自动显示客户端链接</strong>
              <small>方便快速复制给客户。</small>
            </label>
          </div>

          <h3>提醒设置</h3>
          <div className="settings-toggle-list">
            <label className="product-switch">
              <input defaultChecked type="checkbox" />
              <span />
              端口未放行提醒
            </label>
            <label className="product-switch">
              <input defaultChecked type="checkbox" />
              <span />
              服务器离线提醒
            </label>
            <label className="product-switch">
              <input defaultChecked type="checkbox" />
              <span />
              创建失败提醒
            </label>
          </div>
          <div className="settings-action-row">
            <button className="secondary" type="button" onClick={() => setMessage("已恢复为页面默认展示。")}>
              恢复默认
            </button>
            <button className="settings-save-button" type="button" onClick={() => setMessage("设置已在当前页面临时保存。")}>
              保存设置
            </button>
          </div>
          <p className="message">{message}</p>
        </section>
      </div>
    </section>
  );
}
