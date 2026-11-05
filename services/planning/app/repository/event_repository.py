from datetime import date

import asyncpg

EVENT_COLUMNS = (
    "event_id, plan_id, title, event_type, event_date, "
    "description, created_at, updated_at"
)


async def create_event(
    pool: asyncpg.Pool,
    plan_id: int,
    title: str,
    event_type: str,
    event_date: date,
    description: str | None,
) -> asyncpg.Record:
    return await pool.fetchrow(
        f"""
        INSERT INTO planning.events
            (plan_id, title, event_type, event_date, description)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING {EVENT_COLUMNS}
        """,
        plan_id,
        title,
        event_type,
        event_date,
        description,
    )


async def get_event(pool: asyncpg.Pool, event_id: int) -> asyncpg.Record | None:
    return await pool.fetchrow(
        f"SELECT {EVENT_COLUMNS} FROM planning.events WHERE event_id = $1",
        event_id,
    )


async def list_events(
    pool: asyncpg.Pool,
    plan_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[asyncpg.Record]:
    return await pool.fetch(
        f"""
        SELECT {EVENT_COLUMNS}
        FROM planning.events
        WHERE plan_id = $1
          AND ($2::date IS NULL OR event_date >= $2)
          AND ($3::date IS NULL OR event_date < $3)
        ORDER BY event_date, event_id
        """,
        plan_id,
        date_from,
        date_to,
    )


async def update_event(
    pool: asyncpg.Pool, event_id: int, fields: dict
) -> asyncpg.Record | None:
    allowed = ("title", "event_type", "event_date", "description")
    columns = [name for name in fields if name in allowed]
    if not columns:
        return None
    assignments = ", ".join(
        f"{name} = ${index}" for index, name in enumerate(columns, start=2)
    )
    return await pool.fetchrow(
        f"""
        UPDATE planning.events SET {assignments}
        WHERE event_id = $1
        RETURNING {EVENT_COLUMNS}
        """,
        event_id,
        *[fields[name] for name in columns],
    )


async def delete_event(pool: asyncpg.Pool, event_id: int) -> bool:
    result = await pool.execute(
        "DELETE FROM planning.events WHERE event_id = $1", event_id
    )
    return result == "DELETE 1"