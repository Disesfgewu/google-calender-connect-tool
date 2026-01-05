from __future__ import annotations

from test.test import CalendarTestCase


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
