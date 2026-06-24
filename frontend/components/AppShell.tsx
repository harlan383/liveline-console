"use client";

import { useEffect, useState } from "react";

import { LoginScreen } from "@/components/LoginScreen";
import { RouteSafetyGuardrails } from "@/components/RouteSafetyGuardrails";
import { ServerManagementPanel } from "@/components/ServerManagementPanel";
import { SystemStatus } from "@/components/SystemStatus";
import { TaskHistoryPanel } from "@/components/TaskHistoryPanel";
import { TransitRoutesPanel, TransitServersPanel } from "@/components/TransitRoutesPanel";
import { TransitTopologyPreviewPanel } from "@/components/TransitTopologyPreviewPanel";
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

type PanelId = "dashboard" | "transitRoutes" | "servers" | "transitLinks" | "tasks" | "diagnostics" | "settings";

const panels: Array<{
  id: PanelId;
  label: string;
  title: string;
  description: string;
  eyebrow: string;
}> = [
  {
    id: "dashboard",
    label: "总览",
    title: "搭建网络总览",
    eyebrow: "本地控制台",
    description: "查看落地、直连节点、中转 Worker、中转链路和安全边界状态。",
  },
  {
    id: "transitRoutes",
    label: "中转服务器",
    title: "中转服务器",
    eyebrow: "中转资源",
    description: "管理中转 VPS 资源；资源记录不等于真实线路，转发关系请到“中转链路”页面配置。",
  },
  {
    id: "servers",
    label: "落地服务器",
    title: "落地服务器",
    eyebrow: "VPS 与节点",
    description: "管理落地服务器记录和下级节点；节点链接只按需查看或复制。",
  },
  {
    id: "transitLinks",
    label: "中转链路",
    title: "中转链路",
    eyebrow: "转发关系",
    description: "配置中转服务器到落地节点的转发关系；本地规划不等于远程执行或正式 cutover。",
  },
  {
    id: "tasks",
    label: "任务中心",
    title: "任务中心",
    eyebrow: "执行记录",
    description: "查看任务状态、进度、失败摘要和脱敏后的任务结果。",
  },
  {
    id: "diagnostics",
    label: "诊断工具",
    title: "诊断工具",
    eyebrow: "预览与健康检查",
    description: "查看本地 health、拓扑预览和诊断边界；不连接远端。",
  },
  {
    id: "settings",
    label: "设置",
    title: "设置",
    eyebrow: "本地安全基线",
    description: "查看本地长期使用边界、正式链路保护和后续阶段规则。",
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
  const activePanelMeta = panels.find((panel) => panel.id === activePanel) ?? panels[1];

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
        <div className="sidebar-status">
          <span>中转候选</span>
          <strong>socat 23843</strong>
          <span>直连节点</span>
          <strong>保留</strong>
        </div>
        <nav className="nav">
          {panels.map((panel) => (
            <button
              aria-current={activePanel === panel.id ? "page" : undefined}
              className={`nav-item${activePanel === panel.id ? " active" : ""}`}
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
            <span className="page-eyebrow">{activePanelMeta.eyebrow}</span>
            <h1>{activePanelMeta.title}</h1>
            <p>{activePanelMeta.description}</p>
          </div>
          <div className="topbar-actions">
            <div className="topbar-status" aria-label="当前链路状态">
              <span className="ops-badge success">中转候选 socat 23843</span>
              <span className="ops-badge warning">直连节点保留</span>
              <span className="ops-badge muted">未 cutover</span>
            </div>
            <span className="admin-badge">已登录：{currentAdmin.username}</span>
            <button className="ghost-button" type="button" onClick={handleLogout}>
              退出登录
            </button>
          </div>
        </header>

        <RouteSafetyGuardrails />

        <div className="grid">
          {activePanel === "dashboard" ? <DashboardPanel onNavigate={setActivePanel} /> : null}
          {activePanel === "servers" ? <ServerManagementPanel /> : null}
          {activePanel === "transitRoutes" ? <TransitServersPanel /> : null}
          {activePanel === "transitLinks" ? <TransitRoutesPanel /> : null}
          {activePanel === "tasks" ? <TaskHistoryPanel /> : null}
          {activePanel === "diagnostics" ? (
            <>
              <SystemStatus />
              <TransitTopologyPreviewPanel />
            </>
          ) : null}
          {activePanel === "settings" ? <SettingsPanel /> : null}
        </div>
      </section>
    </main>
  );
}

function displayDashboardStatus(status: string | null | undefined) {
  const labels: Record<string, string> = {
    active: "active",
    online: "在线",
    stale: "心跳过期 / 离线",
    worker_online: "Worker 在线",
    pending_worker: "等待 Worker",
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
    transitWorkerStatus: "读取中",
    transitWorkerDetail: "正在读取中转 Worker。",
    transitRoute: "读取中",
    transitRouteEntry: "未返回",
    transitRouteTarget: "未返回",
    transitRouteDetail: "正在读取中转链路。",
    health: "读取中",
    recentTask: "无任务",
    safetyNodeShareLink: "未被中转流程改写",
    safetyRouteShareLink: "未写入",
    safetyCutover: "未切换",
    safetyOriginalNode: "保留",
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
      noticeItems.push("没有在线的中转 Worker。");
    }
    if (!activeRoutes.length) {
      noticeItems.push("还没有 active 中转链路。");
    }
    if (!healthOk) {
      noticeItems.push("本地 backend / database / redis / worker 健康状态需要检查。");
    }
    if (routeShareLinkWritten) {
      noticeItems.push("检测到 transit_routes.share_link 已写入，请确认是否符合当前阶段边界。");
    }
    if (!noticeItems.length) {
      noticeItems.push("当前网络搭建摘要正常；如需继续，优先做长稳观察或按需复制测试配置。");
    }

    setSummary({
      landingServers: `${landingServers.length} 台`,
      landingStatus: landingServers.length ? "已接入" : "未接入",
      landingDetail: landingServers.length
        ? `Worker 在线 ${landingServers.filter((server) => server.worker_online).length} 台；用于直连节点和中转目标。`
        : "请先添加落地服务器。",
      directNode: primaryNode ? "已创建" : "未创建",
      directNodeDetail: primaryNode
        ? `${primaryNode.node_name} / ${displayDashboardStatus(primaryNode.status)}`
        : "暂无直连 Reality 节点。",
      directNodeEntry: primaryNode ? entryWithPort(primaryNode.vps_ip, primaryNode.port) : "未返回",
      directNodeConfig: primaryNodeHasShareLink ? "可导出配置" : "未生成配置",
      transitServers: `${transitServers.length} 台`,
      transitWorkerStatus: onlineTransitServers.length ? "在线" : "离线 / 未接入",
      transitWorkerDetail: primaryTransitServer
        ? `${primaryTransitServer.name} / ${primaryTransitServer.worker_version ?? "版本未返回"}`
        : "暂无中转服务器。",
      transitRoute: primaryRoute ? displayDashboardStatus(primaryRoute.status) : "未创建",
      transitRouteEntry: primaryRoute ? entryWithPort(routeTransitResource?.entry_host, primaryRoute.listen_port) : "未返回",
      transitRouteTarget: primaryRoute ? entryWithPort(primaryRoute.target_host, primaryRoute.target_port) : "未返回",
      transitRouteDetail: primaryRoute
        ? `${primaryRoute.name} / ${primaryRoute.forwarding_method} / cutover 未切换`
        : "暂无 active 中转链路。",
      health: healthOk ? "正常" : "需检查",
      recentTask: latestTask ? `${latestTask.task_type} / ${taskStatusLabel(latestTask.status)}` : "无任务",
      safetyNodeShareLink: "未被中转流程改写",
      safetyRouteShareLink: routeShareLinkWritten ? "已写入，需复核" : "未写入",
      safetyCutover: "未切换",
      safetyOriginalNode: "保留",
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
          <span className="page-eyebrow">网络搭建状态</span>
          <h2>搭建网络状态总览</h2>
          <p>
            一眼查看落地服务器、直连节点、中转 Worker 和中转链路状态。总览只读取本地 API，
            不执行远程命令，也不会显示完整节点链接或修改 `nodes.share_link`。
          </p>
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
          detail={summary.transitWorkerDetail}
          label="中转服务器"
          status={summary.transitWorkerStatus}
          tone={summary.transitWorkerStatus === "在线" ? "success" : "warning"}
          value={summary.transitServers}
        />
        <OverviewStatusCard
          detail={`${summary.transitRouteEntry} -> ${summary.transitRouteTarget}`}
          label="中转链路"
          status="未 cutover"
          tone={summary.transitRoute === "active" ? "success" : "warning"}
          value={summary.transitRoute}
        />
      </div>

      <div className="overview-panels">
        <section className="panel overview-section">
          <div className="status-row">
            <div>
              <h2>当前可用链路</h2>
              <p className="message">只显示 IP、端口、状态和用途；不显示完整客户端链接。</p>
            </div>
            <span className="pill ok">摘要</span>
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
              <h2>安全状态</h2>
              <p className="message">当前系统只用于搭建和导出测试配置，不自动替换原节点。</p>
            </div>
            <span className="pill muted">只读摘要</span>
          </div>
          <div className="overview-safety-grid">
            <span>nodes.share_link：{summary.safetyNodeShareLink}</span>
            <span>transit_routes.share_link：{summary.safetyRouteShareLink}</span>
            <span>cutover：{summary.safetyCutover}</span>
            <span>原直连节点：{summary.safetyOriginalNode}</span>
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
              <p className="message">总览页只做导航，不放执行按钮，避免误操作。</p>
            </div>
            <span className="pill muted">导航</span>
          </div>
          <div className="overview-next-actions">
            <button className="secondary" type="button" onClick={() => onNavigate("servers")}>
              去落地服务器
            </button>
            <button className="secondary" type="button" onClick={() => onNavigate("transitRoutes")}>
              去中转服务器
            </button>
            <button className="secondary" type="button" onClick={() => onNavigate("transitLinks")}>
              去中转链路
            </button>
          </div>
          <p className="message">需要排查问题时，后续进入诊断中心；当前阶段暂不展开完整排障模块。</p>
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

function SettingsPanel() {
  return (
    <section className="panel wide settings-panel">
      <div className="status-row">
        <div>
          <h2>本地控制台设置与安全基线</h2>
          <p className="message">当前只记录本地使用边界；这里不会修改后端配置、链路或数据库。</p>
        </div>
        <span className="pill muted">仅本地</span>
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
          <strong>正式切换</strong>
          <span>当前阶段不是正式 cutover；修改 node.share_link 必须单独审批。</span>
        </div>
      </div>
      <RouteSafetyGuardrails />
    </section>
  );
}
