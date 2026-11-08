#!/bin/sh
# 운영 환경 시작 스크립트. Docker 이미지(Dockerfile)와 Render(render.yaml)가 같이 쓴다.
# 시작 명령을 한 곳에만 두어야 배포 환경마다 실행 방식이 어긋나지 않는다.
#
# 1) DB 마이그레이션을 적용한다. (RUN_MIGRATIONS=false면 건너뛴다)
# 2) uvicorn을 실행한다.
#
# 인스턴스를 여러 개 띄우는 환경에서는 RUN_MIGRATIONS=false로 두고, 플랫폼의
# "배포 전 명령"(release command, pre-deploy 등)에서 `python -m alembic upgrade head`를
# 한 번만 실행한다. Alembic은 마이그레이션이 동시에 두 번 도는 것을 막아 주지 않는다.
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "마이그레이션 적용: alembic upgrade head"
  python -m alembic upgrade head
fi

# exec: 셸 대신 uvicorn이 이 프로세스(컨테이너의 PID 1)를 이어받는다. 그래야 플랫폼이
# 종료할 때 보내는 SIGTERM을 uvicorn이 직접 받아, 처리 중인 요청을 마치고 꺼진다.
# --proxy-headers: 플랫폼의 프록시가 붙인 X-Forwarded-* 헤더로 실제 프로토콜과 클라이언트 IP를
# 알아낸다. 어느 프록시를 믿을지는 환경 변수 FORWARDED_ALLOW_IPS로 정한다(기본값 127.0.0.1).
exec python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers
