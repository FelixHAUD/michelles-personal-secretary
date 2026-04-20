"""Cloud Run HTTP entry point.

Cloud Scheduler sends a POST to /run every 6 hours.
This triggers the full pipeline: fetch events -> Gemini -> deliver reminders.
"""

from __future__ import annotations

import os

from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/run", methods=["POST", "GET"])
def run_handler():
    """Run the pipeline once and return a summary."""
    from secretary.config import load_config
    from secretary.pipeline.runner import run_pipeline
    from secretary.plugin import PluginRegistry, discover_plugins
    from secretary.util.log import setup_logging

    setup_logging(verbose=False)
    config = load_config()

    registry = PluginRegistry()
    for plugin_cls in discover_plugins():
        registry.register(plugin_cls, config.merged_env())

    output = run_pipeline(config=config, registry=registry, dry_run=False)

    return jsonify({
        "status": "ok",
        "reminders_sent": len(output.reminders),
        "conflicts_found": len(output.conflicts),
    })


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
