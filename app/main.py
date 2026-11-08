import logging

from fastapi import FastAPI

from app.api import auth, health, reservations, resources
from app.core.exceptions import register_exception_handlers

# 앱 로거(app.*)의 경고를 어느 모듈에서 났는지와 함께 표준 오류로 내보낸다.
# uvicorn은 자기 로거만 설정하므로, 이걸 안 하면 데드락 재시도 경고 같은 앱 로그가
# 수준과 출처 없이 메시지만 찍힌다. 시각은 배포 환경(Render)의 로그 수집기가 붙인다.
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Reservation API", version="0.1.0")

register_exception_handlers(app)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(resources.router)
app.include_router(reservations.router)
