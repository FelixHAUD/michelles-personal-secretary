"""CLI interface — subcommands for run, dry-run, test-plugins."""

from __future__ import annotations

import argparse
import sys

from .config import load_config
from .plugin import PluginRegistry, discover_plugins
from .util.log import setup_logging


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="secretary",
        description="AI-powered personal secretary",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    run_parser = sub.add_parser("run", help="Run the pipeline")
    run_parser.add_argument("--once", action="store_true", help="Run once then exit")

    sub.add_parser("dry-run", help="Preview reminders without sending")
    sub.add_parser("test-plugins", help="Validate all loaded plugins")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    setup_logging(verbose=args.verbose)

    # Default to dry-run if no command specified
    command = args.command or "dry-run"

    config = load_config()

    if not config.gemini_api_key:
        print("Error: GEMINI_API_KEY not set. Copy .env.example to .env and fill it in.")
        print("Get a free key at: https://aistudio.google.com/apikey")
        sys.exit(1)

    # Discover and register plugins
    registry = PluginRegistry()
    plugin_classes = discover_plugins()
    for plugin_cls in plugin_classes:
        registry.register(plugin_cls, config.merged_env())

    print(registry.summary())
    print()

    if command == "test-plugins":
        print("Plugin validation complete.")
        return

    if command in ("run", "dry-run"):
        from .pipeline.runner import run_pipeline

        dry_run = command == "dry-run"
        if not registry.data_sources:
            print("Error: No data source plugins loaded. Check your configuration.")
            sys.exit(1)

        print("Fetching events...")
        run_pipeline(config=config, registry=registry, dry_run=dry_run)
