"use client";

import { useEffect, useState } from "react";

import { LoginScreen } from "@/components/LoginScreen";
import { NodesPanel } from "@/components/NodesPanel";
import { RouteSafetyGuardrails } from "@/components/RouteSafetyGuardrails";
import { ServerManagementPanel } from "@/components/ServerManagementPanel";
import { SystemStatus } from "@/components/SystemStatus";
import { TaskHistoryPanel } from "@/components/TaskHistoryPanel";
import { TransitRoutesPanel } from "@/components/TransitRoutesPanel";
import { TransitTopologyPreviewPanel } from "@/components/TransitTopologyPreviewPanel";
import {
  AUTH_EXPIRED_EVENT,
  apiFetch,
  type AuthUser,
  type CsrfResult,
  type HealthData,
  type NodeListResult,
  type TaskListResult,
  type TransitRouteListResult,
} from "@/lib/api";

const RECREATE_VPS_STORAGE_KEY = "livelines.recreateVpsId";

type PanelId = "dashboard" | "servers" | "nodes" | "transitRoutes" | "tasks" | "diagnostics" | "settings";

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
    title: "运维总览",
    eyebrow: "本地控制台",
    description: "查看本地控制台健康状态、节点规模、中转链路和最近任务状态。",
  },
  {
    id: "servers",
    label: "服务器",
    title: "服务器",
    eyebrow: "VPS 与中转资源",
    description: "管理 VPS 读取和中转资源元信息；资源记录不等于真实线路。",
  },
  {
    id: "nodes",
    label: "节点",
    title: "节点",
    eyebrow: "Reality 节点运维",
    description: "查看直连节点、状态、导出体验和 Xray 备份元数据。",
  },
  {
    id: "transitRoutes",
    label: "中转链路",
    title: "中转链路",
    eyebrow: "链路规划与安全",
    description: "规划、查看和诊断单条中转链路；正式切换必须单独审批。",
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
  const [recreateVpsId, setRecreateVpsId] = useState<string | null>(null);
  const [activePanel, setActivePanel] = useState<PanelId>("dashboard");
  const [currentAdmin, setCurrentAdmin] = useState<AuthUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [authMessage, setAuthMessage] = useState("");
  const activePanelMeta = panels.find((panel) => panel.id === activePanel) ?? panels[1];

  useEffect(() => {
    setRecreateVpsId(window.localStorage.getItem(RECREATE_VPS_STORAGE_KEY));
  }, []);

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

  function handleVpsReadyForRecreate(vpsId: string) {
    setRecreateVpsId(vpsId);
    window.localStorage.setItem(RECREATE_VPS_STORAGE_KEY, vpsId);
  }

  function clearRecreateVps() {
    setRecreateVpsId(null);
    window.localStorage.removeItem(RECREATE_VPS_STORAGE_KEY);
  }

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
          <span>正式链路</span>
          <strong>socat 18443</strong>
          <span>回退链路</span>
          <strong>gost 8443</strong>
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
              <span className="ops-badge success">正式链路 socat 18443</span>
              <span className="ops-badge warning">回退链路 gost 8443</span>
              <span className="ops-badge muted">当前不执行 cutover</span>
            </div>
            <span className="admin-badge">已登录：{currentAdmin.username}</span>
            <button className="ghost-button" type="button" onClick={handleLogout}>
              退出登录
            </button>
          </div>
        </header>

        <RouteSafetyGuardrails />

        <div className="grid">
          {activePanel === "dashboard" ? <DashboardPanel /> : null}
          {activePanel === "servers" ? <ServerManagementPanel /> : null}
          {activePanel === "nodes" ? <NodesPanel onVpsReadyForRecreate={handleVpsReadyForRecreate} /> : null}
          {activePanel === "transitRoutes" ? <TransitRoutesPanel /> : null}
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

function DashboardPanel() {
  const [metrics, setMetrics] = useState({
    vpsTotal: "-",
    onlineVps: "-",
    nodeTotal: "-",
    healthyNodes: "-",
    abnormalNodes: "-",
    transitRoutes: "-",
    recentTask: "无任务",
    health: "读取中",
  });
  const [message, setMessage] = useState("正在读取本地总览。");

  async function loadDashboard() {
    const [healthResult, nodeResult, routeResult, taskResult] = await Promise.all([
      apiFetch<HealthData>("/api/health"),
      apiFetch<NodeListResult>("/api/nodes"),
      apiFetch<TransitRouteListResult>("/api/transit-routes"),
      apiFetch<TaskListResult>("/api/tasks?limit=8"),
    ]);

    const nodes = nodeResult.success ? nodeResult.data.nodes : [];
    const routes = routeResult.success ? routeResult.data.routes : [];
    const tasks = taskResult.success ? taskResult.data.tasks : [];
    const uniqueVps = new Set(nodes.map((node) => node.vps_id ?? node.vps_ip).filter(Boolean));
    const onlineVps = new Set(
      nodes
        .filter((node) => node.status === "active" || node.service_status === "active")
        .map((node) => node.vps_id ?? node.vps_ip)
        .filter(Boolean),
    );
    const healthyNodes = nodes.filter((node) => node.status === "active").length;
    const healthOk =
      healthResult.success &&
      Object.values(healthResult.data).every((component) => component.status === "ok");
    const latestTask = tasks[0];

    setMetrics({
      vpsTotal: String(uniqueVps.size),
      onlineVps: String(onlineVps.size),
      nodeTotal: String(nodes.length),
      healthyNodes: String(healthyNodes),
      abnormalNodes: String(Math.max(nodes.length - healthyNodes, 0)),
      transitRoutes: String(routes.length),
      recentTask: latestTask ? `${latestTask.task_type} / ${taskStatusLabel(latestTask.status)}` : "无任务",
      health: healthOk ? "正常" : "需检查",
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
          <span className="page-eyebrow">LiveLine Console v1</span>
          <h2>本地运维控制台总览</h2>
          <p>
            当前正式链路为 <strong>socat 18443</strong>，回退链路为 <strong>gost 8443</strong>。
            本页面只读取本地 API，不执行远程命令，也不会修改 node.share_link。
          </p>
        </div>
        <button className="secondary" type="button" onClick={() => void loadDashboard()}>
          刷新总览
        </button>
      </div>

      <div className="metric-grid">
        <MetricCard label="VPS 总数" value={metrics.vpsTotal} tone="info" />
        <MetricCard label="在线 VPS" value={metrics.onlineVps} tone="success" />
        <MetricCard label="节点总数" value={metrics.nodeTotal} tone="info" />
        <MetricCard label="正常节点" value={metrics.healthyNodes} tone="success" />
        <MetricCard label="异常节点" value={metrics.abnormalNodes} tone="danger" />
        <MetricCard label="中转链路" value={metrics.transitRoutes} tone="warning" />
        <MetricCard label="最近任务" value={metrics.recentTask} tone="muted" />
        <MetricCard label="本地健康" value={metrics.health} tone={metrics.health === "正常" ? "success" : "warning"} />
      </div>

      <div className="dashboard-panels">
        <SystemStatus />
        <section className="panel">
          <h2>运维安全边界</h2>
          <div className="status-list">
            <div className="status-row">
              <div>
                <strong>正式链路</strong>
                <p className="message">socat 18443，当前 node.share_link 已指向该链路。</p>
              </div>
              <span className="pill ok">正常</span>
            </div>
            <div className="status-row">
              <div>
                <strong>回退链路</strong>
                <p className="message">gost 8443 必须继续保留，不关闭、不降级、不替换。</p>
              </div>
              <span className="pill warn">警告</span>
            </div>
            <div className="status-row">
              <div>
                <strong>远程执行</strong>
                <p className="message">当前仍为 No-Go；真正 SSH / 创建转发 / cutover 必须另开阶段。</p>
              </div>
              <span className="pill muted">未检测</span>
            </div>
          </div>
          <p className="message">{message}</p>
        </section>
      </div>
    </section>
  );
}

function MetricCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "success" | "warning" | "danger" | "muted" | "info";
}) {
  return (
    <div className={`metric-card ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
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
