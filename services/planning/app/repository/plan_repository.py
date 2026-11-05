import asyncpg

PLAN_COLUMNS = "plan_id, owner_id, title, description, created_at, updated_at"

_ROLE_EXPR = "CASE WHEN p.owner_id = $2 THEN 'owner' ELSE m.role::text END AS role"

_ACCESS_JOIN = """
    FROM planning.plans p
    LEFT JOIN planning.plan_members m
        ON m.plan_id = p.plan_id AND m.user_id = $2
"""

_ACCESS_FILTER = "(p.owner_id = $2 OR m.user_id IS NOT NULL)"


async def create_plan(
    pool: asyncpg.Pool, owner_id: int, title: str, description: str | None
) -> asyncpg.Record:
    return await pool.fetchrow(
        f"""
        INSERT INTO planning.plans (owner_id, title, description)
        VALUES ($1, $2, $3)
        RETURNING {PLAN_COLUMNS}, 'owner' AS role
        """,
        owner_id,
        title,
        description,
    )


async def get_plan(
    pool: asyncpg.Pool, plan_id: int, user_id: int
) -> asyncpg.Record | None:
    """План, если пользователь его владелец или участник. Иначе None."""
    return await pool.fetchrow(
        f"""
        SELECT p.plan_id, p.owner_id, p.title, p.description,
               p.created_at, p.updated_at, {_ROLE_EXPR}
        {_ACCESS_JOIN}
        WHERE p.plan_id = $1 AND {_ACCESS_FILTER}
        """,
        plan_id,
        user_id,
    )


async def list_plans(
    pool: asyncpg.Pool, user_id: int, limit: int, offset: int
) -> list[asyncpg.Record]:
    return await pool.fetch(
        f"""
        SELECT p.plan_id, p.owner_id, p.title, p.description,
               p.created_at, p.updated_at, {_ROLE_EXPR}
        {_ACCESS_JOIN}
        WHERE {_ACCESS_FILTER}
        ORDER BY p.created_at DESC, p.plan_id DESC
        LIMIT $1 OFFSET $3
        """,
        limit,
        user_id,
        offset,
    )


async def update_plan(
    pool: asyncpg.Pool, plan_id: int, owner_id: int, fields: dict
) -> asyncpg.Record | None:
    """Обновляет только переданные поля. Менять план может лишь владелец."""
    allowed = ("title", "description")
    columns = [name for name in fields if name in allowed]
    if not columns:
        return None
    assignments = ", ".join(
        f"{name} = ${index}" for index, name in enumerate(columns, start=3)
    )
    return await pool.fetchrow(
        f"""
        UPDATE planning.plans SET {assignments}
        WHERE plan_id = $1 AND owner_id = $2
        RETURNING {PLAN_COLUMNS}, 'owner' AS role
        """,
        plan_id,
        owner_id,
        *[fields[name] for name in columns],
    )


async def delete_plan(pool: asyncpg.Pool, plan_id: int, owner_id: int) -> bool:
    result = await pool.execute(
        "DELETE FROM planning.plans WHERE plan_id = $1 AND owner_id = $2",
        plan_id,
        owner_id,
    )
    return result == "DELETE 1"