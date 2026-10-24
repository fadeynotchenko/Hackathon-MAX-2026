"""Набор проверочных примеров помощника: примеры ссылаются на настоящие шаблоны
и поля, а прогон честно отличает верный ответ модели от неверного."""

from __future__ import annotations

from typing import Any

from core.usecases.agent.evaluation import case_fields, load_cases, run_cases, template_by_slug
from core.usecases.documents.builtin import BUILTIN_TEMPLATES
from tests.fakes import FakeLLM


def _perfect_replies(cases: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Ответы модели, которая отвечает ровно то, что ждут примеры."""
    replies: list[dict[str, Any]] = []
    for case in cases["fill"]:
        reply: dict[str, Any] = dict(case.get("expect", {}))
        if case.get("items"):
            reply["items"] = [
                {"name": f"{start} работ", "quantity": "1", "unit": "", "price": "100"}
                for start in case["items"]
            ]
        replies.append(reply)
    replies += [
        {
            "intent": c["intent"][0] if isinstance(c["intent"], list) else c["intent"],
            "template": c["template"],
        }
        for c in cases["route"]
    ]
    for case in cases["template"]:
        places = [
            {"text": text, "before": "", "label": f"Поле {n}", "type": "text", "key": ""}
            for n, text in enumerate(case["expect"])
        ]
        replies.append({"title": "", "kind": "", "places": places})
    return replies


def test_cases_name_real_templates_and_fields() -> None:
    cases = load_cases()
    assert set(cases) == {"fill", "route", "template"}
    for case in cases["fill"]:
        keys = {spec.key for spec in template_by_slug(case["template"]).fields}
        assert case_fields(case) <= keys, case["name"]
    slugs = {t.slug for t in BUILTIN_TEMPLATES} | {""}
    assert all(case["template"] in slugs for case in cases["route"])
    for case in cases["template"]:
        assert all(any(text in line for line in case["lines"]) for text in case["expect"])


async def test_perfect_model_passes_every_case() -> None:
    cases = load_cases()
    results = await run_cases(FakeLLM(json_replies=_perfect_replies(cases)), cases)
    assert [r.name for r in results if not r.passed] == []
    assert len(results) == sum(len(group) for group in cases.values())


async def test_wrong_answers_are_reported() -> None:
    cases = {
        "fill": [
            {
                "name": "сумма",
                "template": "offer",
                "message": "КП для ООО Альфа на 450 тысяч, Москва",
                "expect": {"total": "450000"},
                "absent": ["client_name"],
            }
        ],
        "route": [{"name": "счёт", "message": "счёт", "intent": "new", "template": "invoice"}],
    }
    llm = FakeLLM(
        json_replies=[
            {"total": "45000", "client_name": "ООО Альфа"},
            {"intent": "fill", "template": ""},
        ]
    )
    fill, route = await run_cases(llm, cases)
    assert fill.problems == (
        "total: ждали «450000.00», получили «45000.00»",
        "client_name: додумано «ООО Альфа»",
    )
    assert route.problems == ("ждали new 'invoice', получили fill ''",)
