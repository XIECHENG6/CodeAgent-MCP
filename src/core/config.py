import os
from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_settings() -> dict:
    return load_yaml(CONFIG_DIR / "settings.yaml")


def load_agents_config() -> dict:
    return load_yaml(CONFIG_DIR / "agents.yaml")


def load_mcp_config() -> dict:
    return load_yaml(CONFIG_DIR / "mcp_servers.yaml")


def get_project_root() -> Path:
    return PROJECT_ROOT
