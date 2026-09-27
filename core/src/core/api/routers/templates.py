from __future__ import annotations

from fastapi import APIRouter, Query, status

from core.api.dependencies import CurrentUserDep, SessionDep
from core.api.schemas.common import ErrorResponse, IdPath, OkResponse
from core.api.schemas.documents import TemplateRequest, TemplateSchema
from core.domain.documents import FieldSpec
from core.usecases.documents import (
    TemplateInput,
    create_template,
    delete_template,
    get_template,
    list_templates,
    update_template,
)

router = APIRouter(prefix="/templates", tags=["documents"])
_ERRORS = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


def _input(payload: TemplateRequest) -> TemplateInput:
    return TemplateInput(
        title=payload.title,
        description=payload.description,
        body=payload.body,
        fields=tuple(
            FieldSpec(
                key=field.key,
                label=field.label,
                type=field.type,
                required=field.required,
                hint=field.hint,
                carry_over=field.carry_over,
                today_by_default=field.today_by_default,
            )
            for field in payload.fields
        ),
    )


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


@router.post(
    "",
    response_model=TemplateSchema,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    operation_id="create_template",
    summary="Сохранить свой шаблон",
)
async def create(
    payload: TemplateRequest, current: CurrentUserDep, session: SessionDep
) -> TemplateSchema:
    created = await create_template(session, user_id=current.id, data=_input(payload))
    return TemplateSchema.model_validate(created)


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


@router.put(
    "/{template_id}",
    response_model=TemplateSchema,
    responses=_ERRORS,
    operation_id="update_template",
    summary="Изменить свой шаблон",
    description="Документы, созданные раньше, сохраняют прежний текст шаблона.",
)
async def update(
    template_id: IdPath, payload: TemplateRequest, current: CurrentUserDep, session: SessionDep
) -> TemplateSchema:
    updated = await update_template(
        session, user_id=current.id, template_id=template_id, data=_input(payload)
    )
    return TemplateSchema.model_validate(updated)


@router.delete(
    "/{template_id}",
    response_model=OkResponse,
    responses=_ERRORS,
    operation_id="delete_template",
    summary="Удалить свой шаблон",
    description="Шаблон пропадает из библиотеки; документы на нём остаются в архиве.",
)
async def delete(template_id: IdPath, current: CurrentUserDep, session: SessionDep) -> OkResponse:
    await delete_template(session, user_id=current.id, template_id=template_id)
    return OkResponse()
