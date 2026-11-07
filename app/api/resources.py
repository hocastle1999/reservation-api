from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.resource import ResourceCreate, ResourceList, ResourceRead, ResourceUpdate
from app.services import resource_service

router = APIRouter(prefix="/resources", tags=["resources"])

DbSession = Annotated[Session, Depends(get_db)]

ERROR_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {"description": "자원이 없음"},
    status.HTTP_409_CONFLICT: {"description": "같은 이름의 자원이 이미 있음"},
}

# TODO(인증 기능): 등록과 수정은 관리자(ADMIN)만 할 수 있도록 막는다.


@router.post(
    "",
    response_model=ResourceRead,
    status_code=status.HTTP_201_CREATED,
    responses={409: ERROR_RESPONSES[409]},
    summary="자원 등록",
)
def create_resource(data: ResourceCreate, db: DbSession):
    return resource_service.create_resource(db, data)


@router.get("", response_model=ResourceList, summary="자원 목록")
def list_resources(
    db: DbSession,
    include_inactive: Annotated[bool, Query(description="비활성 자원도 포함")] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    items, total = resource_service.list_resources(
        db, include_inactive=include_inactive, limit=limit, offset=offset
    )
    return ResourceList(items=items, total=total)


@router.get(
    "/{resource_id}",
    response_model=ResourceRead,
    responses={404: ERROR_RESPONSES[404]},
    summary="자원 상세",
)
def get_resource(resource_id: int, db: DbSession):
    return resource_service.get_resource(db, resource_id)


@router.patch(
    "/{resource_id}",
    response_model=ResourceRead,
    responses=ERROR_RESPONSES,
    summary="자원 수정 (비활성화 포함)",
    description="보낸 필드만 바꾼다. 자원은 삭제하지 않고 `is_active: false`로 비활성화한다.",
)
def update_resource(resource_id: int, data: ResourceUpdate, db: DbSession):
    return resource_service.update_resource(db, resource_id, data)
