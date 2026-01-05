"""Lightweight Google Calendar helper."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


class CalendarError(RuntimeError):
    """Raised when a calendar operation cannot be completed."""


class calender:
    """Utility wrapper around the Google Calendar API with local caching."""

    DEFAULT_SCOPES = ("https://www.googleapis.com/auth/calendar",)

    def __init__(self, service: Optional[Any] = None, calendar_id: str = "primary") -> None:
        self._service = service
        self.calendar_id = calendar_id
        self._local_events: Dict[str, Dict[str, Any]] = {}
        self._id_counter = 0
        self._owner_email: Optional[str] = None

    @classmethod
    def from_service_account_file(
        cls,
        credentials_file: str,
        calendar_id: str = "primary",
        scopes: Optional[Sequence[str]] = None,
    ) -> "calender":
        """Factory that wires the Google API client using a service-account JSON file."""

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as exc:  # pragma: no cover - import guard
            raise CalendarError(
                "Install google-api-python-client and google-auth to talk to Google Calendar",
            ) from exc

        scopes = tuple(scopes) if scopes else cls.DEFAULT_SCOPES
        credentials = service_account.Credentials.from_service_account_file(
            credentials_file,
            scopes=scopes,
        )
        service = build("calendar", "v3", credentials=credentials)
        return cls(service=service, calendar_id=calendar_id)

    def attach_service(self, service: Any) -> None:
        """Attach or swap the underlying googleapiclient service."""

        if service is None:
            raise CalendarError("service cannot be None")
        self._service = service

    @classmethod
    def from_oauth_credentials(
        cls,
        credentials_file: str,
        token_file: Optional[str] = None,
        token_label: Optional[str] = None,
        calendar_id: str = "primary",
        scopes: Optional[Sequence[str]] = None,
        verify_calendar: bool = True,
    ) -> "calender":
        """Instantiate the helper by running the OAuth installed-app flow."""

        try:
            from googleapiclient.discovery import build
        except ImportError as exc:  # pragma: no cover - import guard
            raise CalendarError("Install google-api-python-client to use OAuth flow") from exc

        token_path = cls._resolve_token_path(credentials_file, token_file, token_label)
        creds = cls._load_oauth_credentials(credentials_file, token_path, scopes)
        service = build("calendar", "v3", credentials=creds)
        if verify_calendar:
            cls._verify_calendar_access(service, calendar_id)
        instance = cls(service=service, calendar_id=calendar_id)
        instance._owner_email = cls._resolve_user_email(service)
        return instance

    @property
    def owner_email(self) -> Optional[str]:
        return self._owner_email

    def read(
        self,
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 250,
        use_cache: bool = False,
    ) -> List[Dict[str, Any]]:
        """Fetch reservations from Google Calendar or the local cache."""

        if self._service and not use_cache:
            params = {
                "maxResults": max_results,
                "singleEvents": True,
                "orderBy": "startTime",
            }
            if time_min:
                params["timeMin"] = self._to_iso8601(time_min)
            if time_max:
                params["timeMax"] = self._to_iso8601(time_max)

            try:
                events_result = self.list_events(**params)
            except Exception as exc:
                raise CalendarError("Could not read events from Google Calendar") from exc

            events = events_result.get("items", [])
            for event in events:
                event_id = event.get("id")
                if event_id:
                    self._local_events[event_id] = event
            return events

        return self._filter_local_events(time_min, time_max, max_results)

    def write(
        self,
        summary: str,
        start: datetime,
        end: datetime,
        description: Optional[str] = None,
        owner_email: Optional[str] = None,
        use_cache_only: bool = False,
        **additional_fields: Any,
    ) -> Dict[str, Any]:
        """Create a new reservation."""

        event_body: Dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": self._to_iso8601(start)},
            "end": {"dateTime": self._to_iso8601(end)},
        }
        if description is not None:
            event_body["description"] = description
        event_body.update(additional_fields)

        if owner_email is None:
            owner_email = self._owner_email
        if owner_email:
            extended_props = event_body.setdefault("extendedProperties", {})
            private_props = extended_props.setdefault("private", {})
            private_props.setdefault("owner", owner_email)

        if self._service and not use_cache_only:
            try:
                created = self.insert_event(event_body)
            except Exception as exc:
                raise CalendarError("Could not create the event in Google Calendar") from exc
        else:
            created = self._store_locally(event_body)

        event_id = created.get("id")
        if event_id:
            self._local_events[event_id] = created
        return created

    def modify(self, event_id: str, use_cache_only: bool = False, **changes: Any) -> Dict[str, Any]:
        """Update an existing reservation."""

        if not event_id:
            raise CalendarError("event_id is required to modify an event")

        if self._service and not use_cache_only:
            try:
                updated = self.patch_event(event_id, changes)
            except Exception as exc:
                raise CalendarError(f"Could not modify event {event_id}") from exc
        else:
            updated = self._apply_local_changes(event_id, changes)

        self._local_events[event_id] = updated
        return updated

    def delete(self, event_id: str, use_cache_only: bool = False) -> None:
        """Remove a reservation from Google Calendar or the cache."""

        if not event_id:
            raise CalendarError("event_id is required to delete an event")

        if self._service and not use_cache_only:
            try:
                self.delete_event(event_id)
            except Exception as exc:
                raise CalendarError(f"Could not delete event {event_id}") from exc

        self._local_events.pop(event_id, None)

    # --- Events resource wrappers (align with Google Calendar REST methods) ---

    def list_events(self, **query_parameters: Any) -> Dict[str, Any]:
        """Mirror of events.list."""

        params = {"calendarId": self.calendar_id, **query_parameters}
        return self._execute_events_call("list", **params)

    def get_event(self, event_id: str, **query_parameters: Any) -> Dict[str, Any]:
        """Mirror of events.get."""

        params = {"calendarId": self.calendar_id, "eventId": event_id, **query_parameters}
        return self._execute_events_call("get", **params)

    def insert_event(self, body: Dict[str, Any], **query_parameters: Any) -> Dict[str, Any]:
        """Mirror of events.insert."""

        params = {"calendarId": self.calendar_id, "body": body, **query_parameters}
        return self._execute_events_call("insert", **params)

    def update_event(self, event_id: str, body: Dict[str, Any], **query_parameters: Any) -> Dict[str, Any]:
        """Mirror of events.update."""

        params = {"calendarId": self.calendar_id, "eventId": event_id, "body": body, **query_parameters}
        return self._execute_events_call("update", **params)

    def patch_event(self, event_id: str, body: Dict[str, Any], **query_parameters: Any) -> Dict[str, Any]:
        """Mirror of events.patch."""

        params = {"calendarId": self.calendar_id, "eventId": event_id, "body": body, **query_parameters}
        return self._execute_events_call("patch", **params)

    def delete_event(self, event_id: str, **query_parameters: Any) -> None:
        """Mirror of events.delete."""

        params = {"calendarId": self.calendar_id, "eventId": event_id, **query_parameters}
        self._execute_events_call("delete", **params)

    def import_event(self, body: Dict[str, Any], **query_parameters: Any) -> Dict[str, Any]:
        """Mirror of events.import."""

        params = {"calendarId": self.calendar_id, "body": body, **query_parameters}
        return self._execute_events_call("import_", **params)

    def move_event(
        self,
        event_id: str,
        destination_calendar_id: str,
        **query_parameters: Any,
    ) -> Dict[str, Any]:
        """Mirror of events.move."""

        params = {
            "calendarId": self.calendar_id,
            "eventId": event_id,
            "destination": destination_calendar_id,
            **query_parameters,
        }
        return self._execute_events_call("move", **params)

    def quick_add_event(self, text: str, **query_parameters: Any) -> Dict[str, Any]:
        """Mirror of events.quickAdd."""

        params = {"calendarId": self.calendar_id, "text": text, **query_parameters}
        return self._execute_events_call("quickAdd", **params)

    def list_event_instances(self, event_id: str, **query_parameters: Any) -> Dict[str, Any]:
        """Mirror of events.instances."""

        params = {"calendarId": self.calendar_id, "eventId": event_id, **query_parameters}
        return self._execute_events_call("instances", **params)

    def watch_events(self, body: Dict[str, Any], **query_parameters: Any) -> Dict[str, Any]:
        """Mirror of events.watch."""

        params = {"calendarId": self.calendar_id, "body": body, **query_parameters}
        return self._execute_events_call("watch", **params)

    def _ensure_events_api(self) -> Any:
        if not self._service:
            raise CalendarError("Google Calendar service is not configured")
        events_api = getattr(self._service, "events", None)
        if callable(events_api):
            return events_api()
        raise CalendarError("Provided service does not expose events()")

    @staticmethod
    def _load_oauth_credentials(
        credentials_file: str,
        token_path: Path,
        scopes: Optional[Sequence[str]] = None,
    ):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials as OAuthCredentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:  # pragma: no cover - import guard
            raise CalendarError(
                "Install google-auth, google-auth-oauthlib, and google-api-python-client",
            ) from exc

        scopes = tuple(scopes) if scopes else calender.DEFAULT_SCOPES
        creds = None
        if token_path.exists():
            creds = OAuthCredentials.from_authorized_user_file(str(token_path), scopes)
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, scopes)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())
        return creds

    @staticmethod
    def _resolve_token_path(
        credentials_file: str,
        token_file: Optional[str],
        token_label: Optional[str],
    ) -> Path:
        if token_file:
            return Path(token_file).expanduser()
        base_dir = Path(credentials_file).resolve().parent
        label = token_label or "default"
        safe_label = "".join(ch if ch.isalnum() else "-" for ch in label) or "default"
        return base_dir / f"token-{safe_label}.json"

    @staticmethod
    def _resolve_user_email(service: Any) -> Optional[str]:
        try:
            profile = service.calendarList().get(calendarId="primary").execute()
            return profile.get("id")
        except Exception:
            return None

    @staticmethod
    def _verify_calendar_access(service: Any, calendar_id: str) -> None:
        try:
            service.calendars().get(calendarId=calendar_id).execute()
        except Exception as exc:
            message = (
                f"Cannot access calendar '{calendar_id}'. "
                "Share that calendar with this Google account (grant 'Make changes to events')."
            )
            raise CalendarError(message) from exc

    def _execute_events_call(self, method_name: str, **params: Any) -> Any:
        events_api = self._ensure_events_api()
        method = getattr(events_api, method_name, None)
        if method is None:
            raise CalendarError(f"events().{method_name} is not available in this service")
        return method(**params).execute()

    def _store_locally(self, event_body: Dict[str, Any]) -> Dict[str, Any]:
        self._id_counter += 1
        local_id = event_body.get("id", f"local-{self._id_counter}")
        stored_event = {**event_body, "id": local_id}
        self._local_events[local_id] = stored_event
        return stored_event

    def _apply_local_changes(self, event_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        if event_id not in self._local_events:
            raise CalendarError(f"Event {event_id} is not cached locally")
        self._local_events[event_id].update(changes)
        return self._local_events[event_id]

    def _filter_local_events(
        self,
        time_min: Optional[datetime],
        time_max: Optional[datetime],
        max_results: int,
    ) -> List[Dict[str, Any]]:
        filtered = list(self._local_events.values())
        if time_min:
            filtered = [
                event
                for event in filtered
                if self._event_starts_after(event, time_min)
            ]
        if time_max:
            filtered = [
                event
                for event in filtered
                if self._event_starts_before(event, time_max)
            ]
        return filtered[:max_results]

    def _event_starts_after(self, event: Dict[str, Any], threshold: datetime) -> bool:
        start = self._extract_start(event)
        normalized_threshold = self._normalize_datetime(threshold)
        return start >= normalized_threshold

    def _event_starts_before(self, event: Dict[str, Any], threshold: datetime) -> bool:
        start = self._extract_start(event)
        normalized_threshold = self._normalize_datetime(threshold)
        return start <= normalized_threshold

    def _extract_start(self, event: Dict[str, Any]) -> datetime:
        start = event.get("start", {}).get("dateTime")
        if isinstance(start, datetime):
            return self._normalize_datetime(start)
        if isinstance(start, str):
            try:
                normalized_str = start.replace("Z", "+00:00")
                parsed = datetime.fromisoformat(normalized_str)
                return self._normalize_datetime(parsed)
            except ValueError as exc:
                raise CalendarError("Event start time is not ISO-8601 compliant") from exc
        raise CalendarError("Event start time is missing")

    def _to_iso8601(self, value: datetime) -> str:
        normalized = self._normalize_datetime(value)
        return normalized.isoformat()

    def _normalize_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
