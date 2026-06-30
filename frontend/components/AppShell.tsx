"use client";

import { useEffect, useState } from "react";

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
  getProductOverview,
  type AuthUser,
  type CsrfResult,
  type ProductOverviewAttentionItem,
  type ProductOverviewHealth,
  type ProductOverviewRecentCreatedItem,
  type ProductOverviewResult,
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
    icon: "customerLines",
    tone: "blue",
    label: "客户线路",
    title: "客户线路",
    subtitle: "统一管理每个客户分配到的直连线路和中转线路。",
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

function formatDate(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString();
}

export function AppShell() {
  const [activePanel, setActivePanel] = useState<PanelId>("dashboard");
  const [currentAdmin, setCurrentAdmin] = useState<AuthUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [authMessage, setAuthMessage] = useState("");
  const [sidebarHealth, setSidebarHealth] = useState<ProductOverviewHealth | null>(null);
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
        <button className={`sidebar-health-card ${sidebarHealth?.status ?? "loading"}`} type="button" onClick={() => setActivePanel("advancedDebug")}>
          <span className="health-dot" />
          <span>
            <strong>{sidebarHealth?.label ?? "系统状态读取中"}</strong>
            <small>{sidebarHealth ? `最近更新：${sidebarHealth.last_refreshed_label}` : "等待总览数据"}</small>
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
          {activePanel === "dashboard" ? <DashboardPanel onNavigate={setActivePanel} onOverviewHealth={setSidebarHealth} /> : null}
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

function attentionIconTone(tone: ProductOverviewAttentionItem["tone"]) {
  if (tone === "danger") {
    return "red";
  }
  if (tone === "warning") {
    return "orange";
  }
  if (tone === "success") {
    return "green";
  }
  return "blue";
}

function recentIconName(type: ProductOverviewRecentCreatedItem["type"]) {
  if (type === "landing_server" || type === "transit_resource") {
    return "server";
  }
  if (type === "direct_node") {
    return "builder";
  }
  return "route";
}

function DashboardPanel({
  onNavigate,
  onOverviewHealth,
}: {
  onNavigate: (panel: PanelId) => void;
  onOverviewHealth: (health: ProductOverviewHealth) => void;
}) {
  const [overview, setOverview] = useState<ProductOverviewResult | null>(null);
  const [message, setMessage] = useState("正在读取真实总览数据。");

  async function loadDashboard() {
    const result = await getProductOverview();
    if (result.success) {
      setOverview(result.data);
      onOverviewHealth(result.data.health);
      setMessage("总览数据已刷新。");
      return;
    }

    setOverview(null);
    setMessage("总览数据暂时无法读取。");
  }

  useEffect(() => {
    void loadDashboard();
  }, []);

  const normalLines = overview?.stats.normal_lines ?? 0;
  const riskLines = overview?.stats.risk_lines ?? 0;
  const abnormalLines = overview?.stats.abnormal_lines ?? 0;
  const pendingItems = overview?.stats.pending_items ?? 0;
  const attentionItems = overview?.attention_items ?? [];
  const recentCreated = overview?.recent_created ?? [];
  const tips = overview?.tips ?? [];
  const healthOk = overview?.health.ok ?? false;

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
            {attentionItems.length ? attentionItems.map((item) => (
              <button className={`attention-item ${item.tone}`} key={item.id} type="button" onClick={() => onNavigate("tasks")}>
                <ProductIcon name="alert" tone={attentionIconTone(item.tone)} />
                <div className="attention-copy">
                  <strong>{item.summary}</strong>
                  <small>{item.detail} · 发现时间：{item.time_label}</small>
                </div>
                <ProductIcon name="arrow" tone="slate" />
              </button>
            )) : (
              <div className="empty compact-empty">总览数据暂时无法读取。</div>
            )}
          </div>
          <button className="attention-view-all" type="button" onClick={() => onNavigate("tasks")}>
            查看全部告警 <span aria-hidden="true">›</span>
          </button>
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
                <div className="recent-create-row" key={`${item.type}-${item.id}`}>
                  <ProductIcon name={recentIconName(item.type)} tone="blue" />
                  <strong>{item.name}</strong>
                  <span>{item.type_label}</span>
                  <small>创建人：{item.created_by}</small>
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
            {tips.length ? tips.map((tip) => (
              <li key={tip}>{tip}</li>
            )) : (
              <li>总览数据暂时无法读取，请稍后刷新或进入高级调试查看系统状态。</li>
            )}
          </ul>
        </section>
      </div>
      <p className="message subtle-message">{message}</p>
    </section>
  );
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
