from tests.conftest import make_token

API = "/api/planning/v1"


async def test_create_plan(client, auth_headers, user):
    response = await client.post(
        f"{API}/plans",
        json={"title": "  My plan  ", "description": "About"},
        headers=auth_headers,
    )
    assert response.status == 201
    body = await response.json()
    assert body["title"] == "My plan"  # пробелы обрезаются
    assert body["description"] == "About"
    assert body["owner_id"] == user
    assert body["role"] == "owner"


async def test_requires_valid_token(client, user):
    assert (await client.get(f"{API}/plans")).status == 401

    bad = {"Authorization": "Bearer not-a-token"}
    assert (await client.get(f"{API}/plans", headers=bad)).status == 401

    expired = {"Authorization": f"Bearer {make_token(user, expires_in=-10)}"}
    response = await client.get(f"{API}/plans", headers=expired)
    assert response.status == 401
    assert (await response.json())["error"] == "Token expired"


async def test_health_is_public(client):
    response = await client.get(f"{API}/health")
    assert response.status == 200


async def test_list_returns_only_own_plans(client, plan, auth_headers, other_headers):
    mine = await (await client.get(f"{API}/plans", headers=auth_headers)).json()
    assert [item["plan_id"] for item in mine] == [plan["plan_id"]]

    theirs = await (await client.get(f"{API}/plans", headers=other_headers)).json()
    assert theirs == []


async def test_get_plan(client, plan, auth_headers):
    response = await client.get(f"{API}/plans/{plan['plan_id']}", headers=auth_headers)
    assert response.status == 200
    assert (await response.json())["title"] == "Test plan"


async def test_other_user_cannot_see_plan(client, plan, other_headers):
    response = await client.get(f"{API}/plans/{plan['plan_id']}", headers=other_headers)
    assert response.status == 404


async def test_update_plan(client, plan, auth_headers):
    url = f"{API}/plans/{plan['plan_id']}"

    response = await client.patch(
        url, json={"title": "Renamed", "description": "Text"}, headers=auth_headers
    )
    assert response.status == 200
    body = await response.json()
    assert body["title"] == "Renamed"
    assert body["description"] == "Text"

    response = await client.patch(url, json={"description": None}, headers=auth_headers)
    assert (await response.json())["description"] is None


async def test_update_without_fields_is_400(client, plan, auth_headers):
    response = await client.patch(
        f"{API}/plans/{plan['plan_id']}", json={}, headers=auth_headers
    )
    assert response.status == 400


async def test_viewer_can_read_but_not_change(
    client, db, plan, other_user, other_headers
):
    await db.execute(
        """
        INSERT INTO planning.plan_members (plan_id, user_id, role)
        VALUES ($1, $2, 'viewer')
        """,
        plan["plan_id"],
        other_user,
    )
    url = f"{API}/plans/{plan['plan_id']}"

    response = await client.get(url, headers=other_headers)
    assert response.status == 200
    assert (await response.json())["role"] == "viewer"

    listed = await (await client.get(f"{API}/plans", headers=other_headers)).json()
    assert [item["plan_id"] for item in listed] == [plan["plan_id"]]

    assert (
        await client.patch(url, json={"title": "Hack"}, headers=other_headers)
    ).status == 403
    assert (await client.delete(url, headers=other_headers)).status == 403


async def test_delete_plan(client, plan, auth_headers):
    url = f"{API}/plans/{plan['plan_id']}"

    assert (await client.delete(url, headers=auth_headers)).status == 204
    assert (await client.get(url, headers=auth_headers)).status == 404
    assert (await client.delete(url, headers=auth_headers)).status == 404


async def test_pagination(client, plan, auth_headers):
    for index in range(2):
        response = await client.post(
            f"{API}/plans", json={"title": f"Plan {index}"}, headers=auth_headers
        )
        assert response.status == 201

    page = await (
        await client.get(f"{API}/plans?limit=2", headers=auth_headers)
    ).json()
    assert len(page) == 2

    rest = await (
        await client.get(f"{API}/plans?limit=2&offset=2", headers=auth_headers)
    ).json()
    assert len(rest) == 1

    for query in ("limit=0", "limit=101", "limit=abc", "offset=-1"):
        response = await client.get(f"{API}/plans?{query}", headers=auth_headers)
        assert response.status == 400, query


async def test_create_plan_validation(client, auth_headers):
    cases = [
        {},
        {"title": ""},
        {"title": "   "},
        {"title": 123},
        {"title": "x" * 201},
        {"title": "ok", "description": 5},
    ]
    for payload in cases:
        response = await client.post(f"{API}/plans", json=payload, headers=auth_headers)
        assert response.status == 400, payload

    response = await client.post(f"{API}/plans", json=["not", "object"], headers=auth_headers)
    assert response.status == 400

    response = await client.post(f"{API}/plans", data="{bad json", headers=auth_headers)
    assert response.status == 400