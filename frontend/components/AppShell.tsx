"use client";

import { useEffect, useState } from "react";

import { AdvancedDebugPanel } from "@/components/AdvancedDebugPanel";
import { CustomerLinesPanel } from "@/components/CustomerLinesPanel";
import { LineBuilderPanel } from "@/components/LineBuilderPanel";
import { LoginScreen } from "@/components/LoginScreen";
import { ServerResourcesPanel } from "@/components/ServerResourcesPanel";
import { TaskHistoryPanel } from "@/components/TaskHistoryPanel";
import {
  AUTH_EXPIRED_EVENT,
  apiFetch,
  type AuthUser,
  type CsrfResult,
  type HealthData,
  type NodeListResult,
  type TaskListResult,
  type TransitResourceListResult,
  type TransitRouteListResult,
  type VpsServerListResult,
} from "@/lib/api";

type PanelId = "dashboard" | "lineBuilder" | "customerLines" | "serverResources" | "tasks" | "settings" | "advancedDebug";

const panels: Array<{
  id: PanelId;
  label: string;
  title: string;
}> = [
  {
    id: "dashboard",
    label: "总览",
    title: "线路总览",
  },
  {
    id: "lineBuilder",
    label: "线路搭建",
    title: "线路搭建",
  },
  {
    id: "customerLines",
    label: "客户线路",
    title: "客户线路",
  },
  {
    id: "serverResources",
    label: "服务器资源",
    title: "服务器资源",
  },
  {
    id: "tasks",
    label: "任务记录",
    title: "任务记录",
  },
  {
    id: "settings",
    label: "设置",
    title: "设置",
  },
  {
    id: "advancedDebug",
    label: "高级调试",
    title: "高级调试",
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
    <main className="page">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark">LC</div>
          <div>
            <div className="brand">LiveLine Console</div>
            <div className="stage">本地运维控制台</div>
          </div>
        </div>
        <nav className="nav">
          {panels.map((panel) => (
            <button
              aria-current={activePanel === panel.id ? "page" : undefined}
              className={`nav-item${activePanel === panel.id ? " active" : ""}${panel.id === "advancedDebug" ? " subdued" : ""}`}
              key={panel.id}
              type="button"
              onClick={() => setActivePanel(panel.id)}
            >
              {panel.label}
            </button>
          ))}
        </nav>
      </aside>

      <section className="main">
        <header className="topbar">
          <div>
            <h1>{activePanelMeta.title}</h1>
          </div>
          <div className="topbar-actions">
            <span className="admin-badge">已登录：{currentAdmin.username}</span>
            <button className="ghost-button" type="button" onClick={handleLogout}>
              退出登录
            </button>
          </div>
        </header>

        <div className="grid">
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

function displayDashboardStatus(status: string | null | undefined) {
  const labels: Record<string, string> = {
    active: "可用",
    online: "在线",
    stale: "心跳过期 / 离线",
    worker_online: "助手在线",
    pending_worker: "等待助手",
    disabled: "已停用",
    failed: "失败",
    deleted: "已删除",
  };
  return status ? labels[status] ?? status : "未返回";
}

function entryWithPort(host: string | null | undefined, port: number | null | undefined) {
  if (!host) {
    return "未返回";
  }
  return port ? `${host}:${port}` : host;
}

function DashboardPanel({ onNavigate }: { onNavigate: (panel: PanelId) => void }) {
  const [summary, setSummary] = useState({
    landingServers: "-",
    landingStatus: "读取中",
    landingDetail: "正在读取落地服务器。",
    directNode: "读取中",
    directNodeDetail: "正在读取直连节点。",
    directNodeEntry: "未返回",
    directNodeConfig: "未返回",
    transitServers: "-",
    transitHelperStatus: "读取中",
    transitHelperDetail: "正在读取中转助手。",
    transitRoute: "读取中",
    transitRouteEntry: "未返回",
    transitRouteTarget: "未返回",
    transitRouteDetail: "正在读取中转链路。",
    health: "读取中",
    recentTask: "无任务",
    noticeItems: ["正在读取本地网络搭建状态。"],
  });
  const [message, setMessage] = useState("正在读取本地总览。");

  async function loadDashboard() {
    const [healthResult, vpsResult, nodeResult, resourceResult, routeResult, taskResult] = await Promise.all([
      apiFetch<HealthData>("/api/health"),
      apiFetch<VpsServerListResult>("/api/vps"),
      apiFetch<NodeListResult>("/api/nodes"),
      apiFetch<TransitResourceListResult>("/api/transit-resources"),
      apiFetch<TransitRouteListResult>("/api/transit-routes"),
      apiFetch<TaskListResult>("/api/tasks?limit=8"),
    ]);

    const landingServers = vpsResult.success ? vpsResult.data.servers : [];
    const nodes = nodeResult.success ? nodeResult.data.nodes : [];
    const transitResources = resourceResult.success ? resourceResult.data.resources : [];
    const routes = routeResult.success ? routeResult.data.routes : [];
    const tasks = taskResult.success ? taskResult.data.tasks : [];
    const healthOk =
      healthResult.success &&
      Object.values(healthResult.data).every((component) => component.status === "ok");
    const latestTask = tasks[0];
    const activeNodes = nodes.filter((node) => node.status === "active");
    const primaryNode = activeNodes[0] ?? nodes[0] ?? null;
    const primaryNodeHasShareLink = Boolean(
      primaryNode?.has_share_link ?? primaryNode?.share_link_present ?? primaryNode?.masked_share_link,
    );
    const transitServers = transitResources.filter((resource) => resource.resource_type === "server" && !resource.deleted_at);
    const onlineTransitServers = transitServers.filter(
      (resource) => resource.worker_online || resource.display_status === "online" || resource.display_status === "worker_online",
    );
    const primaryTransitServer = onlineTransitServers[0] ?? transitServers[0] ?? null;
    const activeRoutes = routes.filter((route) => route.status === "active" && !route.deleted_at);
    const primaryRoute = activeRoutes[0] ?? routes[0] ?? null;
    const routeTransitResource = primaryRoute
      ? transitResources.find((resource) => resource.id === primaryRoute.transit_resource_id)
      : null;
    const routeShareLinkWritten = routes.some((route) => Boolean(route.share_link));
    const noticeItems: string[] = [];

    if (!landingServers.length) {
      noticeItems.push("还没有落地服务器记录。");
    }
    if (!primaryNode) {
      noticeItems.push("还没有直连节点。");
    }
    if (!onlineTransitServers.length) {
      noticeItems.push("没有在线的中转助手。");
    }
    if (!activeRoutes.length) {
      noticeItems.push("还没有 active 中转链路。");
    }
    if (!healthOk) {
      noticeItems.push("本地 backend / database / redis / worker 健康状态需要检查。");
    }
    if (routeShareLinkWritten) {
      noticeItems.push("检测到中转线路已有保存的客户端链接，请确认是否符合当前使用预期。");
    }
    if (!noticeItems.length) {
      noticeItems.push("当前网络搭建摘要正常；如需继续，优先做长稳观察或按需复制测试配置。");
    }

    setSummary({
      landingServers: `${landingServers.length} 台`,
      landingStatus: landingServers.length ? "已接入" : "未接入",
      landingDetail: landingServers.length
        ? `服务器助手在线 ${landingServers.filter((server) => server.worker_online).length} 台；用于直连节点和中转目标。`
        : "请先添加落地服务器。",
      directNode: primaryNode ? "已创建" : "未创建",
      directNodeDetail: primaryNode
        ? `${primaryNode.node_name} / ${displayDashboardStatus(primaryNode.status)}`
        : "暂无直连直播节点。",
      directNodeEntry: primaryNode ? entryWithPort(primaryNode.vps_ip, primaryNode.port) : "未返回",
      directNodeConfig: primaryNodeHasShareLink ? "可导出配置" : "未生成配置",
      transitServers: `${transitServers.length} 台`,
      transitHelperStatus: onlineTransitServers.length ? "在线" : "离线 / 未接入",
      transitHelperDetail: primaryTransitServer
        ? `${primaryTransitServer.name} / ${primaryTransitServer.worker_version ?? "版本未返回"}`
        : "暂无中转服务器。",
      transitRoute: primaryRoute ? displayDashboardStatus(primaryRoute.status) : "未创建",
      transitRouteEntry: primaryRoute ? entryWithPort(routeTransitResource?.entry_host, primaryRoute.listen_port) : "未返回",
      transitRouteTarget: primaryRoute ? entryWithPort(primaryRoute.target_host, primaryRoute.target_port) : "未返回",
      transitRouteDetail: primaryRoute
        ? `${primaryRoute.name} / ${displayForwardingMethod(primaryRoute.forwarding_method)}`
        : "暂无可用中转线路。",
      health: healthOk ? "正常" : "需检查",
      recentTask: latestTask ? `${latestTask.task_type} / ${taskStatusLabel(latestTask.status)}` : "无任务",
      noticeItems,
    });
    setMessage("总览已刷新。");
  }

  useEffect(() => {
    void loadDashboard();
  }, []);

  return (
    <section className="dashboard-panel wide">
      <div className="dashboard-hero">
        <div>
          <h2>搭建网络状态总览</h2>
        </div>
        <button className="secondary" type="button" onClick={() => void loadDashboard()}>
          刷新总览
        </button>
      </div>

      <div className="overview-status-grid" aria-label="网络搭建核心状态">
        <OverviewStatusCard
          detail={summary.landingDetail}
          label="落地服务器"
          status={summary.landingStatus}
          tone={summary.landingStatus === "已接入" ? "success" : "warning"}
          value={summary.landingServers}
        />
        <OverviewStatusCard
          detail={`${summary.directNodeEntry} / ${summary.directNodeConfig}`}
          label="直连节点"
          status={summary.directNodeConfig}
          tone={summary.directNode === "已创建" ? "success" : "warning"}
          value={summary.directNode}
        />
        <OverviewStatusCard
          detail={summary.transitHelperDetail}
          label="中转服务器"
          status={summary.transitHelperStatus}
          tone={summary.transitHelperStatus === "在线" ? "success" : "warning"}
          value={summary.transitServers}
        />
        <OverviewStatusCard
          detail={`${summary.transitRouteEntry} -> ${summary.transitRouteTarget}`}
          label="中转链路"
          status={summary.transitRoute}
          tone={summary.transitRoute === "active" ? "success" : "warning"}
          value={summary.transitRoute}
        />
      </div>

      <div className="overview-panels">
        <section className="panel overview-section">
          <div className="status-row">
            <div>
              <h2>当前可用链路</h2>
            </div>
          </div>
          <div className="overview-link-grid">
            <div className="overview-link-card">
              <span>直连节点</span>
              <strong>{summary.directNodeEntry}</strong>
              <small>状态：{summary.directNodeConfig}；用于保留原直连入口。</small>
            </div>
            <div className="overview-link-card">
              <span>中转链路</span>
              <strong>
                {summary.transitRouteEntry} -&gt; {summary.transitRouteTarget}
              </strong>
              <small>状态：{summary.transitRouteDetail}；用于手动导入客户端测试。</small>
            </div>
          </div>
        </section>

        <section className="panel overview-section">
          <div className="status-row">
            <div>
              <h2>需要注意</h2>
              <p className="message">{message}</p>
            </div>
            <span className={`pill ${summary.health === "正常" ? "ok" : "warn"}`}>本地健康：{summary.health}</span>
          </div>
          <ul className="overview-notice-list">
            {summary.noticeItems.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p className="message">最近任务：{summary.recentTask}</p>
        </section>

        <section className="panel overview-section">
          <div className="status-row">
            <div>
              <h2>下一步</h2>
            </div>
          </div>
          <div className="overview-next-actions">
            <button className="secondary" type="button" onClick={() => onNavigate("serverResources")}>
              去服务器资源
            </button>
            <button className="secondary" type="button" onClick={() => onNavigate("lineBuilder")}>
              去线路搭建
            </button>
            <button className="secondary" type="button" onClick={() => onNavigate("customerLines")}>
              去客户线路
            </button>
          </div>
        </section>
      </div>
    </section>
  );
}

function OverviewStatusCard({
  detail,
  label,
  status,
  tone,
  value,
}: {
  detail: string;
  label: string;
  status: string;
  tone: "success" | "warning" | "danger" | "muted" | "info";
  value: string;
}) {
  return (
    <div className={`overview-status-card ${tone}`}>
      <div className="overview-card-header">
        <span>{label}</span>
        <small>{status}</small>
      </div>
      <strong>{value}</strong>
      <p>{detail}</p>
    </div>
  );
}

function displayForwardingMethod(method: string | null | undefined) {
  const labels: Record<string, string> = {
    haproxy_tcp: "稳定转发服务",
    haproxy: "稳定转发服务",
    socat: "稳定转发服务",
    gost: "稳定转发服务",
  };
  return method ? labels[method] ?? "转发服务" : "未返回";
}

function SettingsPanel() {
  return (
    <section className="panel wide settings-panel">
      <div className="status-row">
        <div>
          <h2>本地控制台设置与安全基线</h2>
        </div>
      </div>
      <div className="settings-grid">
        <div className="settings-card">
          <strong>登录安全</strong>
          <span>登录门禁、API 保护、登录失败限流和生产环境 guardrails 已归档。</span>
        </div>
        <div className="settings-card">
          <strong>本地备份</strong>
          <span>升级前先运行本地数据库备份；真实备份文件不得进入 Git。</span>
        </div>
        <div className="settings-card">
          <strong>链路规则</strong>
          <span>新增或变更端口前必须检查云服务器安全组 / 云防火墙 / 服务器防火墙。</span>
        </div>
        <div className="settings-card">
          <strong>正式线路变更</strong>
          <span>正式线路变更必须单独审批；客户端链接不会在普通页面被自动覆盖。</span>
        </div>
      </div>
    </section>
  );
}
