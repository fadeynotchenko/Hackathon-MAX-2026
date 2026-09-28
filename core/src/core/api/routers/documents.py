from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Query, Request, Response, status

from core.api.dependencies import CurrentUserDep, RedisDep, SessionDep, StateDep
from core.api.schemas.common import ErrorResponse, IdPath, OkResponse
from core.api.schemas.documents import (
    ConfirmFieldsRequest,
    CopyDocumentRequest,
    CreateDocumentRequest,
    DocumentFactSchema,
    DocumentFileSchema,
    DocumentImportSchema,
    DocumentPartiesRequest,
    DocumentSchema,
    DocumentSummarySchema,
    RenderRequest,
    SendDocumentRequest,
    SendDocumentResponse,
    SetFieldsRequest,
)
from core.api.uploads import DOCUMENT_TYPES, binary_body, read_body
from core.db.repositories import DownloadTokenRepository
from core.domain.documents import FieldValue
from core.usecases.agent import document_from_file
from core.usecases.documents import (
    UNSET,
    confirm_fields,
    copy_document,
    create_draft,
    delete_document,
    document_history,
    get_document,
    list_document_files,
    list_documents,
    load_document_file,
    load_file_by_token,
    render_document,
    send_document_to_chat,
    set_fields,
    set_parties,
)
from core.usecases.documents.files import MEDIA_TYPES

router = APIRouter(prefix="/documents", tags=["documents"])
_ERRORS = {401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}


@router.post(
    "",
    response_model=DocumentSchema,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    operation_id="create_document",
    summary="Создать документ из шаблона",
)
async def create(
    payload: CreateDocumentRequest, current: CurrentUserDep, session: SessionDep
) -> DocumentSchema:
    document = await create_draft(
        session,
        user_id=current.id,
        template_id=payload.template_id,
        counterparty_id=payload.counterparty_id,
        organization_id=payload.organization_id,
        title=payload.title,
    )
    return DocumentSchema.model_validate(document)


@router.post(
    "/import",
    response_model=DocumentImportSchema,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS
    | {413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    operation_id="import_document",
    summary="Документ по своему файлу: поменять данные, оставив оформление",
    description=(
        "Находит в файле места для данных (метки {{Название поля}}, помощник или "
        "линейки и реквизиты) и создаёт документ, где значения полей — как в файле. "
        "Дальше документ правится и собирается как любой другой: DOCX — в копии "
        "присланного файла, из PDF переносится только текст."
    ),
    openapi_extra=binary_body(*DOCUMENT_TYPES, description="Документ: DOCX или PDF"),
)
async def import_file(
    request: Request,
    current: CurrentUserDep,
    session: SessionDep,
    state: StateDep,
    filename: str = Query(default="", max_length=255, description="Имя файла у пользователя"),
) -> DocumentImportSchema:
    limit = state.files_config.media_max_bytes
    result = await document_from_file(
        session,
        user_id=current.id,
        data=await read_body(request, max_bytes=limit),
        filename=filename,
        llm=state.llm,
        max_bytes=limit,
    )
    return DocumentImportSchema.model_validate(result)


@router.get(
    "",
    response_model=list[DocumentSummarySchema],
    responses={401: {"model": ErrorResponse}},
    operation_id="list_documents",
    summary="История документов",
)
async def get_all(current: CurrentUserDep, session: SessionDep) -> list[DocumentSummarySchema]:
    documents = await list_documents(session, user_id=current.id)
    return [DocumentSummarySchema.model_validate(d) for d in documents]


@router.get(
    "/{document_id}",
    response_model=DocumentSchema,
    responses=_ERRORS,
    operation_id="get_document",
    summary="Документ с предпросмотром",
)
async def get_one(
    document_id: IdPath, current: CurrentUserDep, session: SessionDep
) -> DocumentSchema:
    document = await get_document(session, user_id=current.id, document_id=document_id)
    return DocumentSchema.model_validate(document)


@router.get(
    "/{document_id}/history",
    response_model=list[DocumentFactSchema],
    responses=_ERRORS,
    operation_id="document_history",
    summary="Путь документа: создан, готов, собран, отправлен, доставлен",
)
async def history(
    document_id: IdPath, current: CurrentUserDep, session: SessionDep
) -> list[DocumentFactSchema]:
    facts = await document_history(session, user_id=current.id, document_id=document_id)
    return [DocumentFactSchema.model_validate(fact) for fact in facts]


@router.post(
    "/{document_id}/copy",
    response_model=DocumentSchema,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    operation_id="copy_document",
    summary="Новый документ на основе этого: без номера и дат, со свежими реквизитами",
)
async def copy(
    document_id: IdPath,
    current: CurrentUserDep,
    session: SessionDep,
    payload: CopyDocumentRequest | None = None,
) -> DocumentSchema:
    document = await copy_document(
        session,
        user_id=current.id,
        document_id=document_id,
        title=payload.title if payload else None,
    )
    return DocumentSchema.model_validate(document)


@router.patch(
    "/{document_id}/fields",
    response_model=DocumentSchema,
    responses=_ERRORS,
    operation_id="set_document_fields",
    summary="Заполнить поля документа",
)
async def patch_fields(
    document_id: IdPath,
    payload: SetFieldsRequest,
    current: CurrentUserDep,
    session: SessionDep,
) -> DocumentSchema:
    values = {
        key: FieldValue(
            value=item.value,
            source=item.source,
            confidence=item.confidence,
            confirmed=item.confirmed,
            fragment=item.fragment,
        )
        for key, item in payload.values.items()
    }
    document = await set_fields(
        session,
        user_id=current.id,
        document_id=document_id,
        values=values,
        title=payload.title,
    )
    return DocumentSchema.model_validate(document)


@router.patch(
    "/{document_id}/parties",
    response_model=DocumentSchema,
    responses=_ERRORS,
    operation_id="set_document_parties",
    summary="Выбрать, от кого и кому документ",
)
async def patch_parties(
    document_id: IdPath,
    payload: DocumentPartiesRequest,
    current: CurrentUserDep,
    session: SessionDep,
) -> DocumentSchema:
    # Нет поля в теле — сторону не трогаем; null — отвязать карточку.
    given = payload.model_fields_set
    document = await set_parties(
        session,
        user_id=current.id,
        document_id=document_id,
        organization_id=payload.organization_id if "organization_id" in given else UNSET,
        counterparty_id=payload.counterparty_id if "counterparty_id" in given else UNSET,
    )
    return DocumentSchema.model_validate(document)


@router.post(
    "/{document_id}/render",
    response_model=DocumentFileSchema,
    responses=_ERRORS | {409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    operation_id="render_document",
    summary="Собрать файл документа (DOCX или PDF)",
)
async def render(
    document_id: IdPath,
    payload: RenderRequest,
    current: CurrentUserDep,
    session: SessionDep,
    state: StateDep,
) -> DocumentFileSchema:
    file = await render_document(
        session,
        user_id=current.id,
        document_id=document_id,
        fmt=payload.format,
        cfg=state.files_config,
    )
    return DocumentFileSchema.model_validate(file)


@router.get(
    "/{document_id}/files",
    response_model=list[DocumentFileSchema],
    responses=_ERRORS,
    operation_id="list_document_files",
    summary="Собранные файлы документа",
)
async def get_files(
    document_id: IdPath, current: CurrentUserDep, session: SessionDep
) -> list[DocumentFileSchema]:
    files = await list_document_files(session, user_id=current.id, document_id=document_id)
    return [DocumentFileSchema.model_validate(f) for f in files]


@router.get(
    "/{document_id}/file",
    response_class=Response,
    responses={
        200: {"content": {"application/octet-stream": {}}, "description": "Файл документа"},
        **_ERRORS,
    },
    operation_id="download_document_file",
    summary="Скачать собранный файл",
)
async def download(
    document_id: IdPath,
    current: CurrentUserDep,
    session: SessionDep,
    state: StateDep,
    file_format: Literal["docx", "pdf"] = Query("docx", alias="format"),
) -> Response:
    file, data = await load_document_file(
        session,
        user_id=current.id,
        document_id=document_id,
        fmt=file_format,
        cfg=state.files_config,
    )
    # Имя файла кириллическое: ASCII-вариант для старых клиентов, filename* — настоящий.
    quoted = quote(file.filename)
    return Response(
        content=data,
        media_type=MEDIA_TYPES[file.format],
        headers={
            "Content-Disposition": f"attachment; filename=\"document.{file.format}\"; filename*=UTF-8''{quoted}"
        },
    )


@router.post(
    "/{document_id}/send",
    response_model=SendDocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERRORS | {409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    operation_id="send_document",
    summary="Отправить файл документа в чат MAX",
)
async def send(
    document_id: IdPath,
    payload: SendDocumentRequest,
    current: CurrentUserDep,
    session: SessionDep,
    state: StateDep,
    redis: RedisDep,
) -> SendDocumentResponse:
    # 202: ядро ставит событие в стрим, файл в чат кладёт бот.
    file, event_id = await send_document_to_chat(
        session,
        user_id=current.id,
        max_user_id=current.max_user_id,
        document_id=document_id,
        fmt=payload.format,
        cfg=state.files_config,
        bus=state.event_bus,
        tokens=DownloadTokenRepository(redis),
        text=payload.text,
    )
    return SendDocumentResponse(event_id=event_id, format=file.format, filename=file.filename)


@router.get(
    "/download/{token}",
    response_class=Response,
    responses={
        200: {"content": {"application/octet-stream": {}}, "description": "Файл документа"},
        404: {"model": ErrorResponse},
    },
    operation_id="download_by_token",
    summary="Скачать файл по одноразовому токену (забирает бот)",
)
async def download_by_token(
    token: str, session: SessionDep, state: StateDep, redis: RedisDep
) -> Response:
    filename, fmt, data = await load_file_by_token(
        session, token=token, cfg=state.files_config, tokens=DownloadTokenRepository(redis)
    )
    return Response(
        content=data,
        media_type=MEDIA_TYPES[fmt],
        headers={
            "Content-Disposition": f"attachment; filename=\"document.{fmt}\"; filename*=UTF-8''{quote(filename)}"
        },
    )


@router.delete(
    "/{document_id}",
    response_model=OkResponse,
    responses=_ERRORS,
    operation_id="delete_document",
    summary="Удалить документ",
)
async def delete(document_id: IdPath, current: CurrentUserDep, session: SessionDep) -> OkResponse:
    await delete_document(session, user_id=current.id, document_id=document_id)
    return OkResponse()


@router.post(
    "/{document_id}/confirm",
    response_model=DocumentSchema,
    responses=_ERRORS,
    operation_id="confirm_document_fields",
    summary="Подтвердить значения помощника или распознавания",
)
async def confirm(
    document_id: IdPath,
    payload: ConfirmFieldsRequest,
    current: CurrentUserDep,
    session: SessionDep,
) -> DocumentSchema:
    document = await confirm_fields(
        session, user_id=current.id, document_id=document_id, keys=payload.keys
    )
    return DocumentSchema.model_validate(document)
