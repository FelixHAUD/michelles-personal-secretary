"""Tests for plugin base classes."""

import pytest

from secretary.plugin import DataSource, Delivery, Hook, Tool


class TestPluginABCs:
    def test_cannot_instantiate_data_source_directly(self):
        with pytest.raises(TypeError):
            DataSource()

    def test_cannot_instantiate_tool_directly(self):
        with pytest.raises(TypeError):
            Tool()

    def test_cannot_instantiate_delivery_directly(self):
        with pytest.raises(TypeError):
            Delivery()

    def test_cannot_instantiate_hook_directly(self):
        with pytest.raises(TypeError):
            Hook()

    def test_concrete_data_source_works(self):
        class FakeSource(DataSource):
            name = "fake"
            description = "test"
            config_schema = []

            def initialize(self, config):
                pass

            def fetch_events(self, start, end):
                return []

        source = FakeSource()
        assert source.name == "fake"
        assert source.fetch_events(None, None) == []

    def test_concrete_tool_works(self):
        class FakeTool(Tool):
            name = "fake_tool"
            description = "test"
            config_schema = []

            def initialize(self, config):
                pass

            def get_tool_definition(self):
                return {"name": "test", "description": "test", "input_schema": {}}

            def execute(self, tool_input):
                return "result"

        tool = FakeTool()
        assert tool.execute({}) == "result"
