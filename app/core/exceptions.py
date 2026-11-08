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


class UnauthorizedError(AppError):
    """인증 실패 (로그인 안 함, 토큰이 잘못됨, 비밀번호 틀림)."""

    status_code = 401


class ForbiddenError(AppError):
    """인증은 됐지만 권한이 없음 (예: 일반 사용자가 관리자 기능 호출)."""

    status_code = 403


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class ServiceUnavailableError(AppError):
    """일시적으로 처리하지 못함. 같은 요청을 잠시 뒤 다시 보내면 성공할 수 있다."""

    status_code = 503


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        # FastAPI 기본 오류 응답과 같은 {"detail": ...} 형식을 쓴다.
        headers = None
        if isinstance(exc, UnauthorizedError):
            # 401 응답에는 어떤 방식으로 인증해야 하는지 알려 주는 헤더를 붙인다. (HTTP 표준)
            headers = {"WWW-Authenticate": "Bearer"}
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.detail}, headers=headers
        )
