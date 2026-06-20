"""Crucible provider smoke test (Groq-only). Run from backend/:  python smoke_test.py"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from app.integrations.llm import ask  # noqa: E402


def main() -> None:
    print("Crucible Groq smoke test\n" + "-" * 32)
    checks = [
        ("victim   (llama-3.3-70b)", "victim", "Reply with exactly: VICTIM OK"),
        ("reporter (qwen3.6-27b)", "reporter", "Reply with exactly: REPORTER OK"),
        ("judge    (gpt-oss-120b)", "judge", "Reply with exactly: JUDGE OK"),
    ]
    all_passed = True
    for label, role, prompt in checks:
        try:
            out = ask(role, prompt, temperature=0)
            print(f"[pass] {label}: {out!r}")
        except Exception as exc:  # noqa: BLE001
            all_passed = False
            print(f"[FAIL] {label}: {type(exc).__name__}: {exc}")
    print("-" * 32)
    print("All Groq models reachable." if all_passed
          else "One or more models failed - check GROQ_API_KEY / model ids in .env.")


if __name__ == "__main__":
    main()
