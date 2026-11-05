import asyncpg

_NAME_EXPR = "COALESCE(NULLIF(u.display_name, ''), u.first_name)"

_INVITE_COLUMNS = (
    "plan_invite_id, plan_id, role::text AS role, token, created_by, expires_at"
)


async def create_invite(
    pool: asyncpg.Pool,
    plan_id: int,
    role: str,
    token: str,
    created_by: int,
    expires_in_days: int,
) -> asyncpg.Record:
    """Срок считается по времени БД, чтобы не зависеть от часов приложения."""
    return await pool.fetchrow(
        f"""
        INSERT INTO planning.plan_invites
            (plan_id, role, token, created_by, expires_at)
        VALUES ($1, $2::planning.plan_role, $3, $4,
                now() + make_interval(days => $5))
        RETURNING {_INVITE_COLUMNS}
        """,
        plan_id,
        role,
        token,
        created_by,
        expires_in_days,
    )


async def list_active_invites(
    pool: asyncpg.Pool, plan_id: int
) -> list[asyncpg.Record]:
    """Не использованные и не просроченные, новые первыми."""
    return await pool.fetch(
        f"""
        SELECT {_INVITE_COLUMNS}
        FROM planning.plan_invites
        WHERE plan_id = $1 AND used_at IS NULL AND expires_at > now()
        ORDER BY plan_invite_id DESC
        """,
        plan_id,
    )


async def delete_invite(pool: asyncpg.Pool, plan_id: int, invite_id: int) -> bool:
    """Отзыв: удаляет только неиспользованное приглашение этого плана."""
    result = await pool.execute(
        """
        DELETE FROM planning.plan_invites
        WHERE plan_invite_id = $1 AND plan_id = $2 AND used_at IS NULL
        """,
        invite_id,
        plan_id,
    )
    return result == "DELETE 1"


async def get_invite_preview(
    pool: asyncpg.Pool, token: str
) -> asyncpg.Record | None:
    """Данные для экрана вступления. Доступно любому вошедшему пользователю."""
    return await pool.fetchrow(
        f"""
        SELECT i.plan_id, p.owner_id, p.title AS plan_title,
               i.role::text AS role, i.created_by,
               {_NAME_EXPR} AS invited_by_name,
               i.expires_at, i.used_at,
               (i.expires_at <= now()) AS expired
        FROM planning.plan_invites i
        JOIN planning.plans p ON p.plan_id = i.plan_id
        LEFT JOIN auth.users u ON u.user_id = i.created_by
        WHERE i.token = $1
        """,
        token,
    )


async def accept_invite(
    pool: asyncpg.Pool, token: str, user_id: int
) -> tuple[str, int | None, str | None]:
    """Вступление по приглашению одной транзакцией.

    Строка приглашения блокируется (FOR UPDATE), поэтому две одновременные
    попытки не смогут использовать одноразовую ссылку дважды.

    Возвращает (status, plan_id, role), status один из:
    not_found, own_plan, already_member, used, expired, accepted.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            invite = await conn.fetchrow(
                """
                SELECT i.plan_invite_id, i.plan_id, i.role::text AS role,
                       i.used_at, (i.expires_at <= now()) AS expired,
                       p.owner_id
                FROM planning.plan_invites i
                JOIN planning.plans p ON p.plan_id = i.plan_id
                WHERE i.token = $1
                FOR UPDATE OF i
                """,
                token,
            )
            if invite is None:
                return "not_found", None, None

            plan_id = invite["plan_id"]
            role = invite["role"]

            if invite["owner_id"] == user_id:
                return "own_plan", plan_id, role

            is_member = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM planning.plan_members
                    WHERE plan_id = $1 AND user_id = $2
                )
                """,
                plan_id,
                user_id,
            )
            if is_member:
                return "already_member", plan_id, role

            if invite["used_at"] is not None:
                return "used", plan_id, role
            if invite["expired"]:
                return "expired", plan_id, role

            inserted = await conn.fetchval(
                """
                INSERT INTO planning.plan_members (plan_id, user_id, role)
                VALUES ($1, $2, $3::planning.plan_role)
                ON CONFLICT (plan_id, user_id) DO NOTHING
                RETURNING plan_member_id
                """,
                plan_id,
                user_id,
                role,
            )
            if inserted is None:
                # Параллельно вступил по другой ссылке: ссылку не тратим.
                return "already_member", plan_id, role

            await conn.execute(
                """
                UPDATE planning.plan_invites
                SET used_by = $2, used_at = now()
                WHERE plan_invite_id = $1
                """,
                invite["plan_invite_id"],
                user_id,
            )
            return "accepted", plan_id, role