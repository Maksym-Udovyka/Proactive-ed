import functools

from aiohttp import web

from app.core import service

API_PREFIX = "/api/planning/v1"
MAX_ID = 2_147_483_647  # предел INT в PostgreSQL


# ---------- вспомогательные функции ----------

def handle_errors(handler):
    """Превращает ошибки сервиса в JSON-ответы с нужным HTTP-статусом."""

    @functools.wraps(handler)
    async def wrapper(request: web.Request) -> web.Response:
        try:
            return await handler(request)
        except service.ServiceError as error:
            return web.json_response({"error": error.message}, status=error.status)

    return wrapper


def _id(request: web.Request, name: str) -> int:
    value = int(request.match_info[name])
    if value > MAX_ID:
        raise service.NotFoundError("Not found")
    return value


async def _read_json(request: web.Request):
    try:
        return await request.json()
    except ValueError:
        raise service.ValidationError("Request body must be valid JSON")


def _pool(request: web.Request):
    return request.app["db"]


def _user(request: web.Request) -> int:
    return request["user_id"]


# ---------- health ----------

async def health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "planning"})


# ---------- планы ----------

@handle_errors
async def list_plans(request: web.Request) -> web.Response:
    result = await service.list_plans(
        _pool(request),
        _user(request),
        request.query.get("limit"),
        request.query.get("offset"),
    )
    return web.json_response(result)


@handle_errors
async def create_plan(request: web.Request) -> web.Response:
    data = await _read_json(request)
    result = await service.create_plan(_pool(request), _user(request), data)
    return web.json_response(result, status=201)


@handle_errors
async def get_plan(request: web.Request) -> web.Response:
    result = await service.get_plan(
        _pool(request), _user(request), _id(request, "plan_id")
    )
    return web.json_response(result)


@handle_errors
async def update_plan(request: web.Request) -> web.Response:
    data = await _read_json(request)
    result = await service.update_plan(
        _pool(request), _user(request), _id(request, "plan_id"), data
    )
    return web.json_response(result)


@handle_errors
async def delete_plan(request: web.Request) -> web.Response:
    await service.delete_plan(_pool(request), _user(request), _id(request, "plan_id"))
    return web.Response(status=204)


# ---------- сессии ----------

@handle_errors
async def list_sessions(request: web.Request) -> web.Response:
    result = await service.list_sessions(
        _pool(request),
        _user(request),
        _id(request, "plan_id"),
        request.query.get("from"),
        request.query.get("to"),
    )
    return web.json_response(result)


@handle_errors
async def create_session(request: web.Request) -> web.Response:
    data = await _read_json(request)
    result = await service.create_session(
        _pool(request), _user(request), _id(request, "plan_id"), data
    )
    return web.json_response(result, status=201)


@handle_errors
async def get_session(request: web.Request) -> web.Response:
    result = await service.get_session(
        _pool(request), _user(request), _id(request, "session_id")
    )
    return web.json_response(result)


@handle_errors
async def update_session(request: web.Request) -> web.Response:
    data = await _read_json(request)
    result = await service.update_session(
        _pool(request), _user(request), _id(request, "session_id"), data
    )
    return web.json_response(result)


@handle_errors
async def delete_session(request: web.Request) -> web.Response:
    await service.delete_session(
        _pool(request), _user(request), _id(request, "session_id")
    )
    return web.Response(status=204)


# ---------- события ----------

@handle_errors
async def list_events(request: web.Request) -> web.Response:
    result = await service.list_events(
        _pool(request),
        _user(request),
        _id(request, "plan_id"),
        request.query.get("from"),
        request.query.get("to"),
    )
    return web.json_response(result)


@handle_errors
async def create_event(request: web.Request) -> web.Response:
    data = await _read_json(request)
    result = await service.create_event(
        _pool(request), _user(request), _id(request, "plan_id"), data
    )
    return web.json_response(result, status=201)


@handle_errors
async def get_event(request: web.Request) -> web.Response:
    result = await service.get_event(
        _pool(request), _user(request), _id(request, "event_id")
    )
    return web.json_response(result)


@handle_errors
async def update_event(request: web.Request) -> web.Response:
    data = await _read_json(request)
    result = await service.update_event(
        _pool(request), _user(request), _id(request, "event_id"), data
    )
    return web.json_response(result)


@handle_errors
async def delete_event(request: web.Request) -> web.Response:
    await service.delete_event(
        _pool(request), _user(request), _id(request, "event_id")
    )
    return web.Response(status=204)


# ---------- хронология ----------

@handle_errors
async def get_timeline(request: web.Request) -> web.Response:
    result = await service.get_timeline(
        _pool(request),
        _user(request),
        _id(request, "plan_id"),
        request.query.get("from"),
        request.query.get("to"),
    )
    return web.json_response(result)


# ---------- регистрация маршрутов ----------

def setup_routes(app: web.Application) -> None:
    p = API_PREFIX
    router = app.router

    router.add_get(f"{p}/health", health)

    router.add_get(f"{p}/plans", list_plans)
    router.add_post(f"{p}/plans", create_plan)
    router.add_get(p + r"/plans/{plan_id:\d+}", get_plan)
    router.add_patch(p + r"/plans/{plan_id:\d+}", update_plan)
    router.add_delete(p + r"/plans/{plan_id:\d+}", delete_plan)

    router.add_get(p + r"/plans/{plan_id:\d+}/sessions", list_sessions)
    router.add_post(p + r"/plans/{plan_id:\d+}/sessions", create_session)
    router.add_get(p + r"/sessions/{session_id:\d+}", get_session)
    router.add_patch(p + r"/sessions/{session_id:\d+}", update_session)
    router.add_delete(p + r"/sessions/{session_id:\d+}", delete_session)

    router.add_get(p + r"/plans/{plan_id:\d+}/events", list_events)
    router.add_post(p + r"/plans/{plan_id:\d+}/events", create_event)
    router.add_get(p + r"/events/{event_id:\d+}", get_event)
    router.add_patch(p + r"/events/{event_id:\d+}", update_event)
    router.add_delete(p + r"/events/{event_id:\d+}", delete_event)

    router.add_get(p + r"/plans/{plan_id:\d+}/timeline", get_timeline)