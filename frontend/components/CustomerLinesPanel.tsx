"use client";

import { useEffect, useMemo, useState } from "react";

import { ProductIcon } from "@/components/ProductIcons";
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

type CustomerLine = {
  id: string;
  name: string;
  customer: string;
  platform: string;
  purpose: string;
  lineRole: string;
  lineType: string;
  entry: string;
  target: string;
  health: LineHealth;
  statusLabel: string;
  suggestion: string;
  lastIssue: string;
  configStatus: string;
  detail: string;
};

const healthTabs: Array<{ label: string; value: "all" | LineHealth }> = [
  { label: "全部", value: "all" },
  { label: "正常", value: "normal" },
  { label: "风险", value: "risk" },
  { label: "异常", value: "abnormal" },
];

function classifyCustomer(text: string) {
  if (/客户A/i.test(text)) {
    return "客户A";
  }
  if (/客户B/i.test(text)) {
    return "客户B";
  }
  if (/自己|自用/i.test(text)) {
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
  return "未设置";
}

function classifyRole(text: string) {
  if (/备用/i.test(text)) {
    return "备用";
  }
  if (/测试/i.test(text)) {
    return "测试";
  }
  return "主线";
}

function entry(host: string | null | undefined, port: number | null | undefined) {
  if (!host) {
    return "未返回";
  }
  return port ? `${host}:${port}` : host;
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
  if (status === "failed") {
    return "abnormal";
  }
  if (status !== "active" || !hasConfig) {
    return "risk";
  }
  return "normal";
}

function lineFromNode(node: NodeData): CustomerLine {
  const text = [node.node_name, node.vps_ip, node.reality_server_name, node.reality_dest].filter(Boolean).join(" ");
  const hasConfig = Boolean(node.share_link_present || node.has_share_link || node.masked_share_link);
  const health = healthFromStatus(node.status, hasConfig);
  return {
    id: `node-${node.id}`,
    name: node.node_name,
    customer: classifyCustomer(text),
    platform: classifyPlatform(text),
    purpose: classifyRole(text),
    lineRole: classifyRole(text),
    lineType: "直连节点",
    entry: entry(node.vps_ip, node.port),
    target: entry(node.vps_ip, node.port),
    health,
    statusLabel: healthLabel(health),
    suggestion: health === "normal" ? "可继续使用" : "建议检查服务状态和客户端配置",
    lastIssue: health === "normal" ? "-" : "最近状态未完全正常",
    configStatus: hasConfig ? "客户端配置：已生成" : "客户端配置：未生成",
    detail: "直连落地线路。服务状态和客户端配置来自当前节点记录。",
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
  const hasConfig = Boolean(route.share_link);
  const health = healthFromStatus(route.status, true);
  return {
    id: `route-${route.id}`,
    name: route.name,
    customer: classifyCustomer(text),
    platform: classifyPlatform(text),
    purpose: classifyRole(text),
    lineRole: classifyRole(text),
    lineType: resource?.resource_type === "server" ? "自建中转线路" : "商家中转线路",
    entry: entry(resource?.entry_host, route.listen_port),
    target: entry(route.target_host, route.target_port),
    health,
    statusLabel: healthLabel(health),
    suggestion: health === "normal" ? "可继续使用" : "建议检查客户连接端口",
    lastIssue: health === "normal" ? "-" : "中转状态需复核",
    configStatus: hasConfig ? "客户端配置：已生成" : "客户端配置：未保存，可临时导出",
    detail: "经中转入口访问落地节点。正式线路状态不在本阶段变更。",
  };
}

export function CustomerLinesPanel() {
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [routes, setRoutes] = useState<TransitRouteData[]>([]);
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [selectedLine, setSelectedLine] = useState<CustomerLine | null>(null);
  const [activeFilter, setActiveFilter] = useState<"all" | LineHealth>("all");
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("正在读取我的线路。");

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
        ? "我的线路已刷新。"
        : "部分线路数据暂时无法读取。",
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
    return [...activeRoutes, ...activeNodes].sort((a, b) => a.customer.localeCompare(b.customer) || a.name.localeCompare(b.name));
  }, [nodes, resources, routes]);

  const filteredLines = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return customerLines.filter((line) => {
      const matchesStatus = activeFilter === "all" || line.health === activeFilter;
      const searchable = `${line.name} ${line.customer} ${line.platform} ${line.lineType}`.toLowerCase();
      return matchesStatus && (!keyword || searchable.includes(keyword));
    });
  }, [activeFilter, customerLines, search]);

  const normalCount = customerLines.filter((line) => line.health === "normal").length;
  const riskCount = customerLines.filter((line) => line.health === "risk").length;
  const abnormalCount = customerLines.filter((line) => line.health === "abnormal").length;

  return (
    <section className="my-lines-page wide">
      <div className="product-page-header">
        <div>
          <h2>我的线路</h2>
          <p>按客户和用途查看可用线路，普通页面不会展示完整客户端链接。</p>
        </div>
        <button className="secondary" type="button" onClick={() => void loadData()}>
          刷新
        </button>
      </div>

      <div className="product-stat-grid three">
        <LineStat icon="lines" title="正常" value={normalCount} detail="可以继续使用" tone="success" />
        <LineStat icon="alert" title="风险" value={riskCount} detail="建议尽快检查" tone="warning" />
        <LineStat icon="alert" title="异常" value={abnormalCount} detail="需要处理" tone="danger" />
      </div>

      <div className="product-section-card">
        <div className="product-filter-bar">
          <div className="filter-tabs">
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
          <input
            aria-label="搜索线路"
            placeholder="搜索线路名称、客户或平台"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>

        <div className="product-table my-lines-table">
          <div className="product-table-row product-table-head">
            <span>线路名称</span>
            <span>分配给谁</span>
            <span>用途</span>
            <span>类型</span>
            <span>当前状态</span>
            <span>当前建议</span>
            <span>操作</span>
          </div>
          {filteredLines.length ? (
            filteredLines.map((line) => (
              <div className="product-table-row" key={line.id}>
                <strong>{line.name}</strong>
                <span>{line.customer}</span>
                <span>{line.platform} / {line.lineRole}</span>
                <span>{line.lineType}</span>
                <span className={`product-badge ${line.health === "normal" ? "success" : line.health === "risk" ? "warning" : "danger"}`}>
                  {line.statusLabel}
                </span>
                <span>{line.suggestion}</span>
                <button className="secondary" type="button" onClick={() => setSelectedLine(line)}>
                  查看详情
                </button>
              </div>
            ))
          ) : (
            <div className="product-empty-state inline">
              <ProductIcon name="lines" tone="blue" />
              <strong>还没有线路</strong>
              <p>你可以先去“线路搭建”创建第一条直连节点或中转线路。</p>
              <button type="button">去创建线路</button>
            </div>
          )}
        </div>
        <div className="product-pagination">
          <span>共 {filteredLines.length} 条</span>
          <button className="secondary" disabled type="button">上一页</button>
          <button type="button">1</button>
          <button className="secondary" disabled type="button">下一页</button>
        </div>
      </div>

      <p className="message">{message}</p>

      {selectedLine ? (
        <div className="modal-backdrop" role="presentation">
          <div className="modal-card customer-line-modal">
            <div className="modal-header">
              <h3>{selectedLine.name}</h3>
              <button className="modal-close-button" type="button" onClick={() => setSelectedLine(null)}>
                ×
              </button>
            </div>
            <div className="business-detail-grid">
              <span>客户</span>
              <strong>{selectedLine.customer}</strong>
              <span>平台</span>
              <strong>{selectedLine.platform}</strong>
              <span>主备</span>
              <strong>{selectedLine.lineRole}</strong>
              <span>线路类型</span>
              <strong>{selectedLine.lineType}</strong>
              <span>入口地址</span>
              <strong>{selectedLine.entry}</strong>
              <span>目标落地</span>
              <strong>{selectedLine.target}</strong>
              <span>状态</span>
              <strong>{selectedLine.statusLabel}</strong>
              <span>客户端配置</span>
              <strong>{selectedLine.configStatus.replace("客户端配置：", "")}</strong>
            </div>
            <div className="modal-actions compact-actions">
              <button className="secondary" type="button">复制链接</button>
              <button className="secondary" type="button">显示二维码</button>
              <button className="secondary" type="button">切换备用</button>
              <button type="button">测试线路</button>
            </div>
            <p className="message">{selectedLine.detail}</p>
          </div>
        </div>
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
    <article className={`product-stat-card ${tone}`}>
      <ProductIcon name={icon} tone={tone === "success" ? "green" : tone === "warning" ? "orange" : "red"} />
      <div>
        <span>{title}</span>
        <strong>{value}</strong>
      </div>
      <p>{detail}</p>
    </article>
  );
}
