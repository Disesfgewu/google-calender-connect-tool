"""Simple multi-account probe for Google Calendar + Tasks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import sys

from google.auth.exceptions import RefreshError

GOOGLE_CALENDAR_ROOT = Path(__file__).resolve().parent / "google-calendar"
if str(GOOGLE_CALENDAR_ROOT) not in sys.path:
	sys.path.insert(0, str(GOOGLE_CALENDAR_ROOT))

from calender.calender import CalendarError, calender


DEFAULT_SCOPES = ("https://www.googleapis.com/auth/calendar.readonly",)


@dataclass(frozen=True)
class AccountBinding:
	"""Describes how to reach a single Google account."""

	name: str
	credentials_file: str
	calendar_id: str = "primary"
	token_label: str = "default"
	token_file: Optional[str] = None
	scopes: Sequence[str] = DEFAULT_SCOPES


class CalendarAccountSession:
	"""Holds the authorized services for one Google account."""

	def __init__(self, binding: AccountBinding) -> None:
		self.binding = binding
		self._credentials = self._authorize()
		self.calendar_client = calender(
			service=self._build_calendar_service(),
			calendar_id=binding.calendar_id,
		)

	def fetch_events(self, days_ahead: int = 7, max_results: int = 50) -> List[Dict]:
		"""Return upcoming calendar events for this account."""

		time_min = datetime.now(timezone.utc)
		time_max = time_min + timedelta(days=days_ahead)
		return self.calendar_client.read(
			time_min=time_min,
			time_max=time_max,
			max_results=max_results,
		)

	def _authorize(self):
		token_path = calender._resolve_token_path(
			self.binding.credentials_file,
			self.binding.token_file,
			self.binding.token_label,
		)
		scopes = tuple(self.binding.scopes) if self.binding.scopes else calender.DEFAULT_SCOPES
		try:
			return calender._load_oauth_credentials(
				self.binding.credentials_file,
				token_path,
				scopes,
			)
		except RefreshError as exc:
			message = str(exc).lower()
			if "invalid_grant" in message or "bad request" in message:
				try:
					token_path.unlink()
				except FileNotFoundError:
					pass
				return calender._load_oauth_credentials(
					self.binding.credentials_file,
					token_path,
					scopes,
				)
			raise

	def _build_calendar_service(self):
		try:
			from googleapiclient.discovery import build
		except ImportError as exc:  # pragma: no cover - import guard
			raise CalendarError("Install google-api-python-client to call Calendar") from exc

		service = build("calendar", "v3", credentials=self._credentials)
		calender._verify_calendar_access(service, self.binding.calendar_id)
		return service


class MultiAccountCalendarProbe:
	"""Utility that fetches upcoming events for every configured account."""

	def __init__(self, bindings: Sequence[AccountBinding]):
		if not bindings:
			raise ValueError("Provide at least one account binding (n > 0)")
		self.sessions = [CalendarAccountSession(binding) for binding in bindings]

	def snapshot(
		self,
		event_limit: int = 25,
		days_ahead: int = 7,
	) -> Dict[str, Dict]:
		"""Collect a dictionary keyed by account name with events payloads."""

		summary: Dict[str, Dict] = {}
		for session in self.sessions:
			events = session.fetch_events(days_ahead=days_ahead, max_results=event_limit)
			summary[session.binding.name] = {
				"calendarId": session.binding.calendar_id,
				"ownerEmail": session.calendar_client.owner_email,
				"events": events,
			}
		return summary

	def print_report(self) -> None:
		"""Pretty-print a snapshot so you can eyeball the response quickly."""

		snapshot = self.snapshot()
		for name, payload in snapshot.items():
			print(f"=== Account: {name} ({payload['calendarId']}) ===")
			print(f"Owner: {payload['ownerEmail'] or 'Unknown'}")
			print("-- Events --")
			for event in payload["events"]:
				event_summary = event.get("summary", "<no title>")
				start = event.get("start", {}).get("dateTime")
				end = event.get("end", {}).get("dateTime")
				print(f"  * {event_summary} :: {start} -> {end}")
			if not payload["events"]:
				print("  (no upcoming events)")
			print()


def _example_bindings() -> List[AccountBinding]:
	"""Replace placeholder calendar IDs with the ones you control."""

	credentials = "./calender/credentials.json"
	return [
		AccountBinding(
			name="primary",  # replace with a descriptive label
			credentials_file=credentials,
			calendar_id="primary",
			token_label="default",
		),
		# Add more accounts here (n can be any positive integer)
		# AccountBinding(
		#     name="teammate",
		#     credentials_file=credentials,
		#     calendar_id="someone@example.com",
		#     token_label="token-2",
		# ),
	]


if __name__ == "__main__":
	probe = MultiAccountCalendarProbe(_example_bindings())
	probe.print_report()
