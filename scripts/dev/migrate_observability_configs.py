"""One-off migration of example observability.yaml to three-state lifecycle.

- Remove endpoint: http://localhost:14268/api/traces from test/development
- Remove output: stdout from logging
- Add provider: loki to logging in test/development
- Add visualization: provider: grafana to test/development
- Add alerting: provider: alertmanager to test only
- Production: keep explicit endpoint; leave logging without provider
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

EXAMPLES_ROOT = Path(__file__).resolve().parent.parent.parent / "examples"
LOCALHOST_TRACES = "http://localhost:14268/api/traces"


def migrate_profile(profile_name: str, data: dict) -> bool:
    """Mutate profile dict; return True if any change was made."""
    changed = False
    if profile_name in ("test", "development"):
        if "tracing" in data and data["tracing"].get("endpoint") == LOCALHOST_TRACES:
            del data["tracing"]["endpoint"]
            changed = True
        if "logging" in data:
            if data["logging"].pop("output", None) is not None:
                changed = True
            if "provider" not in data["logging"]:
                data["logging"]["provider"] = "loki"
                changed = True
        if "visualization" not in data:
            data["visualization"] = {"provider": "grafana"}
            changed = True
        if profile_name == "test" and "alerting" not in data:
            data["alerting"] = {"provider": "alertmanager"}
            changed = True
    elif profile_name == "production":
        if "logging" in data and data["logging"].pop("output", None) is not None:
            changed = True
    return changed


def migrate_file(path: Path) -> bool:
    """Migrate one observability.yaml. Return True if changed."""
    content = path.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    if not data or not isinstance(data, dict):
        return False
    any_changed = False
    for profile_name in list(data.keys()):
        if isinstance(data[profile_name], dict):
            if migrate_profile(profile_name, data[profile_name]):
                any_changed = True
    if not any_changed:
        return False
    new_content = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    path.write_text(new_content, encoding="utf-8")
    return True


def main() -> int:
    configs = sorted(EXAMPLES_ROOT.rglob("config/observability.yaml"))
    if not configs:
        print("No observability.yaml files found", file=sys.stderr)
        return 1
    migrated = 0
    for path in configs:
        if migrate_file(path):
            migrated += 1
            print(path.relative_to(EXAMPLES_ROOT))
    print(f"Migrated {migrated}/{len(configs)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
