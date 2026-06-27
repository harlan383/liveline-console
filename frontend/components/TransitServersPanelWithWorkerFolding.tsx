"use client";

import { useEffect, useRef } from "react";

import { TransitServersPanel } from "@/components/TransitRoutesPanel";

const historyPanelId = "transit-worker-history-fold-panel";
const historicalWorkerMarkers = ["心跳过期 / 离线", "Worker 离线", "已删除"];

function normalizeText(value: string | null | undefined) {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function isHistoricalWorkerRow(group: HTMLElement) {
  const text = normalizeText(group.textContent);
  if (!text || text.includes("待安装 Worker") || text.includes("Worker 在线")) {
    return false;
  }
  return historicalWorkerMarkers.some((marker) => text.includes(marker));
}

function workerGroupSummary(group: HTMLElement) {
  const name = normalizeText(group.querySelector("strong")?.textContent) || "未命名中转服务器";
  const status = normalizeText(group.querySelector(".pill")?.textContent) || "状态未返回";
  const worker = normalizeText(group.querySelector(".server-row-worker")?.textContent) || "Worker 信息未返回";
  return { name, status, worker };
}

function createHistoryPanel(groups: HTMLElement[]) {
  const details = document.createElement("details");
  details.id = historyPanelId;
  details.setAttribute("aria-label", "历史 Worker 记录");
  details.style.marginTop = "12px";
  details.style.border = "1px solid rgba(148, 163, 184, 0.22)";
  details.style.borderRadius = "16px";
  details.style.padding = "12px 14px";
  details.style.background = "rgba(15, 23, 42, 0.52)";

  const summary = document.createElement("summary");
  summary.textContent = `历史 Worker 记录（${groups.length} 条，已折叠）`;
  summary.style.cursor = "pointer";
  summary.style.fontWeight = "700";
  summary.style.color = "#cbd5e1";
  details.appendChild(summary);

  const message = document.createElement("p");
  message.textContent = "这些记录只在界面折叠展示，数据库记录未删除，worker targeting 与中转链路创建逻辑不受影响。";
  message.style.margin = "10px 0";
  message.style.color = "#94a3b8";
  message.style.fontSize = "13px";
  details.appendChild(message);

  const list = document.createElement("div");
  list.style.display = "grid";
  list.style.gap = "8px";
  groups.forEach((group) => {
    const item = document.createElement("div");
    const { name, status, worker } = workerGroupSummary(group);
    item.style.border = "1px solid rgba(148, 163, 184, 0.18)";
    item.style.borderRadius = "12px";
    item.style.padding = "10px";
    item.style.background = "rgba(2, 6, 23, 0.35)";
    item.innerHTML = `<strong>${name}</strong><br><span>状态：${status}</span><br><small>${worker}</small>`;
    list.appendChild(item);
  });
  details.appendChild(list);

  const actions = document.createElement("div");
  actions.style.marginTop = "10px";
  const revealButton = document.createElement("button");
  revealButton.type = "button";
  revealButton.textContent = "临时显示原始历史行";
  revealButton.className = "secondary";
  revealButton.addEventListener("click", () => {
    groups.forEach((group) => {
      group.style.removeProperty("display");
      group.dataset.workerHistoryFolded = "revealed";
    });
    details.remove();
  });
  actions.appendChild(revealButton);
  details.appendChild(actions);

  return details;
}

function applyWorkerHistoryFolding(root: HTMLElement) {
  const table = root.querySelector<HTMLElement>('.server-table[aria-label="中转服务器管理表格"]');
  if (!table) {
    return;
  }

  root.querySelector(`#${historyPanelId}`)?.remove();

  const groups = Array.from(table.querySelectorAll<HTMLElement>(":scope > .server-table-group"));
  const historicalGroups: HTMLElement[] = [];

  groups.forEach((group) => {
    if (group.dataset.workerHistoryFolded === "revealed") {
      group.style.removeProperty("display");
      return;
    }
    if (isHistoricalWorkerRow(group)) {
      group.style.display = "none";
      group.dataset.workerHistoryFolded = "true";
      historicalGroups.push(group);
      return;
    }
    group.style.removeProperty("display");
    delete group.dataset.workerHistoryFolded;
  });

  if (!historicalGroups.length) {
    return;
  }

  table.insertAdjacentElement("afterend", createHistoryPanel(historicalGroups));
}

export function TransitServersPanelWithWorkerFolding() {
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root || typeof MutationObserver === "undefined") {
      return;
    }

    let pending = false;
    const observer = new MutationObserver(() => {
      if (pending) {
        return;
      }
      pending = true;
      window.requestAnimationFrame(() => {
        pending = false;
        observer.disconnect();
        applyWorkerHistoryFolding(root);
        observer.observe(root, { childList: true, subtree: true });
      });
    });

    applyWorkerHistoryFolding(root);
    observer.observe(root, { childList: true, subtree: true });

    return () => observer.disconnect();
  }, []);

  return (
    <div ref={rootRef}>
      <TransitServersPanel />
    </div>
  );
}
