from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response, status

from core.api.dependencies import CurrentUserDep, SessionDep, StateDep
from core.api.previews import (
    PREVIEW_RESPONSES,
    PageQuery,
    PreviewSize,
    SizeQuery,
    preview_response,
)
from core.api.schemas.common import ErrorResponse, IdPath, OkResponse
from core.api.schemas.documents import TemplateImportSchema, TemplateRequest, TemplateSchema
from core.api.uploads import DOCUMENT_TYPES, binary_body, read_body
from core.domain.places import Place
from core.usecases.agent import import_template_file
from core.usecases.documents import (
    TemplateField,
    TemplateInput,
    create_template,
    delete_template,
    get_template,
    keep_template,
    list_templates,
    template_preview,
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
            TemplateField(
                key=field.key,
                label=field.label,
                type=field.type,
                required=field.required,
                hint=field.hint,
                carry_over=field.carry_over,
                today_by_default=field.today_by_default,
                default=field.default,
                places=tuple(Place(place.text, place.before) for place in field.places),
            )
            for field in payload.fields
        ),
        file_id=payload.file_id,
        kind=payload.kind,
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


@router.post(
    "/import",
    response_model=TemplateImportSchema,
    responses=_ERRORS | {413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}},
    operation_id="import_template",
    summary="Разобрать файл-образец для своего шаблона",
    description=(
        "Находит места для данных: метки {{Название поля}} в файле, а без них — "
        "с помощником. Шаблон не создаётся: черновик проверяет человек и "
        "сохраняет через POST /templates с file_id."
    ),
    openapi_extra=binary_body(*DOCUMENT_TYPES, description="Образец документа: DOCX или PDF"),
)
async def import_file(
    request: Request,
    current: CurrentUserDep,
    session: SessionDep,
    state: StateDep,
    filename: str = Query(default="", max_length=255, description="Имя файла у пользователя"),
) -> TemplateImportSchema:
    limit = state.files_config.media_max_bytes
    result = await import_template_file(
        session,
        user_id=current.id,
        data=await read_body(request, max_bytes=limit),
        filename=filename,
        llm=state.llm,
        max_bytes=limit,
    )
    return TemplateImportSchema.model_validate(result)


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


@router.get(
    "/{template_id}/preview",
    response_class=Response,
    responses=PREVIEW_RESPONSES,
    operation_id="template_preview",
    summary="Пустой бланк шаблона картинкой страницы",
)
async def preview(
    template_id: IdPath,
    current: CurrentUserDep,
    session: SessionDep,
    state: StateDep,
    page: int = PageQuery,
    size: PreviewSize = SizeQuery,
) -> Response:
    found = await template_preview(
        session,
        user_id=current.id,
        template_id=template_id,
        page=page,
        size=size,
        cfg=state.files_config,
    )
    return preview_response(found)


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


@router.post(
    "/{template_id}/keep",
    response_model=TemplateSchema,
    responses=_ERRORS,
    operation_id="keep_template",
    summary="Сохранить в каталог шаблон документа, сделанного по файлу",
    description="Следующий такой же документ начнётся с этого шаблона.",
)
async def keep(template_id: IdPath, current: CurrentUserDep, session: SessionDep) -> TemplateSchema:
    kept = await keep_template(session, user_id=current.id, template_id=template_id)
    return TemplateSchema.model_validate(kept)


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
