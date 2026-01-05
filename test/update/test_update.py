from __future__ import annotations

from test.test import CalendarTestCase


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
