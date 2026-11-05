from datetime import date, datetime
from enum import Enum


class ActivityType(str, Enum):
    LECTURE = "lecture"
    PRACTICE = "practice"
    READING = "reading"
    SELF_STUDY = "self_study"
    EXAM_PREP = "exam_prep"


class EventType(str, Enum):
    EXAM = "exam"
    TEST = "test"
    DEADLINE = "deadline"
    OTHER = "other"


class PlanRole(str, Enum):
    """Роли, которые можно назначить участнику (совпадают с planning.plan_role)."""

    VIEWER = "viewer"
    COMMENTER = "commenter"


# Владелец хранится в plans.owner_id, а не в plan_members, поэтому в enum его нет.
OWNER_ROLE = "owner"

# Срок жизни приглашения и размер токена (secrets.token_urlsafe).
INVITE_TTL_DAYS = 7
INVITE_TOKEN_BYTES = 16


def serialize(record) -> dict:
    """Строка из БД -> словарь, пригодный для JSON (даты в ISO-формате)."""
    result = {}
    for key, value in dict(record).items():
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        result[key] = value
    return result