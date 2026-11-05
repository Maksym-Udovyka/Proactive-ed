import secrets
from datetime import date, datetime, time, timedelta, timezone

import asyncpg

from app.domain.models import (
    INVITE_TOKEN_BYTES,
    INVITE_TTL_DAYS,
    ActivityType,
    EventType,
    PlanRole,
    serialize,
)
from app.repository import (
    event_repository,
    invite_repository,
    member_repository,
    plan_repository,
    session_repository,
)

DEFAULT_LIMIT = 50
MAX_LIMIT = 100
MAX_TOKEN_LENGTH = 100


# ---------- ошибки (routes превратит их в HTTP-ответы) ----------

class ServiceError(Exception):
    status = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationError(ServiceError):
    status = 400


class ForbiddenError(ServiceError):
    status = 403


class NotFoundError(ServiceError):
    status = 404


class ConflictError(ServiceError):
    status = 409


class GoneError(ServiceError):
    status = 410


# ---------- валидаторы полей ----------

def _title(value):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("title must be a non-empty string")
    value = value.strip()
    if len(value) > 200:
        raise ValidationError("title must be at most 200 characters")
    return value


def _description(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError("description must be a string or null")
    value = value.strip()
    if len(value) > 2000:
        raise ValidationError("description must be at most 2000 characters")
    return value or None


def _activity_type(value):
    allowed = [item.value for item in ActivityType]
    if value not in allowed:
        raise ValidationError(f"activity_type must be one of: {', '.join(allowed)}")
    return value


def _event_type(value):
    allowed = [item.value for item in EventType]
    if value not in allowed:
        raise ValidationError(f"event_type must be one of: {', '.join(allowed)}")
    return value


def _role(value):
    allowed = [item.value for item in PlanRole]
    if value not in allowed:
        raise ValidationError(f"role must be one of: {', '.join(allowed)}")
    return value


def _start_time(value):
    if not isinstance(value, str):
        raise ValidationError("start_time must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValidationError("start_time must be a valid ISO 8601 datetime")
    if parsed.tzinfo is None:
        raise ValidationError(
            "start_time must include a timezone offset, "
            "e.g. 2026-11-05T10:00:00+02:00"
        )
    return parsed


def _duration(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError("duration_minutes must be an integer")
    if not 1 <= value <= 1440:
        raise ValidationError("duration_minutes must be between 1 and 1440")
    return value


def _event_date(value):
    if not isinstance(value, str):
        raise ValidationError("event_date must be a string in YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError("event_date must be a valid date in YYYY-MM-DD format")


_PLAN_FIELDS = {"title": _title, "description": _description}
_SESSION_FIELDS = {
    "title": _title,
    "activity_type": _activity_type,
    "start_time": _start_time,
    "duration_minutes": _duration,
}
_EVENT_FIELDS = {
    "title": _title,
    "event_type": _event_type,
    "event_date": _event_date,
    "description": _description,
}
_ROLE_FIELDS = {"role": _role}


def _parse(data, validators: dict, required: tuple, partial: bool) -> dict:
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")
    result = {}
    for name, validator in validators.items():
        if name in data:
            result[name] = validator(data[name])
        elif not partial and name in required:
            raise ValidationError(f"{name} is required")
    if partial and not result:
        raise ValidationError("No fields to update")
    return result


# ---------- вспомогательные функции ----------

def parse_pagination(limit, offset) -> tuple[int, int]:
    try:
        limit = int(limit) if limit is not None else DEFAULT_LIMIT
        offset = int(offset) if offset is not None else 0
    except ValueError:
        raise ValidationError("limit and offset must be integers")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValidationError(f"limit must be between 1 and {MAX_LIMIT}")
    if offset < 0:
        raise ValidationError("offset must not be negative")
    return limit, offset


def _parse_date_param(name: str, value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"'{name}' must be a date in YYYY-MM-DD format")


def _parse_range(date_from, date_to):
    """'to' включительно: возвращаем исключающую верхнюю границу (to + 1 день)."""
    d_from = _parse_date_param("from", date_from) if date_from else None
    d_to = _parse_date_param("to", date_to) if date_to else None
    if d_from and d_to and d_from > d_to:
        raise ValidationError("'from' must not be after 'to'")
    return d_from, (d_to + timedelta(days=1)) if d_to else None


def _day_start(day: date | None) -> datetime | None:
    if day is None:
        return None
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


async def _get_plan_or_404(pool, plan_id: int, user_id: int):
    plan = await plan_repository.get_plan(pool, plan_id, user_id)
    if plan is None:
        raise NotFoundError("Plan not found")
    return plan


def _require_owner(plan) -> None:
    if plan["role"] != "owner":
        raise ForbiddenError("Only the plan owner can change this plan")


# ---------- планы ----------

async def create_plan(pool: asyncpg.Pool, user_id: int, data) -> dict:
    fields = _parse(data, _PLAN_FIELDS, required=("title",), partial=False)
    row = await plan_repository.create_plan(
        pool, user_id, fields["title"], fields.get("description")
    )
    return serialize(row)


async def list_plans(pool, user_id: int, limit=None, offset=None) -> list[dict]:
    limit, offset = parse_pagination(limit, offset)
    rows = await plan_repository.list_plans(pool, user_id, limit, offset)
    return [serialize(row) for row in rows]


async def get_plan(pool, user_id: int, plan_id: int) -> dict:
    return serialize(await _get_plan_or_404(pool, plan_id, user_id))


async def update_plan(pool, user_id: int, plan_id: int, data) -> dict:
    plan = await _get_plan_or_404(pool, plan_id, user_id)
    _require_owner(plan)
    fields = _parse(data, _PLAN_FIELDS, required=(), partial=True)
    row = await plan_repository.update_plan(pool, plan_id, user_id, fields)
    if row is None:
        raise NotFoundError("Plan not found")
    return serialize(row)


async def delete_plan(pool, user_id: int, plan_id: int) -> None:
    plan = await _get_plan_or_404(pool, plan_id, user_id)
    _require_owner(plan)
    if not await plan_repository.delete_plan(pool, plan_id, user_id):
        raise NotFoundError("Plan not found")


# ---------- учебные сессии ----------

async def _load_session(pool, user_id: int, session_id: int):
    session = await session_repository.get_session(pool, session_id)
    if session is None:
        raise NotFoundError("Session not found")
    plan = await plan_repository.get_plan(pool, session["plan_id"], user_id)
    if plan is None:
        raise NotFoundError("Session not found")
    return session, plan


async def create_session(pool, user_id: int, plan_id: int, data) -> dict:
    plan = await _get_plan_or_404(pool, plan_id, user_id)
    _require_owner(plan)
    fields = _parse(
        data, _SESSION_FIELDS, required=tuple(_SESSION_FIELDS), partial=False
    )
    row = await session_repository.create_session(
        pool,
        plan_id,
        fields["title"],
        fields["activity_type"],
        fields["start_time"],
        fields["duration_minutes"],
    )
    return serialize(row)


async def list_sessions(
    pool, user_id: int, plan_id: int, date_from=None, date_to=None
) -> list[dict]:
    await _get_plan_or_404(pool, plan_id, user_id)
    d_from, d_to = _parse_range(date_from, date_to)
    rows = await session_repository.list_sessions(
        pool, plan_id, _day_start(d_from), _day_start(d_to)
    )
    return [serialize(row) for row in rows]


async def get_session(pool, user_id: int, session_id: int) -> dict:
    session, _ = await _load_session(pool, user_id, session_id)
    return serialize(session)


async def update_session(pool, user_id: int, session_id: int, data) -> dict:
    _, plan = await _load_session(pool, user_id, session_id)
    _require_owner(plan)
    fields = _parse(data, _SESSION_FIELDS, required=(), partial=True)
    row = await session_repository.update_session(pool, session_id, fields)
    if row is None:
        raise NotFoundError("Session not found")
    return serialize(row)


async def delete_session(pool, user_id: int, session_id: int) -> None:
    _, plan = await _load_session(pool, user_id, session_id)
    _require_owner(plan)
    if not await session_repository.delete_session(pool, session_id):
        raise NotFoundError("Session not found")


# ---------- события ----------

async def _load_event(pool, user_id: int, event_id: int):
    event = await event_repository.get_event(pool, event_id)
    if event is None:
        raise NotFoundError("Event not found")
    plan = await plan_repository.get_plan(pool, event["plan_id"], user_id)
    if plan is None:
        raise NotFoundError("Event not found")
    return event, plan


async def create_event(pool, user_id: int, plan_id: int, data) -> dict:
    plan = await _get_plan_or_404(pool, plan_id, user_id)
    _require_owner(plan)
    fields = _parse(
        data,
        _EVENT_FIELDS,
        required=("title", "event_type", "event_date"),
        partial=False,
    )
    row = await event_repository.create_event(
        pool,
        plan_id,
        fields["title"],
        fields["event_type"],
        fields["event_date"],
        fields.get("description"),
    )
    return serialize(row)


async def list_events(
    pool, user_id: int, plan_id: int, date_from=None, date_to=None
) -> list[dict]:
    await _get_plan_or_404(pool, plan_id, user_id)
    d_from, d_to = _parse_range(date_from, date_to)
    rows = await event_repository.list_events(pool, plan_id, d_from, d_to)
    return [serialize(row) for row in rows]


async def get_event(pool, user_id: int, event_id: int) -> dict:
    event, _ = await _load_event(pool, user_id, event_id)
    return serialize(event)


async def update_event(pool, user_id: int, event_id: int, data) -> dict:
    _, plan = await _load_event(pool, user_id, event_id)
    _require_owner(plan)
    fields = _parse(data, _EVENT_FIELDS, required=(), partial=True)
    row = await event_repository.update_event(pool, event_id, fields)
    if row is None:
        raise NotFoundError("Event not found")
    return serialize(row)


async def delete_event(pool, user_id: int, event_id: int) -> None:
    _, plan = await _load_event(pool, user_id, event_id)
    _require_owner(plan)
    if not await event_repository.delete_event(pool, event_id):
        raise NotFoundError("Event not found")


# ---------- хронологический просмотр ----------

async def get_timeline(
    pool, user_id: int, plan_id: int, date_from=None, date_to=None
) -> list[dict]:
    await _get_plan_or_404(pool, plan_id, user_id)
    d_from, d_to = _parse_range(date_from, date_to)
    sessions = await session_repository.list_sessions(
        pool, plan_id, _day_start(d_from), _day_start(d_to)
    )
    events = await event_repository.list_events(pool, plan_id, d_from, d_to)

    items = [
        (row["start_time"], {"kind": "session", **serialize(row)})
        for row in sessions
    ]
    items += [
        (_day_start(row["event_date"]), {"kind": "event", **serialize(row)})
        for row in events
    ]
    items.sort(key=lambda item: item[0])
    return [item for _, item in items]


# ---------- участники (НОВОЕ) ----------

async def list_members(pool, user_id: int, plan_id: int) -> list[dict]:
    await _get_plan_or_404(pool, plan_id, user_id)
    rows = await member_repository.list_members(pool, plan_id)
    return [serialize(row) for row in rows]


async def update_member_role(
    pool, user_id: int, plan_id: int, member_id: int, data
) -> dict:
    plan = await _get_plan_or_404(pool, plan_id, user_id)
    _require_owner(plan)
    if member_id == plan["owner_id"]:
        raise ValidationError("The owner's role cannot be changed")
    fields = _parse(data, _ROLE_FIELDS, required=("role",), partial=False)
    row = await member_repository.update_role(
        pool, plan_id, member_id, fields["role"]
    )
    if row is None:
        raise NotFoundError("Member not found")
    return serialize(row)


async def remove_member(pool, user_id: int, plan_id: int, member_id: int) -> None:
    plan = await _get_plan_or_404(pool, plan_id, user_id)
    _require_owner(plan)
    if member_id == plan["owner_id"]:
        raise ValidationError("The owner cannot be removed from the plan")
    if not await member_repository.remove_member(pool, plan_id, member_id):
        raise NotFoundError("Member not found")


async def leave_plan(pool, user_id: int, plan_id: int) -> None:
    plan = await _get_plan_or_404(pool, plan_id, user_id)
    if plan["role"] == "owner":
        raise ValidationError("The owner cannot leave the plan")
    if not await member_repository.remove_member(pool, plan_id, user_id):
        raise NotFoundError("Plan not found")


# ---------- приглашения (НОВОЕ) ----------

async def create_invite(pool, user_id: int, plan_id: int, data) -> dict:
    plan = await _get_plan_or_404(pool, plan_id, user_id)
    _require_owner(plan)
    fields = _parse(data, _ROLE_FIELDS, required=(), partial=False)
    role = fields.get("role", PlanRole.VIEWER.value)
    row = await invite_repository.create_invite(
        pool,
        plan_id,
        role,
        secrets.token_urlsafe(INVITE_TOKEN_BYTES),
        user_id,
        INVITE_TTL_DAYS,
    )
    return serialize(row)


async def list_invites(pool, user_id: int, plan_id: int) -> list[dict]:
    plan = await _get_plan_or_404(pool, plan_id, user_id)
    _require_owner(plan)
    rows = await invite_repository.list_active_invites(pool, plan_id)
    return [serialize(row) for row in rows]


async def revoke_invite(pool, user_id: int, plan_id: int, invite_id: int) -> None:
    plan = await _get_plan_or_404(pool, plan_id, user_id)
    _require_owner(plan)
    if not await invite_repository.delete_invite(pool, plan_id, invite_id):
        raise NotFoundError("Invite not found")


def _check_token(token: str) -> str:
    if not token or len(token) > MAX_TOKEN_LENGTH:
        raise NotFoundError("Invite not found")
    return token


async def get_invite_preview(pool, user_id: int, token: str) -> dict:
    """Предпросмотр для экрана вступления.

    state: valid | own_plan | already_member | used | expired
    (тот же порядок проверок, что и при вступлении).
    """
    row = await invite_repository.get_invite_preview(pool, _check_token(token))
    if row is None:
        raise NotFoundError("Invite not found")

    if row["owner_id"] == user_id:
        state = "own_plan"
    elif await member_repository.get_member(pool, row["plan_id"], user_id):
        state = "already_member"
    elif row["used_at"] is not None:
        state = "used"
    elif row["expired"]:
        state = "expired"
    else:
        state = "valid"

    return {
        "plan_id": row["plan_id"],
        "plan_title": row["plan_title"],
        "role": row["role"],
        "invited_by_name": row["invited_by_name"],
        "expires_at": row["expires_at"].isoformat(),
        "state": state,
    }


async def accept_invite(pool, user_id: int, token: str) -> dict:
    status, plan_id, role = await invite_repository.accept_invite(
        pool, _check_token(token), user_id
    )
    if status == "not_found":
        raise NotFoundError("Invite not found")
    if status == "own_plan":
        raise ConflictError("This is your own plan")
    if status == "already_member":
        raise ConflictError("You are already a member of this plan")
    if status == "used":
        raise ConflictError("This invite has already been used")
    if status == "expired":
        raise GoneError("This invite has expired")
    return {"plan_id": plan_id, "role": role}