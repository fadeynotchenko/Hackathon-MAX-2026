"""Вход через initData мини-аппа, продление сессии, выход.

Access-токен клиент держит в памяти и шлёт в Authorization: Bearer.
Refresh-токен уходит только в httpOnly-cookie с путём /api/v1/auth: JS до
него не дотягивается, а браузер не приложит его к обычным запросам API.
Если браузер режет сторонние cookie (Safari во фрейме), refresh не пройдёт —
клиент тогда просто входит заново по initData, который внутри MAX есть всегда.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status

from core.api.dependencies import SessionDep, StateDep
from core.api.schemas.auth import MaxLoginRequest, SessionResponse
from core.api.schemas.common import ErrorResponse, OkResponse
from core.api.schemas.user import UserProfileSchema
from core.domain.exceptions import ForbiddenError, UnauthorizedError
from core.usecases.auth import IssuedSession, login_with_init_data, logout, refresh_session

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "maxapp_refresh"
_COOKIE_PATH = "/api/v1/auth"
RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


def reject_cross_site(request: Request) -> None:
    """CSRF-защита ручек, которые работают только по cookie.

    С SameSite=None браузер приложит refresh-cookie и к форме с чужого сайта.
    Fetch из самого мини-аппа (даже во фрейме max.ru) идёт с Sec-Fetch-Site
    same-origin; cross-site — это только чужая страница. Старые браузеры без
    заголовка пропускаем: у них нет и SameSite=None."""
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise ForbiddenError("Запрос с другого сайта", code="auth.cross_site")


SameSiteDep = Annotated[None, Depends(reject_cross_site)]


def _session_response(
    response: Response, issued: IssuedSession, state: StateDep
) -> SessionResponse:
    # Веб-клиент MAX открывает мини-апп во фрейме со своего домена: для браузера
    # наш origin — третья сторона, и cookie с SameSite=Lax к запросам не приложится.
    # Поэтому в проде SameSite=None (требует Secure); в dev по http это невозможно,
    # там мини-апп открыт напрямую и Lax достаточно.
    production = state.app_config.is_production
    response.set_cookie(
        REFRESH_COOKIE,
        issued.refresh_token,
        max_age=state.auth_config.refresh_ttl_seconds,
        path=_COOKIE_PATH,
        httponly=True,
        secure=production,
        samesite="none" if production else "lax",
    )
    return SessionResponse(
        access_token=issued.access_token,
        expires_in=state.auth_config.access_ttl_seconds,
        user=UserProfileSchema.model_validate(issued.profile),
    )


@router.post(
    "/max",
    response_model=SessionResponse,
    responses={401: {"model": ErrorResponse}},
    operation_id="login_max",
    summary="Вход по initData мини-приложения MAX",
)
async def login_max(
    body: MaxLoginRequest, response: Response, state: StateDep, session: SessionDep
) -> SessionResponse:
    issued = await login_with_init_data(
        session, body.init_data, cfg=state.auth_config, admin_ids=state.app_config.admin_max_ids
    )
    return _session_response(response, issued, state)


@router.post(
    "/refresh",
    response_model=SessionResponse,
    responses={401: {"model": ErrorResponse}},
    operation_id="refresh_session",
    summary="Новый access-токен по refresh-cookie",
)
async def refresh(
    response: Response,
    state: StateDep,
    session: SessionDep,
    refresh_token: RefreshCookie = None,
    _origin: SameSiteDep = None,
) -> SessionResponse:
    if not refresh_token:
        raise UnauthorizedError("Сессия отсутствует", code="auth.refresh.missing")
    issued = await refresh_session(
        session, refresh_token, cfg=state.auth_config, admin_ids=state.app_config.admin_max_ids
    )
    return _session_response(response, issued, state)


@router.post(
    "/logout",
    response_model=OkResponse,
    status_code=status.HTTP_200_OK,
    operation_id="logout",
    summary="Отозвать сессию и очистить cookie",
)
async def logout_route(
    response: Response,
    state: StateDep,
    session: SessionDep,
    refresh_token: RefreshCookie = None,
    _origin: SameSiteDep = None,
) -> OkResponse:
    if refresh_token:
        await logout(session, refresh_token)
    # Атрибуты те же, что при установке: во фрейме браузер игнорирует Set-Cookie
    # с SameSite=Lax, и cookie пережила бы выход.
    production = state.app_config.is_production
    response.delete_cookie(
        REFRESH_COOKIE,
        path=_COOKIE_PATH,
        httponly=True,
        secure=production,
        samesite="none" if production else "lax",
    )
    return OkResponse()
