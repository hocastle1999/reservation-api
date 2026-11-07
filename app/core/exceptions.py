from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """서비스 계층에서 쓰는 예외의 기본 클래스.

    서비스 코드가 HTTPException을 직접 던지지 않는 이유: 서비스는 "무엇이 잘못됐는가"만
    알면 되고, 그걸 HTTP 상태 코드로 어떻게 바꿀지는 API 계층(아래 핸들러)이 정한다.
    그래야 서비스 함수를 HTTP 없이(배치 작업, 테스트 등) 그대로 재사용할 수 있다.
    """

    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        # FastAPI 기본 오류 응답과 같은 {"detail": ...} 형식을 쓴다.
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
