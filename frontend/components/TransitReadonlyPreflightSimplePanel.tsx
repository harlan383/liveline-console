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

type CheckView = {
  id: string;
  label: string;
  status: string;
  passed: boolean;
  detail: string;
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

function preflightOverallState(command: WorkerCommandData | null) {
  if (!command) {
    return {
      className: "muted",
      label: "未开始",
      description: "尚未创建远程只读预检命令。",
    };
  }

  if (["pending", "claimed", "running"].includes(command.status)) {
    return {
      className: "warn",
      label: "运行中",
      description: "Worker command 已创建，等待固定只读检查返回结果。",
    };
  }

  if (["failed", "expired", "cancelled"].includes(command.status)) {
    return {
      className: "bad",
      label: "失败",
      description: "Worker command 未成功完成，请先查看错误摘要，不要进入真实创建。",
    };
  }

  const result = objectValue(command.result_json);
  if (command.status === "succeeded" && result?.passed === true) {
    return {
      className: "ok",
      label: "通过",
      description: "固定只读检查已通过；这仍不代表可以创建真实转发。",
    };
  }

  if (command.status === "succeeded") {
    return {
      className: "warn",
      label: "需要人工处理",
      description: "只读检查已完成，但存在未通过项，需要先处理或重新规划。",
    };
  }

  return {
    className: "warn",
    label: workerCommandStatusLabel(command.status),
    description: "命令状态尚未归类，请刷新或查看任务详情。",
  };
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

function checksFromCommand(command: WorkerCommandData | null): CheckView[] {
  const result = objectValue(command?.result_json);
  const checks = Array.isArray(result?.checks) ? result.checks : [];
  return checks.map((item, index) => {
    const check = objectValue(item);
    return {
      id: stringValue(check, "id") === "-" ? `check_${index + 1}` : stringValue(check, "id"),
      label: stringValue(check, "label") === "-" ? `检查项 ${index + 1}` : stringValue(check, "label"),
      status: stringValue(check, "status"),
      passed: check?.passed === true,
      detail: stringValue(check, "detail"),
    };
  });
}

function actionForFailedCheck(check: CheckView) {
  const id = check.id.toLowerCase();
  if (id.includes("port")) {
    return "确认计划监听端口未被占用；如被占用，换一个新端口并同步检查云安全组 / 云防火墙 / 服务器防火墙。";
  }
  if (id.includes("reachability") || id.includes("tcp") || id.includes("connectivity")) {
    return "检查中转服务器到落地节点目标端口的 TCP 可达性，并确认落地节点服务和防火墙状态。";
  }
  if (id.includes("worker")) {
    return "确认目标 Worker 在线、角色为 transit、版本满足只读预检要求。";
  }
  if (id.includes("socat") || id.includes("gost")) {
    return "查看只读状态摘要；不要在本阶段启动、停止、重启或改写 socat / gost。";
  }
  if (id.includes("firewall")) {
    return "人工核对云安全组、云防火墙和服务器本机防火墙，确认只读预检没有发现明显阻塞。";
  }
  return "保留当前 No-Go 状态，查看脱敏详情并处理后再重新执行只读预检。";
}

function failureSummaries(command: WorkerCommandData | null, checks: CheckView[]) {
  if (!command) {
    return ["尚未执行远程只读预检。"];
  }
  if (command.error_message) {
    return [command.error_message];
  }
  const failedChecks = checks.filter((check) => !check.passed);
  if (failedChecks.length > 0) {
    return failedChecks.map((check) => `${check.label}：${check.detail}`);
  }
  return ["暂无失败项。"];
}

function manualActions(command: WorkerCommandData | null, checks: CheckView[]) {
  if (!command) {
    return ["完成本地计划确认后，点击“执行远程只读预检”。"];
  }
  if (["pending", "claimed", "running"].includes(command.status)) {
    return ["等待 Worker 返回结果，或稍后点击“刷新结果”。"];
  }
  if (["failed", "expired", "cancelled"].includes(command.status)) {
    return ["先查看命令错误，不要进入真实创建；必要时确认 Worker 在线后重新执行只读预检。"];
  }
  const failedChecks = checks.filter((check) => !check.passed);
  if (failedChecks.length > 0) {
    return failedChecks.map(actionForFailedCheck);
  }
  return ["只读预检通过后仍需单独进入真实创建审批；本页面不会创建真实转发。"];
}

function renderRemoteCommandResult(command: WorkerCommandData | null) {
  const state = preflightOverallState(command);
  const checks = checksFromCommand(command);
  const failures = failureSummaries(command, checks);
  const actions = Array.from(new Set(manualActions(command, checks)));

  if (!command) {
    return (
      <div className="readonly-result-panel">
        <div className="readonly-result-header">
          <div>
            <p className="eyebrow">预检结果</p>
            <h4>{state.label}</h4>
            <span>{state.description}</span>
          </div>
          <span className={`pill ${state.className}`}>{state.label}</span>
        </div>
        <div className="readonly-result-columns">
          <div className="readonly-result-box">
            <strong>失败原因摘要</strong>
            {failures.map((failure) => (
              <span key={failure}>{failure}</span>
            ))}
          </div>
          <div className="readonly-result-box">
            <strong>建议人工动作</strong>
            {actions.map((action) => (
              <span key={action}>{action}</span>
            ))}
          </div>
        </div>
        <div className="readonly-result-boundary">
          <strong>安全边界</strong>
          <span>只读预检不会创建真实转发，不会新增监听端口，不会修改防火墙或 nodes.share_link。</span>
        </div>
      </div>
    );
  }

  const result = objectValue(command.result_json);
  const summary = stringValue(result, "summary");
  const redactedSummary = stringValue(result, "redacted_summary");

  return (
    <div className="readonly-result-panel">
      <div className="readonly-result-header">
        <div>
          <p className="eyebrow">预检结果</p>
          <h4>{state.label}</h4>
          <span>{state.description}</span>
        </div>
        <span className={`pill ${state.className}`}>{state.label}</span>
      </div>
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

      <div className="readonly-result-columns">
        <div className="readonly-result-box">
          <strong>失败原因摘要</strong>
          {failures.map((failure) => (
            <span key={failure}>{failure}</span>
          ))}
        </div>
        <div className="readonly-result-box">
          <strong>建议人工动作</strong>
          {actions.map((action) => (
            <span key={action}>{action}</span>
          ))}
        </div>
      </div>

      {checks.length > 0 ? (
        <div className="readonly-simple-checks">
          <h4>检查项列表</h4>
          {checks.map((check) => (
            <div className="readonly-simple-check" key={check.id}>
              <div>
                <strong>{check.label}</strong>
                <span>{check.id}</span>
              </div>
              <span className={`pill ${check.passed ? "ok" : "bad"}`}>{check.passed ? "通过" : "失败"}</span>
              <p>{check.detail}</p>
            </div>
          ))}
        </div>
      ) : null}
      {redactedSummary !== "-" ? (
        <pre className="local-plan-output">{redactedSummary}</pre>
      ) : null}
      <div className="readonly-result-boundary">
        <strong>安全边界</strong>
        <span>该结果来自固定 allowlist 只读检查；不会安装、启动、停止或重启 socat / gost。</span>
        <span>不会绑定监听端口，不会修改防火墙、Xray、nodes.share_link，也不会生成或展示真实客户端链接。</span>
      </div>
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
