from __future__ import annotations

from calender.calender import CalendarError
from test.test import CalendarTestCase


class TestCalendarDelete(CalendarTestCase):
	def test_delete_removes_event(self) -> None:
		event = self.create_event(summary="Delete Test")
		event_id = event["id"]

		self.delete_event(event_id)

		with self.assertRaises(CalendarError):
			self.client.get_event(event_id)
