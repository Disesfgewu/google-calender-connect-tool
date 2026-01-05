"""Minimal demo that authenticates via OAuth, lists events, and inserts a test event."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from calender.calender import calender

CREDENTIALS_FILE = "./calender/credentials.json"
TARGET_CALENDAR_ID = "test@gmail.com"
DEFAULT_TOKEN_LABEL = "test"


def build_client(token_label: str = DEFAULT_TOKEN_LABEL, calendar_id: str = TARGET_CALENDAR_ID) -> calender:
    """Return a Calendar client bound to a specific Google account/token."""

    return calender.from_oauth_credentials(
        credentials_file=CREDENTIALS_FILE,
        token_label=token_label,
        calendar_id=calendar_id,
    )


def main() -> None:
    client = build_client()
    print(f"Using calendar: {TARGET_CALENDAR_ID}")
    print(f"Using token label: {DEFAULT_TOKEN_LABEL}")

    upcoming = client.read(time_min=datetime.now(timezone.utc), max_results=5)
    print(f"Fetched {len(upcoming)} upcoming events")
    for idx, event in enumerate(upcoming, start=1):
        start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
        owner = (
            event.get("extendedProperties", {})
            .get("private", {})
            .get("owner")
        )
        owner_label = f"[{owner}] " if owner else ""
        print(f"  {idx:02d}. {start} | {owner_label}{event.get('summary', '(no title)')}")

    output_path = Path(__file__).with_name("upcoming_events.json")
    output_path.write_text(json.dumps(upcoming, indent=2, ensure_ascii=False))
    print(f"Saved full event payloads to {output_path}")

    taipei_tz = ZoneInfo("Asia/Taipei")
    event_start = datetime(2026, 1, 9, 12, 0, tzinfo=taipei_tz)
    event_end = datetime(2026, 1, 9, 13, 57, tzinfo=taipei_tz)
    created = client.write(
        "測試2",
        event_start,
        event_end,
        description="早安你好",
        location="新北市政府",
    )
    print("Created persistent event:")
    print(f"  ID: {created.get('id')}")
    print(f"  Link: {created.get('htmlLink')}")


if __name__ == "__main__":
    main()
