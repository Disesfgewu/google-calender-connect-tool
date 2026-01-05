from __future__ import annotations

from datetime import timedelta

from test.test import CalendarTestCase


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
