API = "/api/planning/v1"


async def add_session(client, headers, plan_id, start_time, title="Session"):
    response = await client.post(
        f"{API}/plans/{plan_id}/sessions",
        json={
            "title": title,
            "activity_type": "self_study",
            "start_time": start_time,
            "duration_minutes": 60,
        },
        headers=headers,
    )
    assert response.status == 201
    return await response.json()


async def add_event(client, headers, plan_id, event_date, title="Event"):
    response = await client.post(
        f"{API}/plans/{plan_id}/events",
        json={"title": title, "event_type": "exam", "event_date": event_date},
        headers=headers,
    )
    assert response.status == 201
    return await response.json()


async def test_empty_timeline(client, plan, auth_headers):
    response = await client.get(
        f"{API}/plans/{plan['plan_id']}/timeline", headers=auth_headers
    )
    assert response.status == 200
    assert await response.json() == []


async def test_timeline_mixes_sessions_and_events_in_order(client, plan, auth_headers):
    plan_id = plan["plan_id"]
    # создаём намеренно не по порядку
    await add_event(client, auth_headers, plan_id, "2026-11-07", title="E-07")
    await add_session(client, auth_headers, plan_id, "2026-11-06T08:00:00Z", title="S-06")
    await add_event(client, auth_headers, plan_id, "2026-11-06", title="E-06")
    await add_session(client, auth_headers, plan_id, "2026-11-05T22:00:00Z", title="S-05")

    response = await client.get(f"{API}/plans/{plan_id}/timeline", headers=auth_headers)
    assert response.status == 200
    items = await response.json()

    assert [item["title"] for item in items] == ["S-05", "E-06", "S-06", "E-07"]
    assert [item["kind"] for item in items] == ["session", "event", "session", "event"]
    assert "study_session_id" in items[0] and "event_id" not in items[0]
    assert "event_id" in items[1] and "study_session_id" not in items[1]


async def test_timeline_period_filter(client, plan, auth_headers):
    plan_id = plan["plan_id"]
    await add_session(client, auth_headers, plan_id, "2026-11-05T22:00:00Z", title="S-05")
    await add_session(client, auth_headers, plan_id, "2026-11-06T08:00:00Z", title="S-06")
    await add_event(client, auth_headers, plan_id, "2026-11-06", title="E-06")
    await add_event(client, auth_headers, plan_id, "2026-11-07", title="E-07")

    url = f"{API}/plans/{plan_id}/timeline"

    one_day = await (
        await client.get(f"{url}?from=2026-11-06&to=2026-11-06", headers=auth_headers)
    ).json()
    assert [item["title"] for item in one_day] == ["E-06", "S-06"]

    from_day = await (await client.get(f"{url}?from=2026-11-07", headers=auth_headers)).json()
    assert [item["title"] for item in from_day] == ["E-07"]

    until_day = await (await client.get(f"{url}?to=2026-11-05", headers=auth_headers)).json()
    assert [item["title"] for item in until_day] == ["S-05"]


async def test_timeline_invalid_range(client, plan, auth_headers):
    url = f"{API}/plans/{plan['plan_id']}/timeline"
    for query in ("from=2026-11-08&to=2026-11-01", "from=bad", "to=2026-13-40"):
        response = await client.get(f"{url}?{query}", headers=auth_headers)
        assert response.status == 400, query


async def test_timeline_access_rules(client, db, plan, other_user, other_headers):
    url = f"{API}/plans/{plan['plan_id']}/timeline"

    assert (await client.get(url)).status == 401  # без токена
    assert (await client.get(url, headers=other_headers)).status == 404  # чужой план
    assert (await client.get(f"{API}/plans/999999999/timeline", headers=other_headers)).status == 404

    await db.execute(
        "INSERT INTO planning.plan_members (plan_id, user_id, role) VALUES ($1, $2, 'viewer')",
        plan["plan_id"],
        other_user,
    )
    assert (await client.get(url, headers=other_headers)).status == 200  # участник видит