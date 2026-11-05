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


def serialize(record) -> dict:
    """Строка из БД -> словарь, пригодный для JSON (даты в ISO-формате)."""
    result = {}
    for key, value in dict(record).items():
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        result[key] = value
    return result