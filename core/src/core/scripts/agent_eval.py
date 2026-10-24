"""Прогнать набор проверочных примеров помощника на настоящей модели.

    cd core && uv run python -m core.scripts.agent_eval

Нужен ``GIGACHAT_AUTH_KEY`` в окружении. Запросы идут по одному и занимают
поток тарифа: на стенде, где работает живой бот, его пользователи на это
время ждут — запускать на своём ключе или когда бот свободен. Код выхода 1,
если хоть один пример не прошёл.
"""

from __future__ import annotations

import asyncio
import sys

from core.llm import GigaChatConfig, build_llm_client
from core.usecases.agent.evaluation import run_cases


async def main() -> int:
    llm = build_llm_client(GigaChatConfig.from_env())
    if llm is None:
        print("GIGACHAT_AUTH_KEY не задан — проверять не на чем", file=sys.stderr)
        return 2
    try:
        results = await run_cases(llm)
    finally:
        await llm.aclose()
    for result in results:
        mark = "ok  " if result.passed else "FAIL"
        print(f"{mark} [{result.group}] {result.name}")
        for problem in result.problems:
            print(f"       {problem}")
    passed = sum(result.passed for result in results)
    print(f"\n{passed} из {len(results)} примеров прошли")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
