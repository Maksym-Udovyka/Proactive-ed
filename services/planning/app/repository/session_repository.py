from datetime import datetime

import asyncpg

SESSION_COLUMNS = (
    "study_session_id, plan_id, title, activity_type, "
    "start_time, duration_minutes, created_at, updated_at"
)


async def create_session(
    pool: asyncpg.Pool,
    plan_id: int,
    title: str,
    activity_type: str,
    start_time: datetime,
    duration_minutes: int,
) -> asyncpg.Record:
    return await pool.fetchrow(
        f"""
        INSERT INTO planning.study_sessions
            (plan_id, title, activity_type, start_time, duration_minutes)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING {SESSION_COLUMNS}
        """,
        plan_id,
        title,
        activity_type,
        start_time,
        duration_minutes,
    )


async def get_session(
    pool: asyncpg.Pool, session_id: int
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        f"""
        SELECT {SESSION_COLUMNS}
        FROM planning.study_sessions
        WHERE study_session_id = $1
        """,
        session_id,
    )


async def list_sessions(
    pool: asyncpg.Pool,
    plan_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[asyncpg.Record]:
    return await pool.fetch(
        f"""
        SELECT {SESSION_COLUMNS}
        FROM planning.study_sessions
        WHERE plan_id = $1
          AND ($2::timestamptz IS NULL OR start_time >= $2)
          AND ($3::timestamptz IS NULL OR start_time < $3)
        ORDER BY start_time, study_session_id
        """,
        plan_id,
        date_from,
        date_to,
    )


async def update_session(
    pool: asyncpg.Pool, session_id: int, fields: dict
) -> asyncpg.Record | None:
    allowed = ("title", "activity_type", "start_time", "duration_minutes")
    columns = [name for name in fields if name in allowed]
    if not columns:
        return None
    assignments = ", ".join(
        f"{name} = ${index}" for index, name in enumerate(columns, start=2)
    )
    return await pool.fetchrow(
        f"""
        UPDATE planning.study_sessions SET {assignments}
        WHERE study_session_id = $1
        RETURNING {SESSION_COLUMNS}
        """,
        session_id,
        *[fields[name] for name in columns],
    )


async def delete_session(pool: asyncpg.Pool, session_id: int) -> bool:
    result = await pool.execute(
        "DELETE FROM planning.study_sessions WHERE study_session_id = $1",
        session_id,
    )
    return result == "DELETE 1"