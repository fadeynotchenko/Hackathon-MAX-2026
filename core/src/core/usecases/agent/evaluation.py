"""Набор проверочных примеров помощника: сообщение → ожидаемые поля.

Примеры гоняют те же запросы к модели, что и сценарии (``fill_messages``,
``route_request``, ``suggest_places``), и ту же проверку опоры на слова
человека, но без базы: шаблоны берутся встроенные. Так правка промпта или
смена модели меряется числом прошедших примеров, а не впечатлением от двух
сообщений в чате. Запуск с настоящей моделью — ``core.scripts.agent_eval``.

Пример проверяет только то, что в нём названо: ``expect`` — поле и значение
(сверяются после нормализации), ``items`` — начала названий позиций счёта,
``absent`` — поля, которых в сообщении нет и которые модель не должна додумать.
У маршрута ``current`` — текущий документ, как его видит модель в чате.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from core.domain.documents import normalize, parse_items
from core.llm import LLMClient, LLMError
from core.usecases.agent.chat import route_request
from core.usecases.agent.prompts import fields_schema
from core.usecases.agent.service import fill_messages, propose
from core.usecases.agent.template_import import suggest_places, suggested_fields
from core.usecases.documents.builtin import BUILTIN_TEMPLATES, BuiltinTemplate

CASES_FILE = "eval_cases.json"


@dataclass(frozen=True)
class CaseResult:
    group: str
    name: str
    problems: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.problems


def load_cases() -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = json.loads(
        files(__package__).joinpath(CASES_FILE).read_text(encoding="utf-8")
    )
    return data


def template_by_slug(slug: str) -> BuiltinTemplate:
    return next(t for t in BUILTIN_TEMPLATES if t.slug == slug)


async def _fill_case(llm: LLMClient, case: Mapping[str, Any]) -> tuple[str, ...]:
    template = template_by_slug(case["template"])
    fields = template.fields
    specs = {spec.key: spec for spec in fields}
    missing = tuple(spec.key for spec in fields if spec.required)
    message = case["message"]
    raw = await llm.complete_json(
        fill_messages(template.title, fields, {}, missing, message),
        schema=fields_schema(fields),
    )
    got = propose(raw, fields, {}, message).values
    problems: list[str] = []
    for key, expected in case.get("expect", {}).items():
        value = got.get(key)
        want = normalize(specs[key], expected)[0]
        have = normalize(specs[key], value.value)[0] if value is not None else None
        if have != want:
            problems.append(f"{key}: ждали «{want}», получили «{have or '—'}»")
    names = case.get("items")
    if names:
        listed = got.get("items")
        items, _ = parse_items(listed.value) if listed is not None else ([], None)
        lowered = [item.name.lower().replace("ё", "е") for item in items]
        for start in names:
            if not any(start in name for name in lowered):
                problems.append(f"items: нет позиции «{start}…»")
    problems += [
        f"{key}: додумано «{got[key].value}»" for key in case.get("absent", ()) if key in got
    ]
    return tuple(problems)


async def _route_case(llm: LLMClient, case: Mapping[str, Any]) -> tuple[str, ...]:
    catalog = [(t.slug, t.title, t.description) for t in BUILTIN_TEMPLATES]
    messages, schema = route_request(case["message"], case.get("current", "нет"), catalog)
    raw = await llm.complete_json(messages, schema=schema)
    intent, template = str(raw.get("intent", "")), str(raw.get("template", ""))
    # Без текущего документа сценарий понимает «вопрос» и «дополнить» как новый
    # документ, поэтому пример может разрешать несколько намерений.
    allowed = case["intent"] if isinstance(case["intent"], list) else [case["intent"]]
    # Вид документа сценарий читает только у нового документа.
    if intent in allowed and (intent != "new" or template == case["template"]):
        return ()
    return (f"ждали {'/'.join(allowed)} {case['template']!r}, получили {intent} {template!r}",)


async def _template_case(llm: LLMClient, case: Mapping[str, Any]) -> tuple[str, ...]:
    lines: Sequence[str] = case["lines"]
    suggestion = await suggest_places(llm, lines)
    found = {
        place.text
        for field in suggested_fields({"places": suggestion.places}, lines)
        for place in field.places
    }
    return tuple(f"не нашлось места «{text}»" for text in case["expect"] if text not in found)


_RUNNERS = {"fill": _fill_case, "route": _route_case, "template": _template_case}


async def run_cases(
    llm: LLMClient, cases: Mapping[str, Sequence[Mapping[str, Any]]] | None = None
) -> list[CaseResult]:
    """Прогнать примеры по очереди: на тарифе модели — один запрос за раз."""
    results: list[CaseResult] = []
    for group, items in (cases or load_cases()).items():
        for case in items:
            try:
                problems = await _RUNNERS[group](llm, case)
            except LLMError as exc:
                problems = (f"модель не ответила: {exc}",)
            results.append(CaseResult(group, case["name"], problems))
    return results


def case_fields(case: Mapping[str, Any]) -> set[str]:
    """Поля, которые пример называет: проверка, что они есть в шаблоне."""
    return {
        *case.get("expect", {}),
        *case.get("absent", ()),
        *(("items",) if case.get("items") else ()),
    }
