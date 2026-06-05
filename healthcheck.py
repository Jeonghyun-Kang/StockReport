"""연동 진단 CLI.

사용:
    python -m healthcheck          # 가벼운 점검(설정/import/인덱스)
    python -m healthcheck --probe  # 실제 1회 호출까지(DART/네이버 무료, LLM은 토큰 소량 소모)
"""
from __future__ import annotations

import sys

from utils import ensure_root_on_path

ensure_root_on_path()
from diagnostics import run_all  # noqa: E402


def main() -> int:
    probe = "--probe" in sys.argv or "-p" in sys.argv
    mode = "실제 호출(probe)" if probe else "가벼운 점검"
    print(f"=== disclosure-advisor 연동 진단 [{mode}] ===\n")

    statuses = run_all(probe=probe)
    worst = "live"
    for s in statuses:
        print(f"{s.icon} {s.name:18s} | {s.detail}")
        if s.level == "error":
            worst = "error"
        elif s.level == "fallback" and worst != "error":
            worst = "fallback"

    print()
    if worst == "live":
        print("✅ 모든 연동 정상.")
        return 0
    if worst == "fallback":
        print("🟡 일부는 폴백(대체)으로 동작합니다. 위 안내를 참고해 키/패키지를 보완하세요.")
        return 0
    print("🔴 오류가 있는 연동이 있습니다. 위 메시지를 확인하세요.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
