from __future__ import annotations


def _clean_status(value: str | None) -> str:
    return (value or "").strip().lower()


def node_service_display_label(service_status: str | None) -> str:
    status = _clean_status(service_status)
    if status == "active":
        return "服务运行中"
    if status in {"inactive", "stopped"}:
        return "服务未运行"
    if status in {"failed", "error"}:
        return "服务异常"
    if status in {"unknown", ""}:
        return "服务状态未知"
    return service_status or "服务状态未知"


def node_connectivity_display_status(connectivity_status: str | None) -> str:
    status = _clean_status(connectivity_status)
    if status in {"connected", "success", "succeeded", "passed"}:
        return "connected"
    if status in {"failed", "error", "timeout"}:
        return "failed"
    if status == "not_checked":
        return "not_checked"
    if status in {"unknown", ""}:
        return "unknown"
    return connectivity_status or "unknown"


def node_connectivity_display_label(service_status: str | None, connectivity_status: str | None) -> str:
    service = _clean_status(service_status)
    display_status = node_connectivity_display_status(connectivity_status)
    if display_status == "not_checked" and service == "active":
        return "服务运行中，连接未检测"
    if display_status == "not_checked":
        return "连接未检测"
    if display_status == "connected":
        return "连接检测正常"
    if display_status == "failed":
        return "连接检测失败"
    if display_status == "unknown":
        return "连接状态未知"
    return connectivity_status or "连接状态未知"


def build_node_display_fields(service_status: str | None, connectivity_status: str | None) -> dict[str, str]:
    connectivity_label = node_connectivity_display_label(service_status, connectivity_status)
    return {
        "service_display_label": node_service_display_label(service_status),
        "connectivity_display_status": node_connectivity_display_status(connectivity_status),
        "connectivity_display_label": connectivity_label,
        "node_health_summary": connectivity_label,
    }
