import pytest

API = "/api/planning/v1"

VALID = {
    "title": "Math lecture",
    "activity_type": "lecture",
    "start_time": "2026-11-06T10:00:00+02:00",
    "duration_minutes": 90,
}


async def make_session(client, headers, plan_id, **overrides):
    payload = {**VALID, **overrides}
    return await client.post(
        f"{API}/plans/{plan_id}/sessions", json=payload, headers=headers
    )


async def test_create_session(client, plan, auth_headers):
    response = await make_session(client, auth_headers, plan["plan_id"])
    assert response.status == 201
    body = await response.json()
    assert body["plan_id"] == plan["plan_id"]
    assert body["title"] == "Math lecture"
    assert body["activity_type"] == "lecture"
    assert body["duration_minutes"] == 90
    assert body["start_time"] == "2026-11-06T08:00:00+00:00"  # хранится в UTC


@pytest.mark.parametrize(
    "activity", ["lecture", "practice", "reading", "self_study", "exam_prep"]
)
async def test_all_activity_types(client, plan, auth_headers, activity):
    response = await make_session(
        client, auth_headers, plan["plan_id"], activity_type=activity
    )
    assert response.status == 201
    assert (await response.json())["activity_type"] == activity


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": ""},
        {"title": "x" * 201},
        {"activity_type": "party"},
        {"activity_type": None},
        {"duration_minutes": 0},
        {"duration_minutes": -5},
        {"duration_minutes": 1441},
        {"duration_minutes": "90"},
        {"duration_minutes": 1.5},
        {"duration_minutes": True},
        {"start_time": "2026-11-06T10:00:00"},  # нет часового пояса
        {"start_time": "tomorrow"},
        {"start_time": 12345},
    ],
)
async def test_create_session_validation(client, plan, auth_headers, overrides):
    response = await make_session(client, auth_headers, plan["plan_id"], **overrides)
    assert response.status == 400


@pytest.mark.parametrize("missing", list(VALID))
async def test_create_session_requires_all_fields(client, plan, auth_headers, missing):
    payload = {key: value for key, value in VALID.items() if key != missing}
    response = await client.post(
        f"{API}/plans/{plan['plan_id']}/sessions", json=payload, headers=auth_headers
    )
    assert response.status == 400


async def test_get_session(client, plan, auth_headers, other_headers):
    created = await (await make_session(client, auth_headers, plan["plan_id"])).json()
    url = f"{API}/sessions/{created['study_session_id']}"

    response = await client.get(url, headers=auth_headers)
    assert response.status == 200
    assert (await response.json())["title"] == "Math lecture"

    assert (await client.get(url, headers=other_headers)).status == 404
    assert (await client.get(f"{API}/sessions/999999999", headers=auth_headers)).status == 404


async def test_update_session(client, plan, auth_headers):
    created = await (await make_session(client, auth_headers, plan["plan_id"])).json()
    url = f"{API}/sessions/{created['study_session_id']}"

    response = await client.patch(
        url,
        json={"duration_minutes": 45, "activity_type": "practice"},
        headers=auth_headers,
    )
    assert response.status == 200
    body = await response.json()
    assert body["duration_minutes"] == 45
    assert body["activity_type"] == "practice"
    assert body["title"] == "Math lecture"  # остальное не изменилось

    assert (await client.patch(url, json={}, headers=auth_headers)).status == 400
    response = await client.patch(url, json={"duration_minutes": 0}, headers=auth_headers)
    assert response.status == 400


async def test_delete_session(client, plan, auth_headers):
    created = await (await make_session(client, auth_headers, plan["plan_id"])).json()
    url = f"{API}/sessions/{created['study_session_id']}"

    assert (await client.delete(url, headers=auth_headers)).status == 204
    assert (await client.get(url, headers=auth_headers)).status == 404
    assert (await client.delete(url, headers=auth_headers)).status == 404


async def test_list_sessions_sorted_and_filtered(client, plan, auth_headers):
    plan_id = plan["plan_id"]
    # создаём не по порядку, чтобы проверить сортировку
    for start in ("2026-11-07T10:00:00Z", "2026-11-05T10:00:00Z", "2026-11-06T10:00:00Z"):
        response = await make_session(client, auth_headers, plan_id, start_time=start)
        assert response.status == 201

    url = f"{API}/plans/{plan_id}/sessions"
    items = await (await client.get(url, headers=auth_headers)).json()
    starts = [item["start_time"] for item in items]
    assert starts == sorted(starts)
    assert len(items) == 3

    only_second = await (
        await client.get(f"{url}?from=2026-11-06&to=2026-11-06", headers=auth_headers)
    ).json()
    assert [item["start_time"] for item in only_second] == ["2026-11-06T10:00:00+00:00"]

    from_third = await (await client.get(f"{url}?from=2026-11-07", headers=auth_headers)).json()
    assert len(from_third) == 1

    until_first = await (await client.get(f"{url}?to=2026-11-05", headers=auth_headers)).json()
    assert len(until_first) == 1

    for query in ("from=2026-11-08&to=2026-11-01", "from=bad", "to=2026-13-40"):
        response = await client.get(f"{url}?{query}", headers=auth_headers)
        assert response.status == 400, query


async def test_other_user_cannot_use_plan(client, plan, other_headers):
    plan_id = plan["plan_id"]
    assert (await make_session(client, other_headers, plan_id)).status == 404
    response = await client.get(f"{API}/plans/{plan_id}/sessions", headers=other_headers)
    assert response.status == 404


async def test_session_in_missing_plan_is_404(client, auth_headers):
    assert (await make_session(client, auth_headers, 999999999)).status == 404


async def test_viewer_can_read_but_not_change_sessions(
    client, db, plan, auth_headers, other_user, other_headers
):
    created = await (await make_session(client, auth_headers, plan["plan_id"])).json()
    await db.execute(
        "INSERT INTO planning.plan_members (plan_id, user_id, role) VALUES ($1, $2, 'viewer')",
        plan["plan_id"],
        other_user,
    )
    session_url = f"{API}/sessions/{created['study_session_id']}"
    list_url = f"{API}/plans/{plan['plan_id']}/sessions"

    assert (await client.get(list_url, headers=other_headers)).status == 200
    assert (await client.get(session_url, headers=other_headers)).status == 200

    assert (await make_session(client, other_headers, plan["plan_id"])).status == 403
    assert (
        await client.patch(session_url, json={"title": "Hack"}, headers=other_headers)
    ).status == 403
    assert (await client.delete(session_url, headers=other_headers)).status == 403


async def test_deleting_plan_deletes_sessions(client, plan, auth_headers):
    created = await (await make_session(client, auth_headers, plan["plan_id"])).json()
    session_url = f"{API}/sessions/{created['study_session_id']}"

    assert (await client.delete(f"{API}/plans/{plan['plan_id']}", headers=auth_headers)).status == 204
    assert (await client.get(session_url, headers=auth_headers)).status == 404