from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import auth_error, require_admin_session
from app.db.session import get_db
from app.models.task import Task
from app.models.task_log import TaskLog
from app.schemas.common import error_response, success_response
from app.services.redaction import redact_sensitive_payload, redact_text

router = APIRouter()


def serialize_task(task: Task) -> dict:
    return {
        "id": task.id,
        "vps_id": task.vps_id,
        "node_id": task.node_id,
        "task_type": task.task_type,
        "status": task.status,
        "current_step": task.current_step,
        "progress": task.progress,
        "error_code": task.error_code,
        "error_message": redact_text(task.error_message) if task.error_message else None,
        "result_data": redact_sensitive_payload(task.result_data),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def serialize_task_log(log: TaskLog) -> dict:
    return {
        "id": log.id,
        "task_id": log.task_id,
        "level": log.level,
        "step": log.step,
        "message": redact_text(log.message),
        "raw_output": redact_text(log.raw_output) if log.raw_output else None,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


@router.get("")
def list_tasks(
    request: Request,
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    if not require_admin_session(db, request):
        return auth_error()

    tasks = db.scalars(select(Task).order_by(Task.created_at.desc()).limit(limit)).all()
    return success_response({"tasks": [serialize_task(task) for task in tasks]}, "ok")


@router.get("/{task_id}")
def get_task(task_id: str, request: Request, db: Session = Depends(get_db)):
    if not require_admin_session(db, request):
        return auth_error()

    task = db.get(Task, task_id)
    if not task:
        return error_response(404, "TASK_NOT_FOUND", "任务不存在。")

    return success_response(serialize_task(task), "ok")


@router.get("/{task_id}/logs")
def get_task_logs(task_id: str, request: Request, db: Session = Depends(get_db)):
    if not require_admin_session(db, request):
        return auth_error()

    task = db.get(Task, task_id)
    if not task:
        return error_response(404, "TASK_NOT_FOUND", "任务不存在。")

    logs = db.scalars(
        select(TaskLog).where(TaskLog.task_id == task_id).order_by(TaskLog.created_at.asc())
    ).all()
    return success_response({"logs": [serialize_task_log(log) for log in logs]}, "ok")
