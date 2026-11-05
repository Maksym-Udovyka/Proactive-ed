import pytest

API = "/api/planning/v1"

VALID = {
    "title": "Math exam",
    "event_type": "exam",
    "event_date": "2026-11-06",
    "description": "Room 204",
}


async def make_event(client, headers, plan_id, **overrides):
    payload = {**VALID, **overrides}
    return await client.post(
        f"{API}/plans/{plan_id}/events", json=payload, headers=headers
    )


async def test_create_event(client, plan, auth_headers):
    response = await make_event(client, auth_headers, plan["plan_id"])
    assert response.status == 201
    body = await response.json()
    assert body["plan_id"] == plan["plan_id"]
    assert body["title"] == "Math exam"
    assert body["event_type"] == "exam"
    assert body["event_date"] == "2026-11-06"
    assert body["description"] == "Room 204"


async def test_description_is_optional(client, plan, auth_headers):
    payload = {key: value for key, value in VALID.items() if key != "description"}
    response = await client.post(
        f"{API}/plans/{plan['plan_id']}/events", json=payload, headers=auth_headers
    )
    assert response.status == 201
    assert (await response.json())["description"] is None


@pytest.mark.parametrize("event_type", ["exam", "test", "deadline", "other"])
async def test_all_event_types(client, plan, auth_headers, event_type):
    response = await make_event(
        client, auth_headers, plan["plan_id"], event_type=event_type
    )
    assert response.status == 201
    assert (await response.json())["event_type"] == event_type


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": ""},
        {"title": "x" * 201},
        {"event_type": "party"},
        {"event_type": None},
        {"event_date": "06.11.2026"},
        {"event_date": "2026-13-40"},
        {"event_date": "tomorrow"},
        {"event_date": 20261106},
        {"event_date": None},
        {"description": 123},
        {"description": "x" * 2001},
    ],
)
async def test_create_event_validation(client, plan, auth_headers, overrides):
    response = await make_event(client, auth_headers, plan["plan_id"], **overrides)
    assert response.status == 400


@pytest.mark.parametrize("missing", ["title", "event_type", "event_date"])
async def test_create_event_requires_fields(client, plan, auth_headers, missing):
    payload = {key: value for key, value in VALID.items() if key != missing}
    response = await client.post(
        f"{API}/plans/{plan['plan_id']}/events", json=payload, headers=auth_headers
    )
    assert response.status == 400


async def test_get_event(client, plan, auth_headers, other_headers):
    created = await (await make_event(client, auth_headers, plan["plan_id"])).json()
    url = f"{API}/events/{created['event_id']}"

    response = await client.get(url, headers=auth_headers)
    assert response.status == 200
    assert (await response.json())["title"] == "Math exam"

    assert (await client.get(url, headers=other_headers)).status == 404
    assert (await client.get(f"{API}/events/999999999", headers=auth_headers)).status == 404


async def test_update_event(client, plan, auth_headers):
    created = await (await make_event(client, auth_headers, plan["plan_id"])).json()
    url = f"{API}/events/{created['event_id']}"

    response = await client.patch(
        url,
        json={"event_type": "test", "event_date": "2026-11-10"},
        headers=auth_headers,
    )
    assert response.status == 200
    body = await response.json()
    assert body["event_type"] == "test"
    assert body["event_date"] == "2026-11-10"
    assert body["title"] == "Math exam"  # остальное не изменилось

    response = await client.patch(url, json={"description": None}, headers=auth_headers)
    assert (await response.json())["description"] is None

    assert (await client.patch(url, json={}, headers=auth_headers)).status == 400
    response = await client.patch(url, json={"event_date": "bad"}, headers=auth_headers)
    assert response.status == 400


async def test_delete_event(client, plan, auth_headers):
    created = await (await make_event(client, auth_headers, plan["plan_id"])).json()
    url = f"{API}/events/{created['event_id']}"

    assert (await client.delete(url, headers=auth_headers)).status == 204
    assert (await client.get(url, headers=auth_headers)).status == 404
    assert (await client.delete(url, headers=auth_headers)).status == 404


async def test_list_events_sorted_and_filtered(client, plan, auth_headers):
    plan_id = plan["plan_id"]
    for event_date in ("2026-11-07", "2026-11-05", "2026-11-06"):
        response = await make_event(client, auth_headers, plan_id, event_date=event_date)
        assert response.status == 201

    url = f"{API}/plans/{plan_id}/events"
    items = await (await client.get(url, headers=auth_headers)).json()
    dates = [item["event_date"] for item in items]
    assert dates == ["2026-11-05", "2026-11-06", "2026-11-07"]

    only_second = await (
        await client.get(f"{url}?from=2026-11-06&to=2026-11-06", headers=auth_headers)
    ).json()
    assert [item["event_date"] for item in only_second] == ["2026-11-06"]

    from_third = await (await client.get(f"{url}?from=2026-11-07", headers=auth_headers)).json()
    assert len(from_third) == 1

    until_first = await (await client.get(f"{url}?to=2026-11-05", headers=auth_headers)).json()
    assert len(until_first) == 1

    for query in ("from=2026-11-08&to=2026-11-01", "from=bad"):
        response = await client.get(f"{url}?{query}", headers=auth_headers)
        assert response.status == 400, query


async def test_other_user_cannot_use_plan(client, plan, other_headers):
    plan_id = plan["plan_id"]
    assert (await make_event(client, other_headers, plan_id)).status == 404
    response = await client.get(f"{API}/plans/{plan_id}/events", headers=other_headers)
    assert response.status == 404


async def test_event_in_missing_plan_is_404(client, auth_headers):
    assert (await make_event(client, auth_headers, 999999999)).status == 404


async def test_viewer_can_read_but_not_change_events(
    client, db, plan, auth_headers, other_user, other_headers
):
    created = await (await make_event(client, auth_headers, plan["plan_id"])).json()
    await db.execute(
        "INSERT INTO planning.plan_members (plan_id, user_id, role) VALUES ($1, $2, 'viewer')",
        plan["plan_id"],
        other_user,
    )
    event_url = f"{API}/events/{created['event_id']}"
    list_url = f"{API}/plans/{plan['plan_id']}/events"

    assert (await client.get(list_url, headers=other_headers)).status == 200
    assert (await client.get(event_url, headers=other_headers)).status == 200

    assert (await make_event(client, other_headers, plan["plan_id"])).status == 403
    assert (
        await client.patch(event_url, json={"title": "Hack"}, headers=other_headers)
    ).status == 403
    assert (await client.delete(event_url, headers=other_headers)).status == 403


async def test_deleting_plan_deletes_events(client, plan, auth_headers):
    created = await (await make_event(client, auth_headers, plan["plan_id"])).json()
    event_url = f"{API}/events/{created['event_id']}"

    assert (await client.delete(f"{API}/plans/{plan['plan_id']}", headers=auth_headers)).status == 204
    assert (await client.get(event_url, headers=auth_headers)).status == 404