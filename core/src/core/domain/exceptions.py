"""Ошибки прикладного уровня с безопасным для пользователя текстом.

Сценарии бросают их вместо HTTPException: сценарий не знает, что его вызывает
HTTP. Маппинг на статус и формат ответа делает core.api.error_handlers.
"""

from __future__ import annotations


class AppError(Exception):
    """Базовая ошибка домена.

    ``code`` — машинный код для клиента и логов (``auth.init_data_invalid``),
    ``public_message`` — текст, который можно показать человеку. Всё, что
    нельзя показывать (стек, внутренности), остаётся в ``log_message``.
    """

    status_code = 400
    code = "app.error"

    def __init__(
        self,
        public_message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        log_message: str | None = None,
    ) -> None:
        super().__init__(public_message)
        self.public_message = public_message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.log_message = log_message


class UnauthorizedError(AppError):
    status_code = 401
    code = "auth.unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "auth.forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationError(AppError):
    status_code = 422
    code = "validation"
