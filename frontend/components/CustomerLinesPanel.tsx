"use client";

import { useEffect, useMemo, useState } from "react";
import QRCode from "react-qr-code";

import {
  apiFetch,
  type NodeData,
  type NodeListResult,
  type TransitResourceData,
  type TransitResourceListResult,
  type TransitRouteData,
  type TransitRouteListResult,
} from "@/lib/api";

type CustomerLine = {
  id: string;
  name: string;
  customer: string;
  platform: string;
  purpose: string;
  lineType: string;
  entry: string;
  target: string;
  status: string;
  configStatus: string;
  link: string | null;
  detail: string;
};

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

function classifyPurpose(text: string) {
  if (/主线/i.test(text)) {
    return "主线";
  }
  if (/备用/i.test(text)) {
    return "备用";
  }
  if (/测试/i.test(text)) {
    return "测试";
  }
  if (/视频|日常/i.test(text)) {
    return "日常";
  }
  return "未设置";
}

function entry(host: string | null | undefined, port: number | null | undefined) {
  if (!host) {
    return "未返回";
  }
  return port ? `${host}:${port}` : host;
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    active: "已启用",
    creating: "创建中",
    failed: "异常",
    deleted: "已删除",
  };
  return labels[status] ?? status;
}

function lineFromNode(node: NodeData): CustomerLine {
  const text = [node.node_name, node.vps_ip, node.reality_server_name, node.reality_dest].filter(Boolean).join(" ");
  const link = node.share_link ?? null;
  return {
    id: `node-${node.id}`,
    name: node.node_name,
    customer: classifyCustomer(text),
    platform: classifyPlatform(text),
    purpose: classifyPurpose(text),
    lineType: "直连节点",
    entry: entry(node.vps_ip, node.port),
    target: entry(node.vps_ip, node.port),
    status: statusLabel(node.status),
    configStatus: node.share_link_present || node.has_share_link || link ? "客户端配置：已生成" : "客户端配置：未生成",
    link,
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
  return {
    id: `route-${route.id}`,
    name: route.name,
    customer: classifyCustomer(text),
    platform: classifyPlatform(text),
    purpose: classifyPurpose(text),
    lineType: resource?.resource_type === "server" ? "自建中转线路" : "商家中转线路",
    entry: entry(resource?.entry_host, route.listen_port),
    target: entry(route.target_host, route.target_port),
    status: statusLabel(route.status),
    configStatus: route.share_link ? "客户端配置：已生成" : "客户端配置：未保存，可临时导出",
    link: route.share_link,
    detail: "经中转入口访问落地节点。正式线路状态不在本阶段变更。",
  };
}

export function CustomerLinesPanel() {
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [routes, setRoutes] = useState<TransitRouteData[]>([]);
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [selectedLine, setSelectedLine] = useState<CustomerLine | null>(null);
  const [qrLine, setQrLine] = useState<CustomerLine | null>(null);
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

  const groupedLines = useMemo(() => {
    return customerLines.reduce<Record<string, CustomerLine[]>>((groups, line) => {
      groups[line.customer] = [...(groups[line.customer] ?? []), line];
      return groups;
    }, {});
  }, [customerLines]);

  async function copyLine(line: CustomerLine) {
    if (!line.link) {
      setMessage("当前列表没有完整客户端链接；请到线路详情或高级调试中按需导出。");
      return;
    }
    await navigator.clipboard.writeText(line.link);
    setMessage("客户端链接已复制。");
  }

  return (
    <section className="customer-workspace wide">
      <div className="workspace-hero">
        <div>
          <h2>客户线路</h2>
          <p>按客户和用途查看当前可用线路。客户分组来自线路名称和备注，不新增客户数据库。</p>
        </div>
        <button className="secondary" type="button" onClick={() => void loadData()}>
          刷新
        </button>
      </div>

      {customerLines.length === 0 ? (
        <div className="empty">暂无可用客户线路。可先到“线路搭建”查看下一步入口。</div>
      ) : (
        <div className="customer-line-groups">
          {Object.entries(groupedLines).map(([customerName, lines]) => (
            <section className="customer-line-group" key={customerName}>
              <div className="status-row">
                <h2>{customerName}</h2>
                <span className="pill muted">{lines.length} 条线路</span>
              </div>
              <div className="customer-line-grid">
                {lines.map((line) => (
                  <article className="customer-line-card" key={line.id}>
                    <div className="line-card-title">
                      <div>
                        <strong>{line.name}</strong>
                        <span>{line.lineType}</span>
                      </div>
                      <span className="pill ok">{line.status}</span>
                    </div>
                    <div className="business-detail-grid compact">
                      <span>平台</span>
                      <strong>{line.platform}</strong>
                      <span>用途</span>
                      <strong>{line.purpose}</strong>
                      <span>入口地址</span>
                      <strong>{line.entry}</strong>
                      <span>客户端配置</span>
                      <strong>{line.configStatus.replace("客户端配置：", "")}</strong>
                    </div>
                    <div className="line-card-actions">
                      <button className="secondary" type="button" onClick={() => setSelectedLine(line)}>
                        查看详情
                      </button>
                      <button className="secondary" disabled={!line.link} type="button" onClick={() => void copyLine(line)}>
                        复制链接
                      </button>
                      <button className="secondary" disabled={!line.link} type="button" onClick={() => setQrLine(line)}>
                        显示二维码
                      </button>
                      <button disabled type="button">
                        切换备用
                      </button>
                      <button disabled type="button">
                        新建备用线
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

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
              <span>用途</span>
              <strong>{selectedLine.purpose}</strong>
              <span>线路类型</span>
              <strong>{selectedLine.lineType}</strong>
              <span>入口地址</span>
              <strong>{selectedLine.entry}</strong>
              <span>目标落地</span>
              <strong>{selectedLine.target}</strong>
              <span>状态</span>
              <strong>{selectedLine.status}</strong>
              <span>客户端配置</span>
              <strong>{selectedLine.configStatus.replace("客户端配置：", "")}</strong>
            </div>
            <p className="message">{selectedLine.detail}</p>
          </div>
        </div>
      ) : null}

      {qrLine?.link ? (
        <div className="modal-backdrop" role="presentation">
          <div className="modal-card customer-line-modal">
            <div className="modal-header">
              <h3>临时二维码</h3>
              <button className="modal-close-button" type="button" onClick={() => setQrLine(null)}>
                ×
              </button>
            </div>
            <div className="qr-frame">
              <QRCode value={qrLine.link} size={220} />
            </div>
            <p className="message">二维码仅在浏览器中生成，不保存到后端。</p>
          </div>
        </div>
      ) : null}
    </section>
  );
}
