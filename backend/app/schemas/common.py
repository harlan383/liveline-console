from fastapi.responses import JSONResponse


def success_response(data: dict | None = None, message: str = "ok") -> dict:
    return {
        "success": True,
        "data": data or {},
        "message": message,
    }


def error_response(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error_code": error_code,
            "message": message,
        },
    )
