"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";

import { PlatformIcon, ProductIcon } from "@/components/ProductIcons";
import {
  apiFetch,
  type NodeData,
  type NodeListResult,
  type TransitResourceData,
  type TransitResourceListResult,
  type TransitRouteData,
  type TransitRouteListResult,
} from "@/lib/api";

type LineHealth = "normal" | "risk" | "abnormal";
type LineKind = "direct" | "transit";
type ModalMode = "detail" | "edit" | "client" | "monitor";

type CustomerLine = {
  id: string;
  source: "node" | "route" | "demo";
  name: string;
  customer: string;
  platform: string;
  kind: LineKind;
  kindLabel: string;
  mode: "主线" | "备用";
  purpose: string;
  health: LineHealth;
  statusLabel: string;
  lastIssue: string;
  entryHost: string;
  entryPort: number | null;
  targetLabel: string;
  transitLabel: string;
  landingLabel: string;
  regionLabel: string;
  note: string;
  configGenerated: boolean;
  createdAt: string | null;
};

type EditDraft = {
  name: string;
  customer: string;
  platform: string;
  kind: LineKind;
  mode: "主线" | "备用";
  purpose: string;
  note: string;
};

type LineOverride = Partial<Pick<CustomerLine, "name" | "customer" | "platform" | "kind" | "kindLabel" | "mode" | "purpose" | "note">>;

const healthTabs: Array<{ label: string; value: "all" | LineHealth }> = [
  { label: "全部", value: "all" },
  { label: "正常", value: "normal" },
  { label: "风险", value: "risk" },
  { label: "异常", value: "abnormal" },
];

const defaultDemoLines: CustomerLine[] = [
  {
    id: "demo-facebook-vn-primary",
    source: "demo",
    name: "客户A-Facebook越南主线",
    customer: "客户A",
    platform: "Facebook",
    kind: "direct",
    kindLabel: "直连线路",
    mode: "主线",
    purpose: "主用线路",
    health: "normal",
    statusLabel: "正常",
    lastIssue: "-",
    entryHost: "vn1.livecdn.net",
    entryPort: 443,
    targetLabel: "Facebook",
    transitLabel: "直连（无中转）",
    landingLabel: "越南 · 胡志明市",
    regionLabel: "越南 · 胡志明市",
    note: "越南方向主用线路，稳定性优先。",
    configGenerated: true,
    createdAt: "2026-06-28T11:20:00+08:00",
  },
  {
    id: "demo-facebook-vn-backup",
    source: "demo",
    name: "客户A-Facebook越南备用线",
    customer: "客户A",
    platform: "Facebook",
    kind: "direct",
    kindLabel: "直连线路",
    mode: "备用",
    purpose: "备用线路",
    health: "normal",
    statusLabel: "正常",
    lastIssue: "-",
    entryHost: "vn2.livecdn.net",
    entryPort: 443,
    targetLabel: "Facebook",
    transitLabel: "直连（无中转）",
    landingLabel: "越南 · 胡志明市",
    regionLabel: "越南 · 胡志明市",
    note: "主线不可用时切换，保持同平台配置。",
    configGenerated: true,
    createdAt: "2026-06-28T12:10:00+08:00",
  },
  {
    id: "demo-tiktok-sg-primary",
    source: "demo",
    name: "客户B-TikTok新加坡主线",
    customer: "客户B",
    platform: "TikTok",
    kind: "transit",
    kindLabel: "中转线路",
    mode: "主线",
    purpose: "主用线路",
    health: "risk",
    statusLabel: "风险",
    lastIssue: "昨天 16:10",
    entryHost: "109.244.79.147",
    entryPort: 29833,
    targetLabel: "TikTok",
    transitLabel: "广州IEPL-香港出口01",
    landingLabel: "新加坡落地01",
    regionLabel: "新加坡",
    note: "中转端口近期存在波动，建议检查放行配置。",
    configGenerated: true,
    createdAt: "2026-06-27T16:35:00+08:00",
  },
  {
    id: "demo-youtube-hk-primary",
    source: "demo",
    name: "客户C-YouTube香港主线",
    customer: "客户C",
    platform: "YouTube",
    kind: "direct",
    kindLabel: "直连线路",
    mode: "主线",
    purpose: "主用线路",
    health: "normal",
    statusLabel: "正常",
    lastIssue: "-",
    entryHost: "hk1.livecdn.net",
    entryPort: 443,
    targetLabel: "YouTube",
    transitLabel: "直连（无中转）",
    landingLabel: "中国香港",
    regionLabel: "中国香港",
    note: "香港方向主线，当前服务运行正常。",
    configGenerated: true,
    createdAt: "2026-06-26T15:10:00+08:00",
  },
  {
    id: "demo-meta-vn-primary",
    source: "demo",
    name: "自己使用-Meta越南主线",
    customer: "自己使用",
    platform: "Meta",
    kind: "direct",
    kindLabel: "直连线路",
    mode: "主线",
    purpose: "看视频 / 日常使用",
    health: "abnormal",
    statusLabel: "异常",
    lastIssue: "今天 09:42",
    entryHost: "vn-meta.livecdn.net",
    entryPort: 443,
    targetLabel: "Meta",
    transitLabel: "直连（无中转）",
    landingLabel: "越南 · 胡志明市",
    regionLabel: "越南 · 胡志明市",
    note: "自用线路，最近一次检测异常，需要稍后复核。",
    configGenerated: true,
    createdAt: "2026-06-25T09:42:00+08:00",
  },
];

function classifyCustomer(text: string) {
  if (/客户A/i.test(text)) {
    return "客户A";
  }
  if (/客户B/i.test(text)) {
    return "客户B";
  }
  if (/客户C/i.test(text)) {
    return "客户C";
  }
  if (/自己|自用|个人/i.test(text)) {
    return "自己使用";
  }
  return "未分配";
}

function classifyPlatform(text: string) {
  if (/facebook|\bfb\b/i.test(text)) {
    return "Facebook";
  }
  if (/tiktok|\btk\b/i.test(text)) {
    return "TikTok";
  }
  if (/youtube|\byt\b/i.test(text)) {
    return "YouTube";
  }
  if (/meta|instagram|whatsapp/i.test(text)) {
    return "Meta";
  }
  return "未设置";
}

function classifyMode(text: string): "主线" | "备用" {
  return /备用|backup/i.test(text) ? "备用" : "主线";
}

function classifyPurpose(text: string, mode: "主线" | "备用") {
  if (/测试|test/i.test(text)) {
    return "测试线路";
  }
  if (/视频|日常/i.test(text)) {
    return "看视频 / 日常使用";
  }
  return mode === "备用" ? "备用线路" : "主用线路";
}

function healthLabel(health: LineHealth) {
  const labels: Record<LineHealth, string> = {
    normal: "正常",
    risk: "风险",
    abnormal: "异常",
  };
  return labels[health];
}

function healthFromStatus(status: string, hasConfig: boolean): LineHealth {
  if (status === "failed" || status === "timeout" || status === "deleted") {
    return "abnormal";
  }
  if (status !== "active" || !hasConfig) {
    return "risk";
  }
  return "normal";
}

function formatDate(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString();
}

function lineAddress(host: string, port: number | null) {
  return port ? `${host}:${port}` : host;
}

function lineFromNode(node: NodeData): CustomerLine {
  const text = [node.node_name, node.vps_ip, node.reality_server_name, node.reality_dest].filter(Boolean).join(" ");
  const mode = classifyMode(text);
  const hasConfig = Boolean(node.share_link_present || node.has_share_link || node.masked_share_link);
  const health = healthFromStatus(node.status, hasConfig);
  return {
    id: `node-${node.id}`,
    source: "node",
    name: node.node_name,
    customer: classifyCustomer(text),
    platform: classifyPlatform(text),
    kind: "direct",
    kindLabel: "直连线路",
    mode,
    purpose: classifyPurpose(text, mode),
    health,
    statusLabel: healthLabel(health),
    lastIssue: health === "normal" ? "-" : "最近状态未完全正常",
    entryHost: node.vps_ip ?? "未返回",
    entryPort: node.port,
    targetLabel: classifyPlatform(text) === "未设置" ? "目标平台" : classifyPlatform(text),
    transitLabel: "直连（无中转）",
    landingLabel: node.reality_dest ?? node.vps_ip ?? "落地节点",
    regionLabel: node.reality_server_name ?? "落地地区未设置",
    note: "直连线路，可在详情中查看连接入口摘要。",
    configGenerated: hasConfig,
    createdAt: node.created_at,
  };
}

function lineFromRoute(route: TransitRouteData, resource: TransitResourceData | undefined): CustomerLine {
  const text = [
    route.name,
    route.transit_resource_name,
    route.node_name,
    resource?.notes,
    resource?.entry_region,
    resource?.exit_region,
  ]
    .filter(Boolean)
    .join(" ");
  const mode = classifyMode(text);
  const health = healthFromStatus(route.status, true);
  const platform = classifyPlatform(text);
  return {
    id: `route-${route.id}`,
    source: "route",
    name: route.name,
    customer: classifyCustomer(text),
    platform,
    kind: "transit",
    kindLabel: "中转线路",
    mode,
    purpose: classifyPurpose(text, mode),
    health,
    statusLabel: healthLabel(health),
    lastIssue: health === "normal" ? "-" : "中转状态需复核",
    entryHost: resource?.entry_host ?? route.transit_resource_name ?? "中转入口",
    entryPort: route.listen_port,
    targetLabel: platform === "未设置" ? "目标平台" : platform,
    transitLabel: resource?.name ?? route.transit_resource_name ?? "中转入口",
    landingLabel: route.node_name ?? `${route.target_host}:${route.target_port}`,
    regionLabel: resource?.exit_region ?? resource?.entry_region ?? "线路地区未设置",
    note: "通过中转入口访问落地节点，适合需要优化路径的客户线路。",
    configGenerated: route.status === "active",
    createdAt: route.created_at,
  };
}

function mergeLineOverride(line: CustomerLine, override: LineOverride | undefined): CustomerLine {
  if (!override) {
    return line;
  }
  const kind = override.kind ?? line.kind;
  return {
    ...line,
    ...override,
    kind,
    kindLabel: override.kindLabel ?? (kind === "transit" ? "中转线路" : "直连线路"),
  };
}

function toEditDraft(line: CustomerLine): EditDraft {
  return {
    name: line.name,
    customer: line.customer,
    platform: line.platform,
    kind: line.kind,
    mode: line.mode,
    purpose: line.purpose,
    note: line.note,
  };
}

function healthTone(health: LineHealth) {
  return health === "normal" ? "success" : health === "risk" ? "warning" : "danger";
}

function productTone(health: LineHealth) {
  return health === "normal" ? "green" : health === "risk" ? "orange" : "red";
}

function maskConnection(line: CustomerLine, revealed: boolean) {
  if (!revealed) {
    return "连接内容已隐藏，仅手动查看。•••• •••• •••• ••••";
  }
  return `服务器 ${line.entryHost} / 端口 ${line.entryPort ?? "-"} / ${line.kindLabel} / ${line.platform}。完整客户端内容仍保持隐藏。`;
}

export function CustomerLinesPanel() {
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [routes, setRoutes] = useState<TransitRouteData[]>([]);
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [selectedLineId, setSelectedLineId] = useState<string | null>(null);
  const [modalMode, setModalMode] = useState<ModalMode | null>(null);
  const [activeFilter, setActiveFilter] = useState<"all" | LineHealth>("all");
  const [search, setSearch] = useState("");
  const [customerFilter, setCustomerFilter] = useState("all");
  const [platformFilter, setPlatformFilter] = useState("all");
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [lineOverrides, setLineOverrides] = useState<Record<string, LineOverride>>({});
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
  const [showConnectionContent, setShowConnectionContent] = useState(false);
  const [message, setMessage] = useState("正在读取客户线路。");

  async function loadData() {
    const [nodeResult, routeResult, resourceResult] = await Promise.all([
      apiFetch<NodeListResult>("/api/nodes"),
      apiFetch<TransitRouteListResult>("/api/transit-routes"),
      apiFetch<TransitResourceListResult>("/api/transit-resources"),
    ]);
    if (nodeResult.success) {
      setNodes(nodeResult.data.nodes);
    }
    if (routeResult.success) {
      setRoutes(routeResult.data.routes);
    }
    if (resourceResult.success) {
      setResources(resourceResult.data.resources);
    }
    setMessage(
      [nodeResult, routeResult, resourceResult].every((result) => result.success)
        ? "客户线路已刷新。"
        : "部分客户线路数据暂时无法读取。",
    );
  }

  useEffect(() => {
    void loadData();
  }, []);

  const customerLines = useMemo(() => {
    const activeNodes = nodes.filter((node) => node.status === "active").map(lineFromNode);
    const activeRoutes = routes
      .filter((route) => route.status === "active" && !route.deleted_at)
      .map((route) => lineFromRoute(route, resources.find((resource) => resource.id === route.transit_resource_id)));
    const liveLines = [...activeRoutes, ...activeNodes];
    const baseLines = liveLines.length ? liveLines : defaultDemoLines;
    return baseLines
      .map((line) => mergeLineOverride(line, lineOverrides[line.id]))
      .sort((a, b) => a.customer.localeCompare(b.customer) || a.name.localeCompare(b.name));
  }, [lineOverrides, nodes, resources, routes]);

  const filteredLines = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return customerLines.filter((line) => {
      const matchesStatus = activeFilter === "all" || line.health === activeFilter;
      const matchesCustomer = customerFilter === "all" || line.customer === customerFilter;
      const matchesPlatform = platformFilter === "all" || line.platform === platformFilter;
      const searchable = `${line.name} ${line.customer} ${line.platform} ${line.kindLabel} ${line.mode}`.toLowerCase();
      return matchesStatus && matchesCustomer && matchesPlatform && (!keyword || searchable.includes(keyword));
    });
  }, [activeFilter, customerFilter, customerLines, platformFilter, search]);

  const selectedLine = selectedLineId ? customerLines.find((line) => line.id === selectedLineId) ?? null : null;
  const normalCount = customerLines.filter((line) => line.health === "normal").length;
  const riskCount = customerLines.filter((line) => line.health === "risk").length;
  const abnormalCount = customerLines.filter((line) => line.health === "abnormal").length;
  const customerOptions = Array.from(new Set(customerLines.map((line) => line.customer)));
  const platformOptions = Array.from(new Set(customerLines.map((line) => line.platform)));

  function openModal(line: CustomerLine, mode: ModalMode) {
    setSelectedLineId(line.id);
    setModalMode(mode);
    setOpenMenuId(null);
    setShowConnectionContent(false);
    setEditDraft(toEditDraft(line));
  }

  function closeModal() {
    setSelectedLineId(null);
    setModalMode(null);
    setEditDraft(null);
    setShowConnectionContent(false);
  }

  async function copyText(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value);
      setMessage(`${label}已复制。`);
    } catch {
      setMessage(`${label}复制失败，请手动选择。`);
    }
  }

  function saveEditDemo() {
    if (!selectedLine || !editDraft) {
      return;
    }
    setLineOverrides((current) => ({
      ...current,
      [selectedLine.id]: {
        name: editDraft.name.trim() || selectedLine.name,
        customer: editDraft.customer,
        platform: editDraft.platform,
        kind: editDraft.kind,
        kindLabel: editDraft.kind === "transit" ? "中转线路" : "直连线路",
        mode: editDraft.mode,
        purpose: editDraft.purpose,
        note: editDraft.note,
      },
    }));
    setMessage("线路显示信息已保存（前端演示，不会修改数据库）。");
    closeModal();
  }

  function demoAction(label: string) {
    setOpenMenuId(null);
    setMessage(`${label}为前端演示操作，不会触发真实创建、删除或远程任务。`);
  }

  return (
    <section className="customer-lines-page wide">
      <div className="customer-line-stat-grid">
        <LineStat icon="shield" title="正常" value={normalCount} detail="线路运行正常" tone="success" />
        <LineStat icon="alert" title="风险" value={riskCount} detail="需要关注" tone="warning" />
        <LineStat icon="alert" title="异常" value={abnormalCount} detail="需要处理" tone="danger" />
      </div>

      <section className="customer-lines-card">
        <div className="customer-lines-toolbar">
          <div className="customer-line-tabs">
            {healthTabs.map((tab) => (
              <button
                className={activeFilter === tab.value ? "selected" : ""}
                key={tab.value}
                type="button"
                onClick={() => setActiveFilter(tab.value)}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="customer-line-filters">
            <label className="customer-search-field">
              <ProductIcon name="search" tone="slate" />
              <input
                aria-label="搜索线路名称"
                placeholder="搜索线路名称"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <select aria-label="客户筛选" value={customerFilter} onChange={(event) => setCustomerFilter(event.target.value)}>
              <option value="all">全部客户</option>
              {customerOptions.map((customer) => (
                <option key={customer} value={customer}>{customer}</option>
              ))}
            </select>
            <select aria-label="平台筛选" value={platformFilter} onChange={(event) => setPlatformFilter(event.target.value)}>
              <option value="all">全部平台</option>
              {platformOptions.map((platform) => (
                <option key={platform} value={platform}>{platform}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="customer-lines-table" role="table" aria-label="客户线路列表">
          <div className="customer-lines-row customer-lines-head" role="row">
            <span>线路名称</span>
            <span>客户</span>
            <span>平台</span>
            <span>类型</span>
            <span>主线/备用</span>
            <span>当前状态</span>
            <span>最近异常</span>
            <span>操作</span>
          </div>
          {filteredLines.length ? (
            filteredLines.map((line) => (
              <div className="customer-lines-row" key={line.id} role="row">
                <strong>{line.name}</strong>
                <span>{line.customer}</span>
                <span className="platform-cell"><PlatformIcon platform={line.platform} />{line.platform}</span>
                <span className={`line-type-pill ${line.kind}`}>{line.kindLabel}</span>
                <span>{line.mode}</span>
                <span className={`line-health-pill ${healthTone(line.health)}`}>{line.statusLabel}</span>
                <span className={line.health === "normal" ? "" : "issue-text"}>{line.lastIssue}</span>
                <span className="customer-line-actions">
                  <button className="secondary" type="button" onClick={() => openModal(line, "detail")}>
                    查看详情
                  </button>
                  <span className="line-more-wrap">
                    <button className="ghost-button line-more-button" type="button" onClick={() => setOpenMenuId(openMenuId === line.id ? null : line.id)}>
                      更多⌄
                    </button>
                    {openMenuId === line.id ? (
                      <span className="line-more-menu">
                        <button type="button" onClick={() => openModal(line, "edit")}>编辑线路</button>
                        <button type="button" onClick={() => openModal(line, "client")}>查看连接信息</button>
                        <button type="button" onClick={() => openModal(line, "monitor")}>查看监测详情</button>
                        <button type="button" onClick={() => demoAction(line.mode === "主线" ? "设为备用" : "设为主线")}>
                          {line.mode === "主线" ? "设为备用" : "设为主线"}
                        </button>
                        <button type="button" onClick={() => demoAction("暂停显示")}>暂停显示</button>
                        <button type="button" onClick={() => demoAction("删除绑定")}>删除绑定（演示）</button>
                      </span>
                    ) : null}
                  </span>
                </span>
              </div>
            ))
          ) : (
            <div className="customer-lines-empty">
              <ProductIcon name="customerLines" tone="blue" />
              <strong>没有匹配的客户线路</strong>
              <p>请调整筛选条件，或在“线路搭建”页面准备新的客户线路。</p>
            </div>
          )}
        </div>

        <div className="customer-line-pagination">
          <span>共 {filteredLines.length} 条</span>
          <div>
            <button className="secondary" disabled type="button">‹</button>
            <button className="current" type="button">1</button>
            <button className="secondary" disabled type="button">›</button>
            <select aria-label="每页条数" defaultValue="10">
              <option value="10">10 条/页</option>
              <option value="20">20 条/页</option>
            </select>
          </div>
        </div>
      </section>

      <p className="message subtle-message">{message}</p>

      {selectedLine && modalMode === "detail" ? (
        <LineDetailModal
          line={selectedLine}
          onClose={closeModal}
          onCopy={copyText}
          onEdit={() => setModalMode("edit")}
          onOpenClient={() => setModalMode("client")}
        />
      ) : null}
      {selectedLine && modalMode === "edit" && editDraft ? (
        <LineEditModal
          draft={editDraft}
          line={selectedLine}
          onChange={setEditDraft}
          onClose={closeModal}
          onRestore={() => setEditDraft(toEditDraft(selectedLine))}
          onSave={saveEditDemo}
        />
      ) : null}
      {selectedLine && modalMode === "client" ? (
        <LineClientInfoModal
          line={selectedLine}
          revealed={showConnectionContent}
          onClose={closeModal}
          onCopy={copyText}
          onToggleReveal={() => setShowConnectionContent((current) => !current)}
        />
      ) : null}
      {selectedLine && modalMode === "monitor" ? (
        <LineMonitorModal line={selectedLine} onClose={closeModal} onOpenDetail={() => setModalMode("detail")} onDemoAction={demoAction} />
      ) : null}
    </section>
  );
}

function LineStat({
  detail,
  icon,
  title,
  tone,
  value,
}: {
  detail: string;
  icon: string;
  title: string;
  tone: "success" | "warning" | "danger";
  value: number;
}) {
  return (
    <article className={`customer-line-stat ${tone}`}>
      <ProductIcon name={icon} tone={tone === "success" ? "green" : tone === "warning" ? "orange" : "red"} />
      <div>
        <span>{title}</span>
        <strong>{value}</strong>
        <small><i />{detail}</small>
      </div>
    </article>
  );
}

function ModalShell({
  children,
  label,
}: {
  children: ReactNode;
  label: string;
}) {
  return (
    <div className="modal-backdrop customer-modal-backdrop" role="presentation">
      <div className="modal-card customer-modal" role="dialog" aria-modal="true" aria-label={label}>
        {children}
      </div>
    </div>
  );
}

function ModalHeader({
  children,
  onClose,
  title,
}: {
  children?: ReactNode;
  onClose: () => void;
  title: string;
}) {
  return (
    <div className="customer-modal-header">
      <div>
        <h3>{title}</h3>
        {children}
      </div>
      <button className="modal-close-button" type="button" onClick={onClose}>×</button>
    </div>
  );
}

function LineDetailModal({
  line,
  onClose,
  onCopy,
  onEdit,
  onOpenClient,
}: {
  line: CustomerLine;
  onClose: () => void;
  onCopy: (value: string, label: string) => void;
  onEdit: () => void;
  onOpenClient: () => void;
}) {
  const pathItems = line.kind === "transit"
    ? [
        { icon: "builder", title: "本地/OBS", detail: "客户现场" },
        { icon: "servers", title: "中转服务器", detail: line.transitLabel },
        { icon: "server", title: "落地节点", detail: line.landingLabel },
        { icon: "platform", title: "目标平台", detail: line.platform },
      ]
    : [
        { icon: "builder", title: "本地/OBS", detail: "客户现场" },
        { icon: "server", title: "落地节点", detail: line.landingLabel },
        { icon: "platform", title: "目标平台", detail: line.platform },
      ];
  return (
    <ModalShell label="线路详情">
      <ModalHeader title="线路详情" onClose={onClose}>
        <span className={`line-health-pill ${healthTone(line.health)}`}>{line.statusLabel}</span>
      </ModalHeader>
      <div className="line-detail-layout">
        <div className="line-detail-main">
          <section className="line-modal-section">
            <h4>基础信息</h4>
            <div className="line-info-grid">
              <span>线路名称</span><strong>{line.name}</strong>
              <span>客户</span><strong>{line.customer}</strong>
              <span>平台</span><strong><PlatformIcon platform={line.platform} />{line.platform}</strong>
              <span>线路类型</span><strong>{line.kindLabel}</strong>
              <span>主线/备用</span><strong>{line.mode} <em>{line.mode}</em></strong>
              <span>备注</span><strong>{line.note}</strong>
            </div>
          </section>
          <section className="line-modal-section">
            <h4>线路路径</h4>
            <div className="line-path-preview">
              {pathItems.map((item, index) => (
                <span className="line-path-node" key={`${item.title}-${index}`}>
                  <ProductIcon name={item.icon} tone={index === pathItems.length - 1 ? "blue" : index === 1 ? "purple" : "green"} />
                  <strong>{item.title}</strong>
                  <small>{item.detail}</small>
                  {index < pathItems.length - 1 ? <b>→</b> : null}
                </span>
              ))}
            </div>
          </section>
          <section className="line-modal-section client-summary-section">
            <h4>客户端信息</h4>
            <div className="client-summary-grid">
              <span>连接地址</span><strong>{line.entryHost}</strong>
              <span>端口</span><strong>{line.entryPort ?? "-"}</strong>
            </div>
            <div className="client-summary-actions">
              <button className="secondary" type="button" onClick={onOpenClient}>查看连接信息</button>
              <button className="secondary" type="button" onClick={() => void onCopy(line.name, "线路名称")}>复制线路名称</button>
            </div>
          </section>
          <section className="line-modal-section recent-issue-section">
            <h4>最近异常</h4>
            <p className={line.health === "normal" ? "ok-text" : "issue-text"}>{line.lastIssue === "-" ? "当前无异常" : line.lastIssue}</p>
          </section>
        </div>
        <aside className="line-detail-side">
          <section className="line-modal-section run-status-card">
            <div className="line-section-title">
              <h4>运行状态</h4>
              <span className="online-dot">在线</span>
            </div>
            <div className="quality-grid">
              <span><strong>{line.health === "risk" ? "128" : "28"}</strong><small>Ping ms</small></span>
              <span><strong>{line.health === "risk" ? "36" : "3"}</strong><small>抖动 ms</small></span>
              <span><strong>{line.health === "risk" ? "1.25" : "0"}</strong><small>丢包率 %</small></span>
            </div>
          </section>
          <section className="line-modal-section timeline-card">
            <h4>最近检测</h4>
            {["入口连通", line.kind === "transit" ? "中转连通" : "直连入口", "落地在线", "出口正常"].map((item) => (
              <span key={item}><i />{item}<small>今天 09:42</small></span>
            ))}
          </section>
          <section className="line-modal-section">
            <h4>操作建议</h4>
            <p>{line.health === "normal" ? "线路运行良好，Ping 和丢包率均处于优秀水平，可继续保持当前配置。" : "线路存在波动，建议检查端口放行和备用线路可用性。"}</p>
          </section>
        </aside>
      </div>
      <div className="customer-modal-actions">
        <button className="secondary" type="button" onClick={onClose}>关闭</button>
        <button className="secondary" type="button" onClick={onEdit}>编辑线路</button>
        <button type="button" onClick={onOpenClient}>查看连接信息</button>
      </div>
    </ModalShell>
  );
}

function LineEditModal({
  draft,
  line,
  onChange,
  onClose,
  onRestore,
  onSave,
}: {
  draft: EditDraft;
  line: CustomerLine;
  onChange: (draft: EditDraft) => void;
  onClose: () => void;
  onRestore: () => void;
  onSave: () => void;
}) {
  return (
    <ModalShell label="编辑线路信息">
      <ModalHeader title="编辑线路信息" onClose={onClose}>
        <p>修改线路的客户归属与显示信息</p>
      </ModalHeader>
      <div className="line-edit-layout">
        <form className="line-edit-form" onSubmit={(event) => { event.preventDefault(); onSave(); }}>
          <label><span>线路名称 *</span><input value={draft.name} maxLength={50} onChange={(event) => onChange({ ...draft, name: event.target.value })} /><small>{draft.name.length}/50</small></label>
          <label><span>绑定客户 *</span><select value={draft.customer} onChange={(event) => onChange({ ...draft, customer: event.target.value })}><option>客户A</option><option>客户B</option><option>客户C</option><option>自己使用</option><option>未分配</option></select></label>
          <label><span>平台 *</span><select value={draft.platform} onChange={(event) => onChange({ ...draft, platform: event.target.value })}><option>Facebook</option><option>TikTok</option><option>YouTube</option><option>Meta</option><option>未设置</option></select></label>
          <fieldset>
            <legend>线路类型 *</legend>
            <button className={draft.kind === "direct" ? "selected" : ""} type="button" onClick={() => onChange({ ...draft, kind: "direct" })}>直连线路</button>
            <button className={draft.kind === "transit" ? "selected" : ""} type="button" onClick={() => onChange({ ...draft, kind: "transit" })}>中转线路</button>
          </fieldset>
          <fieldset className="radio-fieldset">
            <legend>主线/备用 *</legend>
            <label><input checked={draft.mode === "主线"} type="radio" onChange={() => onChange({ ...draft, mode: "主线" })} />主线</label>
            <label><input checked={draft.mode === "备用"} type="radio" onChange={() => onChange({ ...draft, mode: "备用" })} />备用</label>
          </fieldset>
          <label><span>线路用途 *</span><select value={draft.purpose} onChange={(event) => onChange({ ...draft, purpose: event.target.value })}><option>主用线路</option><option>备用线路</option><option>测试线路</option><option>看视频 / 日常使用</option></select></label>
          <label><span>备注</span><textarea value={draft.note} maxLength={200} onChange={(event) => onChange({ ...draft, note: event.target.value })} /><small>{draft.note.length}/200</small></label>
        </form>
        <aside className="line-edit-side">
          <section className="line-modal-section bound-structure-card">
            <h4>绑定线路结构 <em>{line.kindLabel}</em></h4>
            <div>
              <span><ProductIcon name={line.kind === "transit" ? "servers" : "server"} tone={line.kind === "transit" ? "purple" : "blue"} />{line.kind === "transit" ? line.transitLabel : line.regionLabel}</span>
              <b>→</b>
              <span><ProductIcon name="platform" tone="blue" />目标网络</span>
            </div>
            <dl>
              <dt>线路 ID</dt><dd>LL-{line.id.slice(-8).toUpperCase()}</dd>
              <dt>出口 IP</dt><dd>{line.entryHost}</dd>
              <dt>当前状态</dt><dd className={line.health === "normal" ? "ok-text" : "issue-text"}>{line.statusLabel}</dd>
            </dl>
          </section>
          <section className="line-modal-section display-settings-card">
            <h4>显示设置</h4>
            {["在列表高亮显示异常", "在详情显示连接信息按钮", "启用监测提醒"].map((item) => (
              <label key={item}><span>{item}<small>{item === "启用监测提醒" ? "异常时通过系统内提醒通知" : "发生异常时在列表中高亮显示"}</small></span><input defaultChecked type="checkbox" /></label>
            ))}
          </section>
          <section className="line-modal-section edit-help-card">
            <h4>填写说明</h4>
            <p>绑定客户后，该线路将归属于所选客户，可在客户视图中查看。</p>
            <p>主线用于主要业务承载，备用线路仅在主线不可用时启用。</p>
            <p>启用监测提醒可在发生异常时及时收到系统通知。</p>
          </section>
        </aside>
      </div>
      <div className="customer-modal-actions">
        <button className="secondary" type="button" onClick={onClose}>取消</button>
        <button className="secondary" type="button" onClick={onRestore}>恢复默认</button>
        <button type="button" onClick={onSave}>保存修改</button>
      </div>
    </ModalShell>
  );
}

function LineClientInfoModal({
  line,
  onClose,
  onCopy,
  onToggleReveal,
  revealed,
}: {
  line: CustomerLine;
  onClose: () => void;
  onCopy: (value: string, label: string) => void;
  onToggleReveal: () => void;
  revealed: boolean;
}) {
  const masked = maskConnection(line, revealed);
  return (
    <ModalShell label="客户端连接信息">
      <ModalHeader title="客户端连接信息" onClose={onClose}>
        <span className="manual-view-badge">仅手动查看</span>
      </ModalHeader>
      <div className="client-info-summary">
        <span><small>线路名称</small><strong>{line.name}</strong></span>
        <span><ProductIcon name="user" tone="slate" /><small>客户</small><strong>{line.customer}</strong></span>
        <span><PlatformIcon platform={line.platform} /><small>平台</small><strong>{line.platform}</strong></span>
        <span><small>当前状态</small><b className={`line-health-pill ${healthTone(line.health)}`}>{line.statusLabel}</b></span>
      </div>
      <div className="client-info-layout">
        <section className="line-modal-section">
          <h4>连接摘要</h4>
          <div className="client-field-list">
            <span>服务器地址<strong>{line.entryHost}</strong><button type="button" onClick={() => void onCopy(line.entryHost, "服务器地址")}>复制</button></span>
            <span>客户连接端口<strong>{line.entryPort ?? "-"}</strong><button type="button" onClick={() => void onCopy(String(line.entryPort ?? ""), "端口")}>复制</button></span>
            <span>协议<strong>TLS</strong></span>
            <span>平台<strong>{line.platform}</strong></span>
            <span>线路类型<strong>{line.kindLabel}</strong></span>
          </div>
          <h4>连接内容</h4>
          <div className="masked-connection-box">
            <p>{masked}</p>
            <button aria-label={revealed ? "隐藏连接内容" : "显示连接内容"} type="button" onClick={onToggleReveal}>
              <ProductIcon name="eye" tone="slate" />
            </button>
          </div>
          <div className="client-copy-actions">
            <button type="button" onClick={() => void onCopy(masked, "连接信息")}>复制连接信息</button>
            <button className="secondary" type="button" onClick={() => void onCopy(line.entryHost, "服务器地址")}>复制服务器地址</button>
            <button className="secondary" type="button" onClick={() => void onCopy(String(line.entryPort ?? ""), "端口")}>复制端口</button>
          </div>
          <div className="client-note-box">
            <strong>备用说明</strong>
            <p>当前为{line.mode}。如需切换到备用线，请在客户端或应用内操作，切换后将自动恢复连接。</p>
          </div>
        </section>
        <aside>
          <section className="line-modal-section qr-section">
            <h4>扫码导入</h4>
            <div className="fake-qr" aria-hidden="true">
              {Array.from({ length: 49 }).map((_, index) => <i key={index} />)}
            </div>
            <p>支持客户端扫码快速导入配置。</p>
          </section>
          <section className="line-modal-section usage-note-section">
            <h4>使用说明</h4>
            <ul>
              <li>此信息仅用于交接或自助使用，请妥善保管。</li>
              <li>不建议在公共场所泄露或分享。</li>
              <li>此信息不会在客户线路列表中直接展示。</li>
            </ul>
          </section>
        </aside>
      </div>
      <div className="customer-modal-actions">
        <button className="secondary" type="button" onClick={onClose}>关闭</button>
        <button type="button" onClick={() => void onCopy(masked, "连接信息")}>复制连接信息</button>
      </div>
    </ModalShell>
  );
}

function LineMonitorModal({
  line,
  onClose,
  onDemoAction,
  onOpenDetail,
}: {
  line: CustomerLine;
  onClose: () => void;
  onDemoAction: (label: string) => void;
  onOpenDetail: () => void;
}) {
  const riskMode = line.health !== "normal";
  return (
    <ModalShell label="线路监测详情">
      <ModalHeader title="线路监测详情" onClose={onClose}>
        <span className={`line-health-pill ${healthTone(line.health)}`}>{line.statusLabel}</span>
      </ModalHeader>
      <div className="monitor-summary-grid">
        <MonitorCard icon="shield" label="当前状态" value={line.statusLabel} detail="检测时间：今天 16:10" tone={productTone(line.health)} />
        <MonitorCard icon="clock" label="延迟" value={riskMode ? "128 ms" : "28 ms"} detail={riskMode ? "较昨日 +28 ms" : "表现稳定"} tone={riskMode ? "orange" : "green"} />
        <MonitorCard icon="activity" label="抖动" value={riskMode ? "36 ms" : "3 ms"} detail={riskMode ? "较昨日 +12 ms" : "表现稳定"} tone={riskMode ? "blue" : "green"} />
        <MonitorCard icon="alert" label="丢包" value={riskMode ? "1.25 %" : "0 %"} detail={riskMode ? "较昨日 +0.75 %" : "表现稳定"} tone={riskMode ? "red" : "green"} />
      </div>
      <div className="monitor-detail-layout">
        <div>
          <section className="line-modal-section monitor-checks">
            <h4>检测结果</h4>
            {[
              ["入口连通", "正常", "延迟 38 ms"],
              [line.kind === "transit" ? "中转服务器" : "直连入口", riskMode ? "异常" : "正常", riskMode ? "延迟 128 ms" : "延迟 28 ms"],
              ["落地服务器", "正常", "延迟 42 ms"],
              ["出口平台", "正常", "延迟 65 ms"],
            ].map(([name, status, detail]) => (
              <span key={name} className={status === "异常" ? "warn" : ""}>
                <i />{name}<b>{status}</b><small>{detail}</small>
              </span>
            ))}
            <strong className={riskMode ? "issue-text" : "ok-text"}>{riskMode ? "综合结论：存在中等风险" : "综合结论：线路运行正常"}</strong>
          </section>
          <section className="line-modal-section monitor-alerts">
            <h4>最近告警 <button type="button">查看全部</button></h4>
            {(riskMode ? ["中转服务器延迟偏高", "中转链路丢包率上升"] : ["当前无新的异常告警"]).map((item, index) => (
              <span key={item}><ProductIcon name="alert" tone={riskMode ? "orange" : "green"} />{item}<small>{index ? "今天 15:42" : "今天 16:10"}</small></span>
            ))}
          </section>
          <section className="line-modal-section trend-card">
            <h4>最近 24 小时延迟趋势</h4>
            <div className="trend-chart">
              {Array.from({ length: 24 }).map((_, index) => <i key={index} style={{ height: `${riskMode ? 18 + index * 2 : 28 + (index % 4) * 3}px` }} />)}
            </div>
          </section>
        </div>
        <aside>
          <section className="line-modal-section problem-card">
            <h4>问题定位</h4>
            <div className={riskMode ? "problem-warning" : "problem-ok"}>
              <ProductIcon name={riskMode ? "alert" : "shield"} tone={riskMode ? "orange" : "green"} />
              <strong>{riskMode ? "问题定位：中转服务器存在异常" : "当前未发现明显异常"}</strong>
              <p>{riskMode ? "检测到中转服务器延迟和丢包率较高，可能由中转端口未放行、网络拥塞或服务器负载过高导致。" : "入口、落地和出口平台均表现正常，可继续观察。"}</p>
              <button type="button">查看诊断详情 ›</button>
            </div>
          </section>
          <section className="line-modal-section suggestion-card">
            <h4>建议操作</h4>
            {["检查中转服务器防火墙/安全组", "切换至备用线路验证", "优化出口网络或更换出口节点"].map((item) => (
              <button key={item} type="button" onClick={() => onDemoAction(item)}>
                <ProductIcon name="shield" tone="blue" />{item}<span>›</span>
              </button>
            ))}
          </section>
          <section className="line-modal-section related-lines-card">
            <h4>相关线路（同一客户）</h4>
            <table>
              <tbody>
                <tr><td>{line.name}</td><td>{line.mode}</td><td>{line.statusLabel}</td><td>{riskMode ? "128 ms" : "28 ms"}</td></tr>
                <tr><td>{line.customer}-备用线</td><td>备用</td><td>正常</td><td>42 ms</td></tr>
              </tbody>
            </table>
          </section>
        </aside>
      </div>
      <div className="customer-modal-actions">
        <button className="secondary" type="button" onClick={onClose}>关闭</button>
        <button className="secondary" type="button" onClick={onOpenDetail}>查看线路详情</button>
        <button type="button" onClick={() => onDemoAction("重新检测（演示）")}>重新检测（演示）</button>
      </div>
    </ModalShell>
  );
}

function MonitorCard({
  detail,
  icon,
  label,
  tone,
  value,
}: {
  detail: string;
  icon: string;
  label: string;
  tone: "blue" | "green" | "orange" | "red";
  value: string;
}) {
  return (
    <article className="monitor-card">
      <ProductIcon name={icon} tone={tone} />
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}
