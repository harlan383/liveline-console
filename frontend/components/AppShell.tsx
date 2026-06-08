"use client";

import { useEffect, useState } from "react";

import { LoginScreen } from "@/components/LoginScreen";
import { NodesPanel } from "@/components/NodesPanel";
import { ReadVpsPanel } from "@/components/ReadVpsPanel";
import { SystemStatus } from "@/components/SystemStatus";
import { TransitResourcesPanel } from "@/components/TransitResourcesPanel";
import { TransitRoutesPanel } from "@/components/TransitRoutesPanel";
import { TransitTopologyPreviewPanel } from "@/components/TransitTopologyPreviewPanel";
import { AUTH_EXPIRED_EVENT, apiFetch, type AuthUser, type CsrfResult } from "@/lib/api";

const RECREATE_VPS_STORAGE_KEY = "livelines.recreateVpsId";

type PanelId = "system" | "servers" | "transitResources" | "topology" | "transitRoutes";

const panels: Array<{
  id: PanelId;
  label: string;
  title: string;
  description: string;
}> = [
  {
    id: "system",
    label: "系统状态",
    title: "系统状态",
    description: "查看前端、后端、PostgreSQL、Redis 和 RQ Worker 的基础状态。",
  },
  {
    id: "servers",
    label: "服务器管理",
    title: "服务器管理",
    description: "管理 VPS 读取、直连节点、节点导出和 Xray 备份查看。",
  },
  {
    id: "transitResources",
    label: "中转资源",
    title: "中转资源",
    description: "录入和管理普通公网中转服务器、IEPL / IPLC 等资源元信息。",
  },
  {
    id: "topology",
    label: "拓扑预览",
    title: "中转拓扑预览",
    description: "只在前端本地预览中转链路和未来配置，不连接远端、不保存 route。",
  },
  {
    id: "transitRoutes",
    label: "单条转发",
    title: "单条转发",
    description: "查看和创建单条 gost TCP 转发，已有链接默认脱敏展示。",
  },
];

export function AppShell() {
  const [recreateVpsId, setRecreateVpsId] = useState<string | null>(null);
  const [activePanel, setActivePanel] = useState<PanelId>("servers");
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
        <div className="brand">LiveLine Console</div>
        <div className="stage">Stage 3.4.1 登录门禁</div>
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
            <h1>{activePanelMeta.title}</h1>
            <p>{activePanelMeta.description}</p>
          </div>
          <div className="topbar-actions">
            <span className="admin-badge">已登录：{currentAdmin.username}</span>
            <button className="ghost-button" type="button" onClick={handleLogout}>
              退出登录
            </button>
          </div>
        </header>

        <div className="grid">
          <SystemStatus />
          {activePanel === "servers" ? (
            <>
              <ReadVpsPanel recreateVpsId={recreateVpsId} onRecreateVpsConsumed={clearRecreateVps} />
              <NodesPanel onVpsReadyForRecreate={handleVpsReadyForRecreate} />
              <section className="panel wide">
                <h2>任务日志</h2>
                <div className="empty">节点相关任务日志会在对应面板中展示。</div>
              </section>
            </>
          ) : null}
          {activePanel === "transitResources" ? <TransitResourcesPanel /> : null}
          {activePanel === "topology" ? <TransitTopologyPreviewPanel /> : null}
          {activePanel === "transitRoutes" ? <TransitRoutesPanel /> : null}
          {activePanel === "system" ? (
            <section className="panel wide">
              <h2>操作区</h2>
              <div className="empty">请选择左侧菜单进入对应管理区域。</div>
            </section>
          ) : null}
        </div>
      </section>
    </main>
  );
}
