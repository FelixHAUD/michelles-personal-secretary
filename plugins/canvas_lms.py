"""Canvas LMS DataSource plugin — fetches assignment deadlines."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from secretary.plugin import ConfigRequirement, DataSource


class CanvasLMSSource(DataSource):
    name = "canvas"
    description = "Fetches assignment deadlines from Canvas LMS"
    config_schema = [
        ConfigRequirement(
            key="CANVAS_API_TOKEN",
            description="Canvas LMS API access token",
            secret=True,
        ),
        ConfigRequirement(
            key="CANVAS_BASE_URL",
            description="Canvas instance URL (e.g. https://canvas.university.edu)",
        ),
    ]

    def initialize(self, config: dict[str, Any]) -> None:
        self._token = config["CANVAS_API_TOKEN"]
        self._base_url = config["CANVAS_BASE_URL"].rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self._token}",
        })

    def fetch_events(self, start: datetime, end: datetime) -> list[dict]:
        """Fetch upcoming assignments from all active courses."""
        events = []

        courses = self._get_courses()

        for course in courses:
            try:
                assignments = self._get_assignments(course["id"], start, end)
                for assignment in assignments:
                    event = self._normalize_assignment(assignment, course)
                    if event:
                        events.append(event)
            except Exception:
                continue  # Error isolation per course

        return events

    def _get_courses(self) -> list[dict]:
        """Get all active courses for the current user."""
        url = f"{self._base_url}/api/v1/courses"
        params = {"enrollment_state": "active", "per_page": 50}
        resp = self._session.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def _get_assignments(
        self, course_id: int, start: datetime, end: datetime
    ) -> list[dict]:
        """Get assignments with due dates in the given window."""
        url = f"{self._base_url}/api/v1/courses/{course_id}/assignments"
        params = {
            "per_page": 50,
            "order_by": "due_at",
            "bucket": "upcoming",
        }
        resp = self._session.get(url, params=params)
        resp.raise_for_status()

        assignments = []
        for a in resp.json():
            due_at = a.get("due_at")
            if not due_at:
                continue
            due = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
            if start <= due <= end:
                assignments.append(a)
        return assignments

    def _normalize_assignment(self, assignment: dict, course: dict) -> dict | None:
        """Convert a Canvas assignment into a normalized event dict."""
        due_at = assignment.get("due_at")
        if not due_at:
            return None

        due = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
        course_name = course.get("name", "Unknown Course")

        return {
            "event_id": f"canvas_{assignment['id']}",
            "title": f"[{course_name}] {assignment['name']}",
            "start": due.isoformat(),
            "end": due.isoformat(),  # Deadlines are a single point in time
            "location": "",
            "description": (
                f"Canvas assignment deadline. Course: {course_name}. "
                f"Points: {assignment.get('points_possible', 'N/A')}"
            ),
            "source": "canvas",
        }
