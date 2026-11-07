from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.db.errors import is_duplicate_entry
from app.models import Resource
from app.schemas.resource import ResourceCreate, ResourceUpdate

DUPLICATE_NAME_MESSAGE = "같은 이름의 자원이 이미 있습니다."


def create_resource(db: Session, data: ResourceCreate) -> Resource:
    resource = Resource(**data.model_dump())
    db.add(resource)
    _commit_or_raise_conflict(db)
    # is_active 같은 DB 기본값(server_default)을 읽어 오기 위해 다시 조회한다.
    db.refresh(resource)
    return resource


def get_resource(db: Session, resource_id: int) -> Resource:
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise NotFoundError("자원을 찾을 수 없습니다.")
    return resource


def list_resources(
    db: Session, *, include_inactive: bool, limit: int, offset: int
) -> tuple[list[Resource], int]:
    conditions = [] if include_inactive else [Resource.is_active.is_(True)]

    total = db.scalar(select(func.count()).select_from(Resource).where(*conditions)) or 0
    items = db.scalars(
        select(Resource).where(*conditions).order_by(Resource.id).limit(limit).offset(offset)
    ).all()
    return list(items), total


def update_resource(db: Session, resource_id: int, data: ResourceUpdate) -> Resource:
    resource = get_resource(db, resource_id)
    # exclude_unset: 요청에 포함된 필드만 바꾼다. (보내지 않은 필드는 그대로)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(resource, field, value)
    _commit_or_raise_conflict(db)
    db.refresh(resource)
    return resource


def _commit_or_raise_conflict(db: Session) -> None:
    """이름 중복은 SELECT로 미리 확인하지 않고 DB의 UNIQUE 제약에 맡긴다.

    "같은 이름이 있는지 조회 → 없으면 INSERT"로 하면, 두 요청이 동시에 조회했을 때
    둘 다 "없음"을 보고 INSERT할 수 있다. UNIQUE 제약은 이 경우에도 하나만 통과시킨다.
    그래서 INSERT를 먼저 시도하고, 중복 오류(1062)가 나면 409로 바꿔 응답한다.
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if is_duplicate_entry(exc):
            raise ConflictError(DUPLICATE_NAME_MESSAGE) from exc
        raise
