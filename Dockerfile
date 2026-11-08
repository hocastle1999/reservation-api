# 예약 API 운영 이미지. Docker를 지원하는 어느 플랫폼에서나 같은 이미지로 돈다.
# (Fly.io, Railway, Koyeb, Cloud Run, AWS ECS, 일반 VPS 등. 설정은 환경 변수로 넣는다)
#
#   docker build -t reservation-api .
#   docker run -p 8000:8000 --env-file prod.env reservation-api
#
# 필요한 환경 변수는 README의 "배포 → 환경 변수" 표를 참고한다.

# 로컬, CI와 같은 Python 3.11. slim: 운영에 필요 없는 빌드 도구를 뺀 작은 이미지.
# bookworm까지 적어서 기반 OS가 예고 없이 바뀌지 않게 한다.
FROM python:3.11-slim-bookworm

# PYTHONDONTWRITEBYTECODE: 컨테이너 안에 .pyc를 만들지 않는다 (어차피 다시 시작하면 사라짐).
# PYTHONUNBUFFERED: 로그를 버퍼에 모으지 않고 바로 내보낸다. 안 그러면 플랫폼 로그에
#   늦게 보이거나, 컨테이너가 죽을 때 마지막 로그가 사라진다.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 의존성을 소스보다 먼저 설치한다. Docker는 단계(레이어)별로 결과를 저장해 두므로,
# requirements.txt가 그대로면 소스만 바꿔 다시 빌드할 때 설치 단계를 건너뛴다.
# 운영용 requirements.txt만 설치한다. (pytest, ruff 같은 개발 도구는 넣지 않는다)
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app
COPY scripts/start.sh ./scripts/start.sh

# root가 아닌 전용 사용자로 실행한다. 앱에 취약점이 있어도 컨테이너 안에서
# 할 수 있는 일을 줄인다. 앱은 파일을 쓰지 않으므로 소스 소유자를 바꿀 필요가 없다.
RUN useradd --system --no-create-home --uid 10001 app
USER app

# 많은 플랫폼이 PORT 환경 변수로 포트를 알려 준다. 없으면 8000을 쓴다.
ENV PORT=8000
EXPOSE 8000

# 컨테이너 상태 확인. slim 이미지에는 curl이 없어서 파이썬으로 요청한다.
# DB를 보지 않는 /health를 쓴다. DB가 잠깐 끊겼다고 앱 컨테이너를 재시작하지 않게 하기 위해서다.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8000'), timeout=4)"

CMD ["sh", "scripts/start.sh"]
