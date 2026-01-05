"""Integration test runner for google-calender-connect-tool."""

from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from calender.calender import CalendarError, calender


class CalendarTestCase(unittest.TestCase):
    """Base class that provisions a calendar client for real API tests."""

    CREDENTIALS_FILE = "./calender/credentials.json"
    CALENDAR_ID = "test@gmail.com"
    TOKEN_LABEL = "integration-tests"
    DEFAULT_OFFSET_MINUTES = 5
    DEFAULT_DURATION_MINUTES = 30

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.client = calender.from_oauth_credentials(
            credentials_file=cls.CREDENTIALS_FILE,
            token_label=cls.TOKEN_LABEL,
            calendar_id=cls.CALENDAR_ID,
        )

    def setUp(self) -> None:
        super().setUp()
        self._created_event_ids: list[str] = []

    def tearDown(self) -> None:
        for event_id in self._created_event_ids:
            try:
                self.client.delete(event_id)
            except CalendarError:
                pass
        self._created_event_ids.clear()
        super().tearDown()

    def make_time_window(
        self,
        offset_minutes: Optional[int] = None,
        duration_minutes: Optional[int] = None,
    ) -> tuple[datetime, datetime]:
        offset = offset_minutes or self.DEFAULT_OFFSET_MINUTES
        duration = duration_minutes or self.DEFAULT_DURATION_MINUTES
        start = datetime.now(timezone.utc) + timedelta(minutes=offset)
        end = start + timedelta(minutes=duration)
        return start, end

    def create_event(
        self,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        **extra_fields,
    ) -> dict:
        event_summary = summary or f"Test Event {uuid.uuid4().hex[:8]}"
        event_start = start
        event_end = end
        if event_start is None or event_end is None:
            event_start, event_end = self.make_time_window()

        event = self.client.write(
            event_summary,
            event_start,
            event_end,
            description=description,
            **extra_fields,
        )
        event_id = event.get("id")
        if event_id:
            self._created_event_ids.append(event_id)
        return event

    def delete_event(self, event_id: str) -> None:
        """Delete and deregister an event created during a test."""

        self.client.delete(event_id)
        if event_id in self._created_event_ids:
            self._created_event_ids.remove(event_id)


class TestCalendarRead(CalendarTestCase):
    def test_read_returns_recently_created_event(self) -> None:
        start, end = self.make_time_window()
        event = self.create_event(start=start, end=end)

        window_start = start - timedelta(minutes=1)
        window_end = end + timedelta(minutes=1)
        events = self.client.read(time_min=window_start, time_max=window_end, max_results=10)

        self.assertTrue(
            any(item.get("id") == event.get("id") for item in events),
            "Created event should be returned by read() within the specified window",
        )


class TestCalendarWrite(CalendarTestCase):
    def test_write_creates_event_with_owner_metadata(self) -> None:
        summary = "Integration Write Test"
        event = self.create_event(summary=summary, description="Write test", location="Test Location")

        self.assertEqual(event["summary"], summary)
        self.assertIn("start", event)
        self.assertIn("end", event)

        owner = (
            event.get("extendedProperties", {})
            .get("private", {})
            .get("owner")
        )
        if self.client.owner_email:
            self.assertEqual(owner, self.client.owner_email)
        else:
            self.assertIsNotNone(owner)


class TestCalendarUpdate(CalendarTestCase):
    def test_modify_updates_summary_and_description(self) -> None:
        original = self.create_event(summary="Update Test", description="before")

        updated = self.client.modify(
            original["id"],
            summary="Update Test (edited)",
            description="after",
        )

        self.assertEqual(updated["summary"], "Update Test (edited)")
        self.assertEqual(updated["description"], "after")


class TestCalendarDelete(CalendarTestCase):
    def test_delete_removes_event(self) -> None:
        start, end = self.make_time_window()
        event = self.create_event(summary="Delete Test", start=start, end=end)
        event_id = event["id"]

        self.delete_event(event_id)

        window_start = start - timedelta(minutes=1)
        window_end = end + timedelta(minutes=1)
        events = self.client.read(time_min=window_start, time_max=window_end, max_results=10)

        self.assertFalse(
            any(item.get("id") == event_id for item in events),
            "Deleted event should not appear in subsequent read() calls",
        )


if __name__ == "__main__":
    unittest.main()
