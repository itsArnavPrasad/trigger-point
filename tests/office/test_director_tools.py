"""The Director can only call tools its definition lists. Autopilot asks it to do connector work, so
every tool those asks name must be listed, or the live run silently cannot do them."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = "mcp__claude_ai_Google_Calendar__"


def director_tools() -> set[str]:
    text = (ROOT / ".claude/agents/mission-director.md").read_text()
    line = next(x for x in text.splitlines() if x.startswith("tools:"))
    return {t.strip() for t in line.removeprefix("tools:").split(",")}


def test_the_director_has_every_tool_autopilot_asks_it_to_use() -> None:
    needed = {
        "mcp__trigger_point__prepare_reply",
        "mcp__trigger_point__record_reply_sent",
        "mcp__trigger_point__get_booking",
        "mcp__trigger_point__record_booked_meeting",
        "mcp__trigger_point__record_busy_times",
        "mcp__claude_ai_Gmail__get_thread",
        "mcp__claude_ai_Gmail__send_message",
        "mcp__claude_ai_Google_Calendar__create_event",
        f"{CHECK}list_events",
        f"{CHECK}list_calendars",
    }
    assert needed <= director_tools(), sorted(needed - director_tools())


def test_every_autopilot_tool_the_driver_names_is_a_real_mcp_tool() -> None:
    import re

    driver = (ROOT / "src/trigger_point/office/autopilot_driver.py").read_text()
    named = set(
        re.findall(
            r"\b(prepare_reply|record_reply_sent|get_booking|record_busy_times|list_open_threads|sync_replies)\b",
            driver,
        )
    )
    tools = (ROOT / "src/trigger_point/workflow/mcp_tools.py").read_text()
    assert all(f"def {n}(" in tools for n in named), named
