"""Tests for the Canvas LMS DataSource plugin."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from secretary.plugin import PluginRegistry

from plugins.canvas_lms import CanvasLMSSource


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CANVAS_CONFIG = {
    "CANVAS_API_TOKEN": "test-token-123",
    "CANVAS_BASE_URL": "https://canvas.university.edu",
}

SAMPLE_COURSE = {"id": 101, "name": "CS 101"}
SAMPLE_COURSE_2 = {"id": 202, "name": "MATH 201"}

SAMPLE_ASSIGNMENT = {
    "id": 5001,
    "name": "Homework 3",
    "due_at": "2026-04-20T23:59:00Z",
    "points_possible": 100,
}

SAMPLE_ASSIGNMENT_NO_DUE = {
    "id": 5002,
    "name": "Extra Credit",
    "due_at": None,
    "points_possible": 10,
}

SAMPLE_ASSIGNMENT_OUT_OF_RANGE = {
    "id": 5003,
    "name": "Final Exam",
    "due_at": "2026-06-01T23:59:00Z",
    "points_possible": 200,
}

START = datetime(2026, 4, 19, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 4, 21, 0, 0, tzinfo=timezone.utc)


def _make_plugin() -> CanvasLMSSource:
    plugin = CanvasLMSSource()
    plugin.initialize(CANVAS_CONFIG)
    return plugin


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNormalizeAssignment:
    def test_produces_correct_structure(self):
        plugin = _make_plugin()
        result = plugin._normalize_assignment(SAMPLE_ASSIGNMENT, SAMPLE_COURSE)

        assert result is not None
        assert result["event_id"] == "canvas_5001"
        assert result["title"] == "[CS 101] Homework 3"
        assert result["source"] == "canvas"
        assert result["location"] == ""
        assert "Points: 100" in result["description"]
        assert "CS 101" in result["description"]
        # start and end are the same for deadlines
        assert result["start"] == result["end"]

    def test_returns_none_when_no_due_date(self):
        plugin = _make_plugin()
        result = plugin._normalize_assignment(SAMPLE_ASSIGNMENT_NO_DUE, SAMPLE_COURSE)
        assert result is None

    def test_unknown_course_name(self):
        plugin = _make_plugin()
        result = plugin._normalize_assignment(SAMPLE_ASSIGNMENT, {"id": 1})
        assert result is not None
        assert "Unknown Course" in result["title"]

    def test_missing_points(self):
        assignment = {"id": 9999, "name": "Quiz", "due_at": "2026-04-20T12:00:00Z"}
        plugin = _make_plugin()
        result = plugin._normalize_assignment(assignment, SAMPLE_COURSE)
        assert result is not None
        assert "Points: N/A" in result["description"]


class TestFetchEvents:
    @patch.object(CanvasLMSSource, "_get_courses")
    @patch.object(CanvasLMSSource, "_get_assignments")
    def test_returns_normalized_assignments(self, mock_assignments, mock_courses):
        mock_courses.return_value = [SAMPLE_COURSE]
        mock_assignments.return_value = [SAMPLE_ASSIGNMENT]

        plugin = _make_plugin()
        events = plugin.fetch_events(START, END)

        assert len(events) == 1
        assert events[0]["event_id"] == "canvas_5001"
        assert events[0]["source"] == "canvas"

    @patch.object(CanvasLMSSource, "_get_courses")
    @patch.object(CanvasLMSSource, "_get_assignments")
    def test_filters_by_date_range(self, mock_assignments, mock_courses):
        mock_courses.return_value = [SAMPLE_COURSE]
        mock_assignments.return_value = [
            SAMPLE_ASSIGNMENT,
            SAMPLE_ASSIGNMENT_NO_DUE,
        ]

        plugin = _make_plugin()
        events = plugin.fetch_events(START, END)

        # Only the assignment with a valid due_at is returned (no-due is skipped by normalize)
        assert len(events) == 1
        assert events[0]["event_id"] == "canvas_5001"

    @patch.object(CanvasLMSSource, "_get_courses")
    def test_handles_empty_course_list(self, mock_courses):
        mock_courses.return_value = []

        plugin = _make_plugin()
        events = plugin.fetch_events(START, END)

        assert events == []

    @patch.object(CanvasLMSSource, "_get_courses")
    @patch.object(CanvasLMSSource, "_get_assignments")
    def test_error_isolation_per_course(self, mock_assignments, mock_courses):
        """One broken course should not prevent others from loading."""
        mock_courses.return_value = [SAMPLE_COURSE, SAMPLE_COURSE_2]

        def side_effect(course_id, start, end):
            if course_id == 101:
                raise ConnectionError("API timeout")
            return [SAMPLE_ASSIGNMENT]

        mock_assignments.side_effect = side_effect

        plugin = _make_plugin()
        events = plugin.fetch_events(START, END)

        # Course 101 fails, but course 202 still loads
        assert len(events) == 1
        assert events[0]["title"] == "[MATH 201] Homework 3"


class TestGetAssignmentsFiltering:
    def test_filters_assignments_by_date_range(self):
        plugin = _make_plugin()

        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            SAMPLE_ASSIGNMENT,           # in range
            SAMPLE_ASSIGNMENT_NO_DUE,    # no due_at, skipped
            SAMPLE_ASSIGNMENT_OUT_OF_RANGE,  # out of range
        ]
        mock_resp.raise_for_status = MagicMock()
        plugin._session.get = MagicMock(return_value=mock_resp)

        assignments = plugin._get_assignments(101, START, END)

        assert len(assignments) == 1
        assert assignments[0]["id"] == 5001


class TestRegistryIntegration:
    def test_skips_when_canvas_api_token_missing(self):
        registry = PluginRegistry()
        registry.register(CanvasLMSSource, {"CANVAS_BASE_URL": "https://example.com"})

        assert len(registry.data_sources) == 0
        assert len(registry._failed) == 1
        assert "Missing config" in registry._failed[0][1]
        assert "CANVAS_API_TOKEN" in registry._failed[0][1]

    def test_skips_when_canvas_base_url_missing(self):
        registry = PluginRegistry()
        registry.register(CanvasLMSSource, {"CANVAS_API_TOKEN": "tok"})

        assert len(registry.data_sources) == 0
        assert len(registry._failed) == 1
        assert "CANVAS_BASE_URL" in registry._failed[0][1]

    def test_skips_when_all_config_missing(self):
        registry = PluginRegistry()
        registry.register(CanvasLMSSource, {})

        assert len(registry.data_sources) == 0
        assert len(registry._failed) == 1

    def test_registers_when_config_present(self):
        registry = PluginRegistry()
        registry.register(CanvasLMSSource, CANVAS_CONFIG)

        assert len(registry.data_sources) == 1
        assert registry.data_sources[0].name == "canvas"
