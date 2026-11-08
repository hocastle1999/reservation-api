"""중복 예약 방지 두 방식(lock, slot)의 부하 측정.

실행 (프로젝트 루트에서):
    .\\.venv\\Scripts\\python.exe -m scripts.benchmark_reservations
    .\\.venv\\Scripts\\python.exe -m scripts.benchmark_reservations --threads 64 --per-thread 30

무엇을 재는가:
- HTTP와 인증(JWT, Argon2)은 빼고 서비스 함수(reservation_service.create_reservation)를
  직접 호출한다. 두 방식의 차이는 DB 처리에만 있고, 나머지 계층은 똑같기 때문이다.
- 실제 요청처럼 예약 전에 같은 세션으로 사용자를 한 번 읽는다(get_current_user와 같은 순서).
- 스레드마다 자기 DB 연결로 요청을 연달아 보낸다. 모든 스레드는 동시에 출발한다.
- 끝나면 "확정 예약끼리 겹치지 않는가"를 다시 확인하고, 만든 데이터를 지운다.

주의: 테스트 DB(이름이 _test로 끝나는 DB)에서만 돈다. 측정 중 만든 데이터는 지우지만,
개발 DB를 실수로 건드리지 않도록 막아 둔다.
"""

import argparse
import itertools
import logging
import os
import platform
import random
import statistics
import sys
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

STRATEGIES = ("lock", "slot")
SLOT = timedelta(minutes=30)
# 측정용 예약은 먼 미래(2031년)에 만든다. 과거 시각은 예약할 수 없기 때문이다.
FUTURE_BASE = datetime(2031, 1, 6, 0, 0)
# 기존 예약 기록(--history)은 과거에 쌓는다.
HISTORY_BASE = datetime(2020, 1, 1, 0, 0)


@dataclass(frozen=True)
class Request:
    resource_index: int
    start: datetime  # UTC, naive
    slots: int  # 30분 칸 개수


# --- 시나리오 ---------------------------------------------------------------
# 각 함수는 스레드별 요청 목록을 돌려준다. rng로 만들어서 같은 seed면 같은 요청이 나온다.


def scenario_same_slot(threads: int, per_thread: int, rng: random.Random) -> list[list[Request]]:
    """모든 요청이 같은 자원의 같은 1시간. 최악의 경합. 1건만 성공해야 한다."""
    return [[Request(0, FUTURE_BASE, 2)] * per_thread for _ in range(threads)]


def scenario_disjoint(threads: int, per_thread: int, rng: random.Random) -> list[list[Request]]:
    """모든 요청이 같은 자원이지만 서로 겹치지 않는 30분. 모두 성공해야 한다.

    방법 A는 겹치지 않아도 자원 락에서 한 줄로 서고, 방법 B는 서로 기다리지 않는다.
    두 방식의 구조 차이가 가장 크게 드러나는 경우다.
    """
    starts = [FUTURE_BASE + SLOT * i for i in range(threads * per_thread)]
    rng.shuffle(starts)
    requests = [Request(0, start, 1) for start in starts]
    return [requests[i::threads] for i in range(threads)]


def scenario_random_one_day(
    threads: int, per_thread: int, rng: random.Random
) -> list[list[Request]]:
    """같은 자원, 하루(48칸) 안에서 무작위 시작, 길이 30분~2시간. 일부만 성공한다.

    여러 요청이 칸 일부씩 겹치는 경우가 많아서, 방법 B의 데드락 가능성을 확인하는 용도다.
    """
    return [
        [
            Request(0, FUTURE_BASE + SLOT * rng.randrange(44), rng.randint(1, 4))
            for _ in range(per_thread)
        ]
        for _ in range(threads)
    ]


def scenario_many_resources(
    threads: int, per_thread: int, rng: random.Random
) -> list[list[Request]]:
    """자원 20개에 고르게 퍼진 요청, 일주일 안에서 무작위. 경합이 적은 평소 상황."""
    return [
        [
            Request(
                rng.randrange(20), FUTURE_BASE + SLOT * rng.randrange(7 * 48 - 4), rng.randint(1, 4)
            )
            for _ in range(per_thread)
        ]
        for _ in range(threads)
    ]


SCENARIOS = {
    "same-slot": scenario_same_slot,
    "disjoint": scenario_disjoint,
    "random-one-day": scenario_random_one_day,
    "many-resources": scenario_many_resources,
}


# --- 실행 -------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--threads", type=int, default=32, help="동시에 요청하는 스레드 수")
    parser.add_argument("--per-thread", type=int, default=30, help="스레드 하나가 보내는 요청 수")
    parser.add_argument(
        "--history",
        type=int,
        default=0,
        help="측정 전에 자원 0에 쌓아 둘 과거 확정 예약 수 (기록이 많을 때의 성능 확인)",
    )
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument("--strategies", nargs="+", choices=STRATEGIES, default=list(STRATEGIES))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--db", default=os.environ.get("TEST_DB_NAME", "reservation_test"), help="측정할 DB"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.db.endswith("_test"):
        sys.exit(f"측정은 *_test DB에서만 실행한다 (현재: {args.db})")
    # 앱 모듈을 import하기 전에 DB 이름을 바꾼다. 설정과 엔진은 import 시점에 만들어진다.
    os.environ["DB_NAME"] = args.db

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from app.core.config import get_settings
    from app.db.session import create_app_engine

    command.upgrade(Config("alembic.ini"), "head")

    # 스레드마다 연결 하나. 풀이 모자라면 측정하려는 DB 대기 대신 풀 대기를 재게 된다.
    engine = create_app_engine(pool_size=args.threads + 2, max_overflow=0)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    # 준비 운동: 풀의 연결을 미리 모두 열어 둔다. 안 그러면 첫 요청들에 "DB 접속 시간"이
    # 섞여서 p95, p99가 부풀려진다.
    warm = [engine.connect() for _ in range(args.threads + 2)]
    for conn in warm:
        conn.execute(text("SELECT 1"))
    mysql_version = warm[0].execute(text("SELECT VERSION()")).scalar_one()
    for conn in warm:
        conn.close()

    print(
        f"MySQL {mysql_version}, Python {platform.python_version()}, "
        f"{platform.system()} {platform.release()}, CPU {os.cpu_count()}개"
    )
    print(
        f"threads={args.threads}, per_thread={args.per_thread}, "
        f"history={args.history}, seed={args.seed}\n"
    )
    print(
        "| 시나리오 | 방식 | 요청 | 성공 | 409 | 오류 | 데드락 | 처리량(건/초) "
        "| p50(ms) | p95(ms) | p99(ms) | 겹침 검증 |"
    )
    print("| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |")

    settings = get_settings()
    for scenario in args.scenarios:
        for strategy in args.strategies:
            settings.reservation_strategy = strategy
            # 두 방식이 같은 요청을 받도록 시나리오마다 같은 seed로 요청을 만든다.
            plan = SCENARIOS[scenario](args.threads, args.per_thread, random.Random(args.seed))
            row = run_once(session_factory, plan, args.history)
            print(f"| {scenario} | {strategy} | {row}")

    engine.dispose()


def run_once(session_factory, plan: list[list[Request]], history: int) -> str:
    from sqlalchemy.exc import OperationalError

    from app.core.exceptions import ConflictError, ServiceUnavailableError
    from app.core.time import to_kst
    from app.models import User
    from app.schemas.reservation import ReservationCreate
    from app.services import reservation_service

    threads = len(plan)
    resource_count = 1 + max(r.resource_index for reqs in plan for r in reqs)
    resource_ids, user_ids = setup(session_factory, resource_count, threads)
    try:
        if history:
            add_history(session_factory, resource_ids[0], user_ids[0], history)

        # 요청 객체는 측정 전에 미리 만든다. (입력 검증 시간은 두 방식이 같으므로 뺀다)
        payloads = [
            [
                ReservationCreate(
                    resource_id=resource_ids[r.resource_index],
                    start_at=to_kst(r.start),
                    end_at=to_kst(r.start + SLOT * r.slots),
                )
                for r in reqs
            ]
            for reqs in plan
        ]

        # 모든 스레드와 측정 스레드(main)가 함께 출발선에 선다.
        barrier = threading.Barrier(threads + 1)

        def worker(index: int) -> list[tuple[str, float]]:
            results = []
            barrier.wait()
            for data in payloads[index]:
                started = time.perf_counter()
                with session_factory() as db:
                    user = db.get(User, user_ids[index])
                    try:
                        reservation_service.create_reservation(db, user, data)
                        outcome = "created"
                    except ConflictError:
                        outcome = "conflict"
                    except ServiceUnavailableError:
                        outcome = "503"  # 데드락 재시도를 모두 실패
                    except OperationalError as exc:
                        # 1213: 데드락, 1205: 락 대기 시간 초과
                        outcome = f"mysql-{exc.orig.args[0]}"
                results.append((outcome, time.perf_counter() - started))
            return results

        deadlock_counter = DeadlockCounter()
        service_logger = logging.getLogger(reservation_service.__name__)
        service_logger.addHandler(deadlock_counter)
        try:
            with ThreadPoolExecutor(max_workers=threads) as pool:
                futures = [pool.submit(worker, i) for i in range(threads)]
                barrier.wait()
                started = time.perf_counter()
                results = [item for future in futures for item in future.result()]
                elapsed = time.perf_counter() - started
        finally:
            service_logger.removeHandler(deadlock_counter)

        overlap_ok = verify_no_overlap(session_factory, resource_ids, history)
    finally:
        cleanup(session_factory, resource_ids, user_ids)

    outcomes = Counter(outcome for outcome, _ in results)
    latencies_ms = sorted(seconds * 1000 for _, seconds in results)
    errors = ", ".join(
        f"{name} {count}"
        for name, count in outcomes.items()
        if name.startswith("mysql-") or name == "503"
    )
    q = statistics.quantiles(latencies_ms, n=100, method="inclusive")
    return (
        f"{len(results)} | {outcomes['created']} | {outcomes['conflict']} | {errors or '-'} "
        f"| {deadlock_counter.count} | {len(results) / elapsed:,.0f} | {q[49]:.1f} "
        f"| {q[94]:.1f} | {q[98]:.1f} | {'통과' if overlap_ok else '**실패**'} |"
    )


class DeadlockCounter(logging.Handler):
    """서비스가 데드락으로 재시도할 때 남기는 경고 로그를 센다.

    재시도에 성공하면 사용자에게는 보이지 않는 데드락도 여기서 잡힌다.
    (InnoDB 지표 INNODB_METRICS는 PROCESS 권한이 필요해서 앱 계정으로는 읽을 수 없다)
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.count = 0
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        with self._lock:
            self.count += 1


def setup(session_factory, resource_count: int, threads: int) -> tuple[list[int], list[int]]:
    from app.models import Resource, User

    run_id = uuid.uuid4().hex[:8]
    with session_factory() as db:
        resources = [
            Resource(name=f"bench-{run_id}-{i}", capacity=4) for i in range(resource_count)
        ]
        users = [
            User(email=f"bench-{run_id}-{i}@example.com", password_hash="unused", name="bench")
            for i in range(threads)
        ]
        db.add_all(resources + users)
        db.commit()
        return [r.id for r in resources], [u.id for u in users]


def add_history(session_factory, resource_id: int, user_id: int, count: int) -> None:
    """과거 확정 예약(1시간짜리)을 count개 넣는다. 방법 B를 위해 칸도 함께 넣는다."""
    from sqlalchemy import insert, select

    from app.models import Reservation, ReservationSlot

    with session_factory() as db:
        for chunk_start in range(0, count, 2000):
            rows = [
                {
                    "resource_id": resource_id,
                    "user_id": user_id,
                    "start_at": HISTORY_BASE + timedelta(hours=i),
                    "end_at": HISTORY_BASE + timedelta(hours=i + 1),
                }
                for i in range(chunk_start, min(chunk_start + 2000, count))
            ]
            db.execute(insert(Reservation), rows)
        db.flush()
        reservations = db.execute(
            select(Reservation.id, Reservation.start_at).where(
                Reservation.resource_id == resource_id
            )
        ).all()
        slots = [
            {"resource_id": resource_id, "slot_start": start + SLOT * k, "reservation_id": rid}
            for rid, start in reservations
            for k in range(2)
        ]
        for chunk_start in range(0, len(slots), 4000):
            db.execute(insert(ReservationSlot), slots[chunk_start : chunk_start + 4000])
        db.commit()


def verify_no_overlap(session_factory, resource_ids: list[int], history: int) -> bool:
    from sqlalchemy import select

    from app.models import Reservation, ReservationStatus

    with session_factory() as db:
        for resource_id in resource_ids:
            rows = db.execute(
                select(Reservation.start_at, Reservation.end_at)
                .where(
                    Reservation.resource_id == resource_id,
                    Reservation.status == ReservationStatus.CONFIRMED,
                )
                .order_by(Reservation.start_at)
            ).all()
            for (_, prev_end), (next_start, _) in itertools.pairwise(rows):
                if prev_end > next_start:
                    return False
    return True


def cleanup(session_factory, resource_ids: list[int], user_ids: list[int]) -> None:
    from sqlalchemy import delete

    from app.models import Reservation, Resource, User

    with session_factory() as db:
        # 칸(reservation_slots)은 외래키 ON DELETE CASCADE로 함께 지워진다.
        db.execute(delete(Reservation).where(Reservation.resource_id.in_(resource_ids)))
        db.execute(delete(Resource).where(Resource.id.in_(resource_ids)))
        db.execute(delete(User).where(User.id.in_(user_ids)))
        db.commit()


if __name__ == "__main__":
    # 측정 시각과 관계없이 FUTURE_BASE가 미래인지 확인한다.
    assert FUTURE_BASE > datetime.now(UTC).replace(tzinfo=None), "FUTURE_BASE를 미래로 옮기세요"
    main()
