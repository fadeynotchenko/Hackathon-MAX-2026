"""Слой сценариев (use-case-ов): auth, users.

Функции принимают AsyncSession и конфиг явно, результат — frozen dataclass,
ошибки — core.domain.exceptions.AppError. Не знают о транспорте (HTTP, CLI).
"""
