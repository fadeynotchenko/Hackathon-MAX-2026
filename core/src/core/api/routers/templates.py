from __future__ import annotations

from fastapi import APIRouter, Query

from core.api.dependencies import CurrentUserDep, SessionDep
from core.api.schemas.common import ErrorResponse, IdPath
from core.api.schemas.documents import TemplateSchema
from core.usecases.documents import get_template, list_templates

router = APIRouter(prefix="/templates", tags=["documents"])


@router.get(
    "",
    response_model=list[TemplateSchema],
    responses={401: {"model": ErrorResponse}},
    operation_id="list_templates",
    summary="Библиотека шаблонов",
)
async def get_templates(
    current: CurrentUserDep,
    session: SessionDep,
    slug: str | None = Query(
        default=None, max_length=64, description="Оставить только шаблон с этим слугом"
    ),
) -> list[TemplateSchema]:
    templates = await list_templates(session, user_id=current.id, slug=slug)
    return [TemplateSchema.model_validate(t) for t in templates]


@router.get(
    "/{template_id}",
    response_model=TemplateSchema,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    operation_id="get_template",
    summary="Шаблон и описание его полей",
)
async def get_one(
    template_id: IdPath, current: CurrentUserDep, session: SessionDep
) -> TemplateSchema:
    template = await get_template(session, user_id=current.id, template_id=template_id)
    return TemplateSchema.model_validate(template)
