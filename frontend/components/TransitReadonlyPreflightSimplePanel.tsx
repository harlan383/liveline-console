"use client";

import type { ReadonlyPreflightPlanResponse, WorkerCommandData } from "@/lib/api";

type TransitReadonlyPreflightSimplePanelProps = {
  ready: boolean;
  statusLabel: string;
  resourceName: string;
  nodeName: string;
  plannedListenPort: string;
  targetPort: string;
  issues: string[];
  healthConfirmed: boolean;
  boundaryConfirmed: boolean;
  workerBoundaryConfirmed: boolean;
  readonlyPreflightLoading: boolean;
  remotePreflightLoading: boolean;
  readonlyPreflightApiMessage: string;
  remotePreflightMessage: string;
  readonlyPreflightPlan: ReadonlyPreflightPlanResponse | null;
  remotePreflightCommand: WorkerCommandData | null;
  preflightSummaryCopied: boolean;
  onHealthConfirmedChange: (value: boolean) => void;
  onBoundaryConfirmedChange: (value: boolean) => void;
  onWorkerBoundaryConfirmedChange: (value: boolean) => void;
  onGeneratePlan: () => void;
  onRunCommand: () => void;
  onRefreshCommand: () => void;
  onCopySummary: () => void;
};

function workerCommandStatusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: "等待中",
    claimed: "已领取",
    running: "执行中",
    succeeded: "成功",
    failed: "失败",
    expired: "已过期",
    cancelled: "已取消",
  };
  return labels[status] ?? status;
}

function objectValue(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function stringValue(record: Record<string, unknown> | null, key: string) {
  const value = record?.[key];
  return typeof value === "string" && value ? value : "-";
}

function booleanLabel(value: boolean) {
  return value ? "是" : "否";
}

function commandPillClass(command: WorkerCommandData | null, ready: boolean) {
  if (command?.status === "succeeded") {
    return "ok";
  }
  if (command?.status === "failed") {
    return "bad";
  }
  return ready ? "ok" : "bad";
}

function renderRemoteCommandResult(command: WorkerCommandData | null) {
  if (!command) {
    return (
      <div className="readonly-simple-empty">
        <strong>尚未执行远程只读预检</strong>
        <span>确认本地规划和安全边界后，点击按钮创建 `transit_readonly_preflight` Worker command。</span>
      </div>
    );
  }

  const result = objectValue(command.result_json);
  const checks = Array.isArray(result?.checks) ? result.checks : [];
  const summary = stringValue(result, "summary");
  const redactedSummary = stringValue(result, "redacted_summary");

  return (
    <div className="readonly-simple-result">
      <div className="detail-grid">
        <span>Worker command</span>
        <strong>{command.id}</strong>
        <span>命令状态</span>
        <strong>{workerCommandStatusLabel(command.status)}</strong>
        <span>目标 Worker</span>
        <strong>{command.target_worker_id ?? "-"}</strong>
        <span>Worker 版本</span>
        <strong>{command.target_worker_version ?? "-"}</strong>
        <span>结果摘要</span>
        <strong>{summary}</strong>
      </div>
      {checks.length > 0 ? (
        <div className="readonly-simple-checks">
          {checks.map((item, index) => {
            const check = objectValue(item);
            const passed = check?.passed === true;
            const checkId = stringValue(check, "id");
            return (
              <div className="readonly-simple-check" key={`${checkId}-${index}`}>
                <div>
                  <strong>{stringValue(check, "label")}</strong>
                  <span>{checkId}</span>
                </div>
                <span className={`pill ${passed ? "ok" : "bad"}`}>{stringValue(check, "status")}</span>
                <p>{stringValue(check, "detail")}</p>
              </div>
            );
          })}
        </div>
      ) : null}
      {redactedSummary !== "-" ? (
        <pre className="local-plan-output">{redactedSummary}</pre>
      ) : null}
    </div>
  );
}

export function TransitReadonlyPreflightSimplePanel({
  ready,
  statusLabel,
  resourceName,
  nodeName,
  plannedListenPort,
  targetPort,
  issues,
  healthConfirmed,
  boundaryConfirmed,
  workerBoundaryConfirmed,
  readonlyPreflightLoading,
  remotePreflightLoading,
  readonlyPreflightApiMessage,
  remotePreflightMessage,
  readonlyPreflightPlan,
  remotePreflightCommand,
  preflightSummaryCopied,
  onHealthConfirmedChange,
  onBoundaryConfirmedChange,
  onWorkerBoundaryConfirmedChange,
  onGeneratePlan,
  onRunCommand,
  onRefreshCommand,
  onCopySummary,
}: TransitReadonlyPreflightSimplePanelProps) {
  const busy = readonlyPreflightLoading || remotePreflightLoading;

  return (
    <section className="readonly-simple-panel" aria-label="远程只读预检简化面板">
      <div className="readonly-simple-hero">
        <div>
          <p className="eyebrow">Worker allowlist</p>
          <h3>远程只读预检</h3>
          <p className="message">
            一个按钮创建 `transit_readonly_preflight` Worker command，只执行固定只读检查，不创建真实转发。
          </p>
        </div>
        <span className={`pill ${commandPillClass(remotePreflightCommand, ready)}`}>
          {remotePreflightCommand ? workerCommandStatusLabel(remotePreflightCommand.status) : statusLabel}
        </span>
      </div>

      <div className="readonly-simple-grid">
        <div className="readonly-simple-card">
          <h4>计划摘要</h4>
          <div className="detail-grid compact-detail-grid">
            <span>中转服务器</span>
            <strong>{resourceName || "-"}</strong>
            <span>落地节点</span>
            <strong>{nodeName || "-"}</strong>
            <span>计划监听端口</span>
            <strong>{plannedListenPort || "-"}</strong>
            <span>落地目标端口</span>
            <strong>{targetPort || "-"}</strong>
          </div>
          {issues.length > 0 ? (
            <div className="failure-box">
              <strong>尚不能执行</strong>
              {issues.slice(0, 5).map((issue) => (
                <span key={issue}>{issue}</span>
              ))}
              {issues.length > 5 ? <span>还有 {issues.length - 5} 项需要确认。</span> : null}
            </div>
          ) : (
            <div className="warning-box">
              <strong>已满足按钮执行条件</strong>
              <span>点击后仅创建只读 Worker command；不会创建转发链路，也不会改端口、防火墙或节点链接。</span>
            </div>
          )}
        </div>

        <div className="readonly-simple-card">
          <h4>执行前确认</h4>
          <div className="local-plan-checks simple-checks">
            <label className="check-row">
              <input
                checked={healthConfirmed}
                type="checkbox"
                onChange={(event) => onHealthConfirmedChange(event.target.checked)}
              />
              <span>本地 health 正常，pending / running tasks 为 0</span>
            </label>
            <label className="check-row">
              <input
                checked={boundaryConfirmed}
                type="checkbox"
                onChange={(event) => onBoundaryConfirmedChange(event.target.checked)}
              />
              <span>我确认不会创建真实转发、不会修改 node.share_link、不会 cutover</span>
            </label>
            <label className="check-row">
              <input
                checked={workerBoundaryConfirmed}
                type="checkbox"
                onChange={(event) => onWorkerBoundaryConfirmedChange(event.target.checked)}
              />
              <span>我确认只通过 Worker allowlist 执行固定只读检查，不接受任意 shell</span>
            </label>
          </div>
        </div>
      </div>

      <div className="readonly-simple-actions">
        <button
          className="secondary"
          disabled={readonlyPreflightLoading}
          type="button"
          onClick={onGeneratePlan}
        >
          {readonlyPreflightLoading ? "校验中" : "校验本地计划"}
        </button>
        <button
          className="primary readonly-simple-main-button"
          disabled={!ready || remotePreflightLoading}
          type="button"
          onClick={onRunCommand}
        >
          {remotePreflightLoading ? "只读预检执行中" : "执行远程只读预检"}
        </button>
        {remotePreflightCommand ? (
          <button
            className="secondary"
            disabled={busy}
            type="button"
            onClick={onRefreshCommand}
          >
            刷新结果
          </button>
        ) : null}
        <button className="secondary" type="button" onClick={onCopySummary}>
          {preflightSummaryCopied ? "摘要已复制" : "复制脱敏摘要"}
        </button>
      </div>

      <div className="readonly-simple-status">
        {readonlyPreflightApiMessage ? <p className="message">{readonlyPreflightApiMessage}</p> : null}
        {remotePreflightMessage ? <p className="message">{remotePreflightMessage}</p> : null}
        {readonlyPreflightPlan ? (
          <p className="message">
            后端 no-op 计划：{readonlyPreflightPlan.summary}；下一步：{readonlyPreflightPlan.next_action}
          </p>
        ) : null}
      </div>

      {renderRemoteCommandResult(remotePreflightCommand)}

      <div className="warning-box">
        <strong>只读预检安全边界</strong>
        <span>不会安装、启动、停止或重启 socat / gost；不会绑定监听端口；不会修改防火墙。</span>
        <span>不会修改 Xray、不会修改 nodes.share_link、不会导出完整客户端链接、不会 cutover。</span>
      </div>
    </section>
  );
}
