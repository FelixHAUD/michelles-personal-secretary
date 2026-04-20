"""Tests for plugin registry — config validation, error isolation, categorization."""

from secretary.plugin import ConfigRequirement, DataSource, PluginRegistry, Tool


class FakeSource(DataSource):
    name = "fake_source"
    description = "test source"
    config_schema = [
        ConfigRequirement(key="SOURCE_KEY", description="required key"),
    ]

    def initialize(self, config):
        self._key = config["SOURCE_KEY"]

    def fetch_events(self, start, end):
        return []


class FakeTool(Tool):
    name = "fake_tool"
    description = "test tool"
    config_schema = []

    def initialize(self, config):
        pass

    def get_tool_definition(self):
        return {"name": "test", "description": "test", "input_schema": {}}

    def execute(self, tool_input):
        return "ok"


class BrokenPlugin(DataSource):
    name = "broken"
    description = "always fails"
    config_schema = []

    def initialize(self, config):
        raise RuntimeError("I'm broken!")

    def fetch_events(self, start, end):
        return []


class TestPluginRegistry:
    def test_registers_data_source(self):
        registry = PluginRegistry()
        registry.register(FakeSource, {"SOURCE_KEY": "value"})

        assert len(registry.data_sources) == 1
        assert registry.data_sources[0].name == "fake_source"

    def test_registers_tool(self):
        registry = PluginRegistry()
        registry.register(FakeTool, {})

        assert len(registry.tools) == 1

    def test_skips_plugin_with_missing_config(self):
        registry = PluginRegistry()
        registry.register(FakeSource, {})  # Missing SOURCE_KEY

        assert len(registry.data_sources) == 0
        assert len(registry._failed) == 1
        assert "Missing config" in registry._failed[0][1]

    def test_isolates_broken_plugin(self):
        registry = PluginRegistry()
        registry.register(BrokenPlugin, {})

        assert len(registry.data_sources) == 0
        assert len(registry._failed) == 1
        assert "broken" in registry._failed[0][1].lower()

    def test_broken_plugin_doesnt_affect_others(self):
        registry = PluginRegistry()
        registry.register(BrokenPlugin, {})
        registry.register(FakeTool, {})

        assert len(registry.tools) == 1
        assert len(registry._failed) == 1

    def test_summary_shows_loaded_and_skipped(self):
        registry = PluginRegistry()
        registry.register(FakeSource, {"SOURCE_KEY": "val"})
        registry.register(BrokenPlugin, {})

        summary = registry.summary()
        assert "1 loaded" in summary
        assert "1 skipped" in summary
        assert "fake_source" in summary
