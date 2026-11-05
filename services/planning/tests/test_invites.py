import asyncio

from conftest import API


async def make_invite(client, headers, plan: dict, role: str | None = None) -> dict:
    payload = {} if role is None else {"role": role}
    response = await client.post(
        f"{API}/plans/{plan['plan_id']}/invites", json=payload, headers=headers
    )
    assert response.status == 201
    return await response.json()


async def add_member(db, plan_id: int, user_id: int, role: str = "viewer") -> None:
    await db.execute(
        """
        INSERT INTO planning.plan_members (plan_id, user_id, role)
        VALUES ($1, $2, $3::planning.plan_role)
        """,
        plan_id,
        user_id,
        role,
    )


async def expire(db, token: str) -> None:
    await db.execute(
        """
        UPDATE planning.plan_invites
        SET expires_at = now() - interval '1 hour' WHERE token = $1
        """,
        token,
    )


async def mark_used(db, token: str) -> None:
    await db.execute(
        "UPDATE planning.plan_invites SET used_at = now() WHERE token = $1", token
    )


def invites_url(plan: dict) -> str:
    return f"{API}/plans/{plan['plan_id']}/invites"


def preview_url(token: str) -> str:
    return f"{API}/invites/{token}"


def accept_url(token: str) -> str:
    return f"{API}/invites/{token}/accept"


# ---------- создание ----------

async def test_create_invite_defaults_to_viewer(client, auth_headers, plan, user):
    invite = await make_invite(client, auth_headers, plan)
    assert invite["role"] == "viewer"
    assert invite["plan_id"] == plan["plan_id"]
    assert invite["created_by"] == user
    assert len(invite["token"]) >= 16
    assert invite["expires_at"]


async def test_create_invite_with_commenter_role(client, auth_headers, plan):
    invite = await make_invite(client, auth_headers, plan, "commenter")
    assert invite["role"] == "commenter"


async def test_invite_lives_seven_days(client, db, auth_headers, plan):
    invite = await make_invite(client, auth_headers, plan)
    ok = await db.fetchval(
        """
        SELECT expires_at > now() + interval '6 days 23 hours'
           AND expires_at <= now() + interval '7 days'
        FROM planning.plan_invites WHERE token = $1
        """,
        invite["token"],
    )
    assert ok is True


async def test_tokens_are_unique(client, auth_headers, plan):
    first = await make_invite(client, auth_headers, plan)
    second = await make_invite(client, auth_headers, plan)
    assert first["token"] != second["token"]


async def test_create_invite_rejects_bad_role(client, auth_headers, plan):
    for payload in ({"role": "owner"}, {"role": "admin"}, {"role": 5}):
        response = await client.post(
            invites_url(plan), json=payload, headers=auth_headers
        )
        assert response.status == 400, payload


async def test_create_invite_rejects_non_object_body(client, auth_headers, plan):
    response = await client.post(invites_url(plan), json=["viewer"], headers=auth_headers)
    assert response.status == 400


async def test_member_cannot_create_invite(
    client, db, other_headers, plan, other_user
):
    await add_member(db, plan["plan_id"], other_user)
    response = await client.post(invites_url(plan), json={}, headers=other_headers)
    assert response.status == 403


async def test_outsider_cannot_create_invite(client, other_headers, plan):
    response = await client.post(invites_url(plan), json={}, headers=other_headers)
    assert response.status == 404


async def test_create_invite_requires_auth(client, plan):
    response = await client.post(invites_url(plan), json={})
    assert response.status == 401


# ---------- список активных ----------

async def test_list_shows_only_active_invites(client, db, auth_headers, plan):
    active = await make_invite(client, auth_headers, plan)
    used = await make_invite(client, auth_headers, plan)
    expired = await make_invite(client, auth_headers, plan)
    await mark_used(db, used["token"])
    await expire(db, expired["token"])

    response = await client.get(invites_url(plan), headers=auth_headers)
    assert response.status == 200
    tokens = [item["token"] for item in await response.json()]
    assert tokens == [active["token"]]


async def test_list_newest_first(client, auth_headers, plan):
    first = await make_invite(client, auth_headers, plan)
    second = await make_invite(client, auth_headers, plan)
    response = await client.get(invites_url(plan), headers=auth_headers)
    tokens = [item["token"] for item in await response.json()]
    assert tokens == [second["token"], first["token"]]


async def test_member_cannot_list_invites(
    client, db, other_headers, plan, other_user
):
    await add_member(db, plan["plan_id"], other_user)
    response = await client.get(invites_url(plan), headers=other_headers)
    assert response.status == 403


async def test_outsider_cannot_list_invites(client, other_headers, plan):
    response = await client.get(invites_url(plan), headers=other_headers)
    assert response.status == 404


# ---------- отзыв ----------

async def test_owner_revokes_invite(client, auth_headers, other_headers, plan):
    invite = await make_invite(client, auth_headers, plan)
    url = f"{invites_url(plan)}/{invite['plan_invite_id']}"
    assert (await client.delete(url, headers=auth_headers)).status == 204

    assert (await client.get(preview_url(invite["token"]), headers=other_headers)).status == 404
    assert (await client.post(accept_url(invite["token"]), headers=other_headers)).status == 404
    assert (await client.delete(url, headers=auth_headers)).status == 404


async def test_used_invite_cannot_be_revoked(client, db, auth_headers, plan):
    invite = await make_invite(client, auth_headers, plan)
    await mark_used(db, invite["token"])
    response = await client.delete(
        f"{invites_url(plan)}/{invite['plan_invite_id']}", headers=auth_headers
    )
    assert response.status == 404


async def test_cannot_revoke_invite_through_another_plan(client, auth_headers, plan):
    invite = await make_invite(client, auth_headers, plan)
    response = await client.post(
        f"{API}/plans", json={"title": "Second"}, headers=auth_headers
    )
    second_plan = await response.json()
    response = await client.delete(
        f"{invites_url(second_plan)}/{invite['plan_invite_id']}", headers=auth_headers
    )
    assert response.status == 404


async def test_member_cannot_revoke_invite(
    client, db, auth_headers, other_headers, plan, other_user
):
    invite = await make_invite(client, auth_headers, plan)
    await add_member(db, plan["plan_id"], other_user)
    response = await client.delete(
        f"{invites_url(plan)}/{invite['plan_invite_id']}", headers=other_headers
    )
    assert response.status == 403


async def test_outsider_cannot_revoke_invite(
    client, auth_headers, other_headers, plan
):
    invite = await make_invite(client, auth_headers, plan)
    response = await client.delete(
        f"{invites_url(plan)}/{invite['plan_invite_id']}", headers=other_headers
    )
    assert response.status == 404


# ---------- предпросмотр ----------

async def test_preview_valid_for_outsider(
    client, auth_headers, other_headers, plan
):
    invite = await make_invite(client, auth_headers, plan, "commenter")
    response = await client.get(preview_url(invite["token"]), headers=other_headers)
    assert response.status == 200
    body = await response.json()
    assert body["state"] == "valid"
    assert body["plan_id"] == plan["plan_id"]
    assert body["plan_title"] == "Test plan"
    assert body["role"] == "commenter"
    assert body["invited_by_name"] == "Test"
    assert body["expires_at"]


async def test_preview_does_not_consume_invite(
    client, auth_headers, other_headers, plan
):
    invite = await make_invite(client, auth_headers, plan)
    for _ in range(2):
        response = await client.get(preview_url(invite["token"]), headers=other_headers)
        assert (await response.json())["state"] == "valid"


async def test_preview_own_plan(client, auth_headers, plan):
    invite = await make_invite(client, auth_headers, plan)
    response = await client.get(preview_url(invite["token"]), headers=auth_headers)
    assert (await response.json())["state"] == "own_plan"


async def test_preview_already_member(
    client, db, auth_headers, other_headers, plan, other_user
):
    invite = await make_invite(client, auth_headers, plan)
    await add_member(db, plan["plan_id"], other_user)
    response = await client.get(preview_url(invite["token"]), headers=other_headers)
    assert (await response.json())["state"] == "already_member"


async def test_preview_used(client, db, auth_headers, other_headers, plan):
    invite = await make_invite(client, auth_headers, plan)
    await mark_used(db, invite["token"])
    response = await client.get(preview_url(invite["token"]), headers=other_headers)
    assert (await response.json())["state"] == "used"


async def test_preview_expired(client, db, auth_headers, other_headers, plan):
    invite = await make_invite(client, auth_headers, plan)
    await expire(db, invite["token"])
    response = await client.get(preview_url(invite["token"]), headers=other_headers)
    assert (await response.json())["state"] == "expired"


async def test_preview_unknown_token_is_404(client, other_headers):
    response = await client.get(preview_url("no-such-token"), headers=other_headers)
    assert response.status == 404


async def test_preview_overlong_token_is_404(client, other_headers):
    response = await client.get(preview_url("a" * 101), headers=other_headers)
    assert response.status == 404


async def test_preview_requires_auth(client, auth_headers, plan):
    invite = await make_invite(client, auth_headers, plan)
    response = await client.get(preview_url(invite["token"]))
    assert response.status == 401


# ---------- вступление ----------

async def test_accept_joins_plan(
    client, db, auth_headers, other_headers, plan, user, other_user
):
    invite = await make_invite(client, auth_headers, plan, "commenter")
    response = await client.post(accept_url(invite["token"]), headers=other_headers)
    assert response.status == 200
    assert await response.json() == {"plan_id": plan["plan_id"], "role": "commenter"}

    # план теперь доступен с нужной ролью
    response = await client.get(f"{API}/plans/{plan['plan_id']}", headers=other_headers)
    assert response.status == 200
    assert (await response.json())["role"] == "commenter"

    # участник виден в списке
    response = await client.get(
        f"{API}/plans/{plan['plan_id']}/members", headers=auth_headers
    )
    assert [(m["user_id"], m["role"]) for m in await response.json()] == [
        (user, "owner"),
        (other_user, "commenter"),
    ]

    # ссылка помечена использованной и пропала из активных
    used_by = await db.fetchval(
        "SELECT used_by FROM planning.plan_invites WHERE token = $1", invite["token"]
    )
    assert used_by == other_user
    response = await client.get(invites_url(plan), headers=auth_headers)
    assert await response.json() == []


async def test_accept_twice_by_same_user_says_already_member(
    client, auth_headers, other_headers, plan
):
    invite = await make_invite(client, auth_headers, plan)
    assert (await client.post(accept_url(invite["token"]), headers=other_headers)).status == 200
    response = await client.post(accept_url(invite["token"]), headers=other_headers)
    assert response.status == 409
    assert "already a member" in (await response.json())["error"]


async def test_concurrent_accepts_use_invite_once(
    client, auth_headers, other_headers, plan
):
    invite = await make_invite(client, auth_headers, plan)
    responses = await asyncio.gather(
        client.post(accept_url(invite["token"]), headers=other_headers),
        client.post(accept_url(invite["token"]), headers=other_headers),
    )
    assert sorted(r.status for r in responses) == [200, 409]


async def test_accept_used_invite_is_409(
    client, db, auth_headers, other_headers, plan
):
    invite = await make_invite(client, auth_headers, plan)
    await mark_used(db, invite["token"])
    response = await client.post(accept_url(invite["token"]), headers=other_headers)
    assert response.status == 409
    assert "already been used" in (await response.json())["error"]

    response = await client.get(f"{API}/plans/{plan['plan_id']}", headers=other_headers)
    assert response.status == 404


async def test_accept_expired_invite_is_410(
    client, db, auth_headers, other_headers, plan, user
):
    invite = await make_invite(client, auth_headers, plan)
    await expire(db, invite["token"])
    response = await client.post(accept_url(invite["token"]), headers=other_headers)
    assert response.status == 410
    assert "expired" in (await response.json())["error"]

    # участником не стал
    response = await client.get(
        f"{API}/plans/{plan['plan_id']}/members", headers=auth_headers
    )
    assert [m["user_id"] for m in await response.json()] == [user]


async def test_owner_cannot_accept_own_invite(client, auth_headers, plan):
    invite = await make_invite(client, auth_headers, plan)
    response = await client.post(accept_url(invite["token"]), headers=auth_headers)
    assert response.status == 409
    assert "own plan" in (await response.json())["error"]


async def test_accept_does_not_spend_invite_for_existing_member(
    client, db, auth_headers, other_headers, plan, other_user
):
    invite = await make_invite(client, auth_headers, plan)
    await add_member(db, plan["plan_id"], other_user)
    response = await client.post(accept_url(invite["token"]), headers=other_headers)
    assert response.status == 409
    used_at = await db.fetchval(
        "SELECT used_at FROM planning.plan_invites WHERE token = $1", invite["token"]
    )
    assert used_at is None


async def test_accept_unknown_token_is_404(client, other_headers):
    response = await client.post(accept_url("no-such-token"), headers=other_headers)
    assert response.status == 404


async def test_accept_requires_auth(client, auth_headers, plan):
    invite = await make_invite(client, auth_headers, plan)
    response = await client.post(accept_url(invite["token"]))
    assert response.status == 401


async def test_left_member_can_rejoin_with_new_invite(
    client, auth_headers, other_headers, plan
):
    first = await make_invite(client, auth_headers, plan)
    assert (await client.post(accept_url(first["token"]), headers=other_headers)).status == 200
    response = await client.delete(
        f"{API}/plans/{plan['plan_id']}/membership", headers=other_headers
    )
    assert response.status == 204

    # старая ссылка одноразовая и уже потрачена
    response = await client.post(accept_url(first["token"]), headers=other_headers)
    assert response.status == 409

    second = await make_invite(client, auth_headers, plan, "commenter")
    response = await client.post(accept_url(second["token"]), headers=other_headers)
    assert response.status == 200