import asyncpg

# Имя для показа: display_name, иначе first_name.
_NAME_EXPR = "COALESCE(NULLIF(u.display_name, ''), u.first_name)"


async def list_members(pool: asyncpg.Pool, plan_id: int) -> list[asyncpg.Record]:
    """Владелец первым, затем остальные участники в порядке вступления."""
    return await pool.fetch(
        f"""
        SELECT user_id, name, role FROM (
            SELECT u.user_id, {_NAME_EXPR} AS name, 'owner'::text AS role,
                   0 AS sort_group, 0 AS sort_id
            FROM planning.plans p
            JOIN auth.users u ON u.user_id = p.owner_id
            WHERE p.plan_id = $1
            UNION ALL
            SELECT u.user_id, {_NAME_EXPR} AS name, m.role::text AS role,
                   1 AS sort_group, m.plan_member_id AS sort_id
            FROM planning.plan_members m
            JOIN auth.users u ON u.user_id = m.user_id
            WHERE m.plan_id = $1
        ) members
        ORDER BY sort_group, sort_id
        """,
        plan_id,
    )


async def get_member(
    pool: asyncpg.Pool, plan_id: int, user_id: int
) -> asyncpg.Record | None:
    """Участник из plan_members (без владельца) или None."""
    return await pool.fetchrow(
        f"""
        SELECT u.user_id, {_NAME_EXPR} AS name, m.role::text AS role
        FROM planning.plan_members m
        JOIN auth.users u ON u.user_id = m.user_id
        WHERE m.plan_id = $1 AND m.user_id = $2
        """,
        plan_id,
        user_id,
    )


async def update_role(
    pool: asyncpg.Pool, plan_id: int, user_id: int, role: str
) -> asyncpg.Record | None:
    """Меняет роль и сразу возвращает обновлённого участника (один запрос)."""
    return await pool.fetchrow(
        f"""
        WITH updated AS (
            UPDATE planning.plan_members
            SET role = $3::planning.plan_role
            WHERE plan_id = $1 AND user_id = $2
            RETURNING user_id, role
        )
        SELECT u.user_id, {_NAME_EXPR} AS name, updated.role::text AS role
        FROM updated
        JOIN auth.users u ON u.user_id = updated.user_id
        """,
        plan_id,
        user_id,
        role,
    )


async def remove_member(pool: asyncpg.Pool, plan_id: int, user_id: int) -> bool:
    """Убирает участника. Используется и для «удалить», и для «выйти самому»."""
    result = await pool.execute(
        "DELETE FROM planning.plan_members WHERE plan_id = $1 AND user_id = $2",
        plan_id,
        user_id,
    )
    return result == "DELETE 1"