from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# 길이 제한은 DB 컬럼 길이(VARCHAR)와 맞춘다. 여기서 먼저 막으면 DB 오류 대신 422로 응답한다.
ResourceName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Location = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
Capacity = Annotated[int, Field(ge=1, description="수용 인원 (1 이상)")]


class ResourceCreate(BaseModel):
    # 정의하지 않은 필드가 오면 조용히 무시하지 않고 422로 거절한다. (오타를 바로 알 수 있음)
    model_config = ConfigDict(extra="forbid")

    name: ResourceName
    capacity: Capacity
    description: Description | None = None
    location: Location | None = None


class ResourceUpdate(BaseModel):
    """PATCH용. 보낸 필드만 바꾼다."""

    model_config = ConfigDict(extra="forbid")

    name: ResourceName | None = None
    capacity: Capacity | None = None
    description: Description | None = None
    location: Location | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def reject_null_for_required_columns(self) -> Self:
        # "보내지 않음"과 "null을 보냄"을 구분한다.
        # description, location은 null로 지울 수 있지만, 아래 필드는 DB에서 NOT NULL이다.
        for field in ("name", "capacity", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field}는 null로 바꿀 수 없습니다.")
        return self


class ResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    capacity: int
    description: str | None
    location: str | None
    is_active: bool


class ResourceList(BaseModel):
    items: list[ResourceRead]
    total: int = Field(description="필터 조건에 맞는 전체 개수 (페이지와 무관)")
