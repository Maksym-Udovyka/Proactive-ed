from conftest import API


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


def members_url(plan: dict) -> str:
    return f"{API}/plans/{plan['plan_id']}/members"


# ---------- список участников ----------

async def test_list_contains_only_owner_by_default(client, auth_headers, plan, user):
    response = await client.get(members_url(plan), headers=auth_headers)
    assert response.status == 200
    assert await response.json() == [{"user_id": user, "name": "Test", "role": "owner"}]


async def test_list_owner_first_then_members(
    client, db, auth_headers, other_headers, plan, user, other_user
):
    await add_member(db, plan["plan_id"], other_user, "commenter")

    # одинаковый результат и для владельца, и для участника
    for headers in (auth_headers, other_headers):
        response = await client.get(members_url(plan), headers=headers)
        assert response.status == 200
        body = await response.json()
        assert [(m["user_id"], m["role"]) for m in body] == [
            (user, "owner"),
            (other_user, "commenter"),
        ]


async def test_list_prefers_display_name(client, db, auth_headers, plan, user):
    await db.execute(
        "UPDATE auth.users SET display_name = 'Ada' WHERE user_id = $1", user
    )
    response = await client.get(members_url(plan), headers=auth_headers)
    assert (await response.json())[0]["name"] == "Ada"


async def test_list_hidden_from_outsider(client, other_headers, plan):
    response = await client.get(members_url(plan), headers=other_headers)
    assert response.status == 404


async def test_list_requires_auth(client, plan):
    response = await client.get(members_url(plan))
    assert response.status == 401


# ---------- смена роли ----------

async def test_owner_changes_role(
    client, db, auth_headers, plan, other_user
):
    await add_member(db, plan["plan_id"], other_user, "viewer")
    response = await client.patch(
        f"{members_url(plan)}/{other_user}",
        json={"role": "commenter"},
        headers=auth_headers,
    )
    assert response.status == 200
    body = await response.json()
    assert body["user_id"] == other_user
    assert body["role"] == "commenter"
    assert body["name"] == "Test"


async def test_change_role_rejects_invalid_role(
    client, db, auth_headers, plan, other_user
):
    await add_member(db, plan["plan_id"], other_user)
    for payload in ({"role": "owner"}, {"role": "admin"}, {"role": 1}, {}):
        response = await client.patch(
            f"{members_url(plan)}/{other_user}", json=payload, headers=auth_headers
        )
        assert response.status == 400, payload


async def test_change_role_rejects_non_object_body(
    client, db, auth_headers, plan, other_user
):
    await add_member(db, plan["plan_id"], other_user)
    response = await client.patch(
        f"{members_url(plan)}/{other_user}", json=["viewer"], headers=auth_headers
    )
    assert response.status == 400


async def test_member_cannot_change_roles(
    client, db, other_headers, plan, user, other_user
):
    await add_member(db, plan["plan_id"], other_user)
    response = await client.patch(
        f"{members_url(plan)}/{other_user}",
        json={"role": "commenter"},
        headers=other_headers,
    )
    assert response.status == 403


async def test_outsider_cannot_change_roles(
    client, other_headers, plan, other_user
):
    response = await client.patch(
        f"{members_url(plan)}/{other_user}",
        json={"role": "commenter"},
        headers=other_headers,
    )
    assert response.status == 404


async def test_owner_role_cannot_be_changed(client, auth_headers, plan, user):
    response = await client.patch(
        f"{members_url(plan)}/{user}", json={"role": "viewer"}, headers=auth_headers
    )
    assert response.status == 400


async def test_change_role_of_non_member_is_404(
    client, auth_headers, plan, other_user
):
    response = await client.patch(
        f"{members_url(plan)}/{other_user}",
        json={"role": "viewer"},
        headers=auth_headers,
    )
    assert response.status == 404


async def test_huge_user_id_is_404(client, auth_headers, plan):
    response = await client.patch(
        f"{members_url(plan)}/99999999999",
        json={"role": "viewer"},
        headers=auth_headers,
    )
    assert response.status == 404


# ---------- удаление участника владельцем ----------

async def test_owner_removes_member(
    client, db, auth_headers, other_headers, plan, other_user
):
    await add_member(db, plan["plan_id"], other_user)
    response = await client.delete(
        f"{members_url(plan)}/{other_user}", headers=auth_headers
    )
    assert response.status == 204

    # участник потерял доступ к плану
    response = await client.get(
        f"{API}/plans/{plan['plan_id']}", headers=other_headers
    )
    assert response.status == 404


async def test_remove_member_twice_is_404(
    client, db, auth_headers, plan, other_user
):
    await add_member(db, plan["plan_id"], other_user)
    url = f"{members_url(plan)}/{other_user}"
    assert (await client.delete(url, headers=auth_headers)).status == 204
    assert (await client.delete(url, headers=auth_headers)).status == 404


async def test_member_cannot_remove_members(
    client, db, other_headers, plan, other_user
):
    await add_member(db, plan["plan_id"], other_user)
    response = await client.delete(
        f"{members_url(plan)}/{other_user}", headers=other_headers
    )
    assert response.status == 403


async def test_outsider_cannot_remove_members(
    client, other_headers, plan, other_user
):
    response = await client.delete(
        f"{members_url(plan)}/{other_user}", headers=other_headers
    )
    assert response.status == 404


async def test_owner_cannot_be_removed(client, auth_headers, plan, user):
    response = await client.delete(
        f"{members_url(plan)}/{user}", headers=auth_headers
    )
    assert response.status == 400


# ---------- выход из плана ----------

async def test_member_leaves_plan(
    client, db, auth_headers, other_headers, plan, user, other_user
):
    await add_member(db, plan["plan_id"], other_user)
    response = await client.delete(
        f"{API}/plans/{plan['plan_id']}/membership", headers=other_headers
    )
    assert response.status == 204

    response = await client.get(
        f"{API}/plans/{plan['plan_id']}", headers=other_headers
    )
    assert response.status == 404

    # владелец остался единственным в списке
    response = await client.get(members_url(plan), headers=auth_headers)
    assert [m["user_id"] for m in await response.json()] == [user]


async def test_owner_cannot_leave(client, auth_headers, plan):
    response = await client.delete(
        f"{API}/plans/{plan['plan_id']}/membership", headers=auth_headers
    )
    assert response.status == 400
    # план на месте
    response = await client.get(f"{API}/plans/{plan['plan_id']}", headers=auth_headers)
    assert response.status == 200


async def test_outsider_cannot_leave(client, other_headers, plan):
    response = await client.delete(
        f"{API}/plans/{plan['plan_id']}/membership", headers=other_headers
    )
    assert response.status == 404


async def test_leave_twice_is_404(client, db, other_headers, plan, other_user):
    await add_member(db, plan["plan_id"], other_user)
    url = f"{API}/plans/{plan['plan_id']}/membership"
    assert (await client.delete(url, headers=other_headers)).status == 204
    assert (await client.delete(url, headers=other_headers)).status == 404