"""核心业务链路的集成测试。

原则：断言错误码而不是只断言状态码——错误码是本项目的对外契约。
"""

import pytest
import pytest_asyncio

API = "/api/v1"

WORKFLOW = {
    "statuses": [
        {"key": "todo", "name": "待办", "order": 0, "is_initial": True, "is_final": False},
        {"key": "doing", "name": "进行中", "order": 1, "is_initial": False, "is_final": False},
        {"key": "done", "name": "已完成", "order": 2, "is_initial": False, "is_final": True},
    ],
    "transitions": [
        {"from_status_key": "todo", "to_status_key": "doing", "allowed_roles": ["OWNER", "MEMBER"]},
        {"from_status_key": "doing", "to_status_key": "done", "allowed_roles": ["OWNER"]},
    ],
}

PASSWORD = "password123"


async def register(client, username: str) -> dict:
    resp = await client.post(
        f"{API}/auth/register",
        json={"username": username, "password": PASSWORD, "email": f"{username}@example.com"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def login(client, username: str) -> str:
    resp = await client.post(
        f"{API}/auth/login",
        json={
            "username": username,
            "password": PASSWORD,
            "device_id": "pytest-device",
            "device_name": "pytest",
            "user_agent": "pytest/1.0",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def make_user(client, username: str) -> dict:
    user = await register(client, username)
    token = await login(client, username)
    return {"id": user["id"], "username": username, "token": token, "headers": bearer(token)}


@pytest_asyncio.fixture
async def owner(client):
    return await make_user(client, "alice")


@pytest_asyncio.fixture
async def member(client):
    return await make_user(client, "bob")


@pytest_asyncio.fixture
async def outsider(client):
    return await make_user(client, "carol")


@pytest_asyncio.fixture
async def team(client, owner):
    resp = await client.post(f"{API}/teams/", json={"name": "Team A"}, headers=owner["headers"])
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def project(client, owner, team):
    resp = await client.post(
        f"{API}/teams/{team['id']}/projects/", json={"name": "Project A"}, headers=owner["headers"]
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def configured_project(client, owner, project):
    """配置好工作流的项目：todo -> doing -> done。"""
    resp = await client.put(
        f"{API}/projects/{project['id']}/workflow/", json=WORKFLOW, headers=owner["headers"]
    )
    assert resp.status_code == 200, resp.text
    return project


@pytest_asyncio.fixture
async def task(client, owner, configured_project):
    resp = await client.post(
        f"{API}/projects/{configured_project['id']}/tasks/",
        json={"title": "第一个任务"},
        headers=owner["headers"],
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def add_member_to_project(client, owner, team, project, user) -> None:
    resp = await client.post(
        f"{API}/teams/{team['id']}/members",
        json={"user_id": user["id"], "role": "member"},
        headers=owner["headers"],
    )
    assert resp.status_code == 201, resp.text

    resp = await client.post(
        f"{API}/projects/{project['id']}/members",
        json={"user_id": user["id"], "role": "MEMBER"},
        headers=owner["headers"],
    )
    assert resp.status_code == 201, resp.text


# ---------------- 认证 ----------------


async def test_register_login_and_me(client):
    user = await register(client, "carol")
    assert user["username"] == "carol"

    token = await login(client, "carol")
    resp = await client.get(f"{API}/auth/me", headers=bearer(token))
    assert resp.status_code == 200
    assert resp.json()["username"] == "carol"


async def test_me_without_token_returns_401(client):
    resp = await client.get(f"{API}/auth/me")
    assert resp.status_code == 401
    body = resp.json()
    # 与业务错误共用同一响应信封
    assert body["code"] == "NOT_AUTHENTICATED"
    assert "request_id" in body
    assert resp.headers.get("www-authenticate") == "Bearer"


async def test_unknown_route_returns_unified_envelope(client):
    resp = await client.get(f"{API}/definitely-not-exist")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


async def test_login_with_wrong_password_returns_401(client):
    await register(client, "dave")
    resp = await client.post(
        f"{API}/auth/login",
        json={
            "username": "dave",
            "password": "wrong-password",
            "device_id": "pytest-device",
            "device_name": "pytest",
            "user_agent": "pytest/1.0",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_CREDENTIALS"


async def test_duplicate_username_returns_409(client):
    await register(client, "erin")
    resp = await client.post(
        f"{API}/auth/register",
        json={"username": "erin", "password": PASSWORD, "email": "erin2@example.com"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "USERNAME_ALREADY_EXISTS"


# ---------------- 工作流配置 ----------------


async def test_workflow_requires_exactly_one_initial_status(client, owner, project):
    bad = {
        "statuses": [
            {"key": "a", "name": "A", "order": 0, "is_initial": True},
            {"key": "b", "name": "B", "order": 1, "is_initial": True},
        ],
        "transitions": [],
    }
    resp = await client.put(
        f"{API}/projects/{project['id']}/workflow/", json=bad, headers=owner["headers"]
    )
    assert 400 <= resp.status_code < 500
    assert resp.json()["code"] == "WORKFLOW_INITIAL_STATUS_INVALID"


async def test_workflow_rejects_duplicate_status_key(client, owner, project):
    bad = {
        "statuses": [
            {"key": "todo", "name": "待办", "order": 0, "is_initial": True},
            {"key": "todo", "name": "重复", "order": 1},
        ],
        "transitions": [],
    }
    resp = await client.put(
        f"{API}/projects/{project['id']}/workflow/", json=bad, headers=owner["headers"]
    )
    assert 400 <= resp.status_code < 500
    assert resp.json()["code"] == "WORKFLOW_STATUS_KEY_DUPLICATE"


async def test_create_task_requires_configured_workflow(client, owner, project):
    resp = await client.post(
        f"{API}/projects/{project['id']}/tasks/",
        json={"title": "无工作流的任务"},
        headers=owner["headers"],
    )
    assert 400 <= resp.status_code < 500
    assert resp.json()["code"] == "TASK_WORKFLOW_NOT_CONFIGURED"


# ---------------- 状态迁移 ----------------


async def test_transition_without_edge_is_rejected(client, owner, task):
    resp = await client.post(
        f"{API}/tasks/{task['id']}/transition",
        json={"to_status_key": "done"},
        headers=owner["headers"],
    )
    assert 400 <= resp.status_code < 500
    assert resp.json()["code"] == "TASK_TRANSITION_NOT_FOUND"


async def test_transition_denied_for_role_not_in_allowed_roles(
    client, owner, member, team, project, configured_project, task
):
    await add_member_to_project(client, owner, team, project, member)

    # todo -> doing 允许 MEMBER
    resp = await client.post(
        f"{API}/tasks/{task['id']}/transition",
        json={"to_status_key": "doing"},
        headers=member["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status_key"] == "doing"

    # doing -> done 只允许 OWNER
    resp = await client.post(
        f"{API}/tasks/{task['id']}/transition",
        json={"to_status_key": "done"},
        headers=member["headers"],
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "TASK_TRANSITION_ROLE_DENIED"


async def test_self_transition_is_denied(client, owner, task):
    resp = await client.post(
        f"{API}/tasks/{task['id']}/transition",
        json={"to_status_key": "todo"},
        headers=owner["headers"],
    )
    assert 400 <= resp.status_code < 500
    assert resp.json()["code"] in {"WORKFLOW_SELF_TRANSITION_DENIED", "TASK_TRANSITION_NOT_FOUND"}


# ---------------- 越权 ----------------


async def test_non_member_cannot_list_project_tasks(client, outsider, configured_project):
    resp = await client.get(
        f"{API}/projects/{configured_project['id']}/tasks/", headers=outsider["headers"]
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "TASK_ACCESS_DENIED"


async def test_non_member_cannot_read_task_detail(client, outsider, task):
    resp = await client.get(f"{API}/tasks/{task['id']}", headers=outsider["headers"])
    assert 400 <= resp.status_code < 500


# ---------------- 分页边界 ----------------


@pytest.mark.parametrize(
    "query",
    ["page=0", "page_size=0", "page_size=1000"],
)
async def test_list_tasks_rejects_invalid_pagination(client, owner, configured_project, query):
    resp = await client.get(
        f"{API}/projects/{configured_project['id']}/tasks/?{query}", headers=owner["headers"]
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


# ---------------- 附件（回归：下载链接必须真实可访问） ----------------


async def test_attachment_upload_then_download(client, owner, task):
    files = {"file": ("hello.txt", b"hello workflowx", "text/plain")}
    resp = await client.post(
        f"{API}/tasks/{task['id']}/attachments", files=files, headers=owner["headers"]
    )
    assert resp.status_code == 201, resp.text
    attachment = resp.json()
    assert attachment["download_url"].startswith("/static/uploads/")

    # 关键断言：download_url 必须真的能取回，这是之前修掉的 bug
    download = await client.get(attachment["download_url"])
    assert download.status_code == 200
    assert download.content == b"hello workflowx"

    # 走鉴权下载接口同样可用
    resp = await client.get(
        f"{API}/tasks/{task['id']}/attachments/{attachment['id']}/download",
        headers=owner["headers"],
    )
    assert resp.status_code == 200
    assert resp.content == b"hello workflowx"
