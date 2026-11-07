import pytest

from tests.conftest import auth_header


@pytest.fixture
def client(client, admin):
    """이 파일의 테스트는 관리자로 로그인한 상태에서 실행한다. (권한 검사는 test_auth.py)"""
    client.headers.update(auth_header(admin))
    return client


def create(client, **overrides):
    body = {"name": "회의실 A", "capacity": 6} | overrides
    return client.post("/resources", json=body)


# --- 등록 -------------------------------------------------------------------


def test_create_resource_returns_201_with_defaults(client):
    response = create(client, description="2층 창가", location="본관 2층")

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["name"] == "회의실 A"
    assert body["capacity"] == 6
    assert body["description"] == "2층 창가"
    assert body["location"] == "본관 2층"
    assert body["is_active"] is True  # DB 기본값


def test_create_resource_strips_whitespace_in_name(client):
    response = create(client, name="  회의실 B  ")

    assert response.status_code == 201
    assert response.json()["name"] == "회의실 B"


def test_create_resource_with_duplicate_name_returns_409(client):
    assert create(client, name="Room A").status_code == 201

    response = create(client, name="Room A")

    assert response.status_code == 409
    assert response.json() == {"detail": "같은 이름의 자원이 이미 있습니다."}


def test_duplicate_name_check_ignores_case(client):
    # DB 콜레이션(utf8mb4_0900_ai_ci)은 대소문자를 구분하지 않는다.
    # 그래서 "Room A"와 "room a"는 같은 이름으로 취급된다.
    assert create(client, name="Room A").status_code == 201

    assert create(client, name="room a").status_code == 409


@pytest.mark.parametrize(
    "overrides",
    [
        {"capacity": 0},
        {"capacity": -1},
        {"name": ""},
        {"name": "   "},
        {"name": "가" * 101},
        {"unknown_field": "x"},
    ],
    ids=["capacity-0", "capacity-negative", "name-empty", "name-blank", "name-too-long", "extra"],
)
def test_create_resource_with_invalid_body_returns_422(client, overrides):
    assert create(client, **overrides).status_code == 422


# --- 조회 -------------------------------------------------------------------


def test_get_resource(client):
    resource_id = create(client).json()["id"]

    response = client.get(f"/resources/{resource_id}")

    assert response.status_code == 200
    assert response.json()["name"] == "회의실 A"


def test_get_unknown_resource_returns_404(client):
    response = client.get("/resources/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "자원을 찾을 수 없습니다."}


def test_list_excludes_inactive_resources_by_default(client):
    create(client, name="A")
    inactive_id = create(client, name="B").json()["id"]
    client.patch(f"/resources/{inactive_id}", json={"is_active": False})

    default = client.get("/resources").json()
    with_inactive = client.get("/resources", params={"include_inactive": True}).json()

    assert [r["name"] for r in default["items"]] == ["A"]
    assert default["total"] == 1
    assert [r["name"] for r in with_inactive["items"]] == ["A", "B"]
    assert with_inactive["total"] == 2


def test_list_paginates_and_reports_total(client):
    for i in range(5):
        create(client, name=f"Room {i}")

    page = client.get("/resources", params={"limit": 2, "offset": 2}).json()

    assert [r["name"] for r in page["items"]] == ["Room 2", "Room 3"]
    assert page["total"] == 5


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_list_with_invalid_paging_returns_422(client, params):
    assert client.get("/resources", params=params).status_code == 422


# --- 수정 -------------------------------------------------------------------


def test_patch_changes_only_given_fields(client):
    resource_id = create(client, description="원래 설명").json()["id"]

    response = client.patch(f"/resources/{resource_id}", json={"capacity": 10})

    assert response.status_code == 200
    body = response.json()
    assert body["capacity"] == 10
    assert body["name"] == "회의실 A"
    assert body["description"] == "원래 설명"


def test_patch_can_clear_nullable_field_with_null(client):
    resource_id = create(client, description="지울 설명").json()["id"]

    response = client.patch(f"/resources/{resource_id}", json={"description": None})

    assert response.status_code == 200
    assert response.json()["description"] is None


@pytest.mark.parametrize("field", ["name", "capacity", "is_active"])
def test_patch_rejects_null_for_required_field(client, field):
    resource_id = create(client).json()["id"]

    response = client.patch(f"/resources/{resource_id}", json={field: None})

    assert response.status_code == 422


def test_patch_to_existing_name_returns_409(client):
    create(client, name="A")
    b_id = create(client, name="B").json()["id"]

    response = client.patch(f"/resources/{b_id}", json={"name": "A"})

    assert response.status_code == 409
    # 실패한 수정은 반영되지 않아야 한다.
    assert client.get(f"/resources/{b_id}").json()["name"] == "B"


def test_patch_unknown_resource_returns_404(client):
    assert client.patch("/resources/999999", json={"capacity": 3}).status_code == 404
