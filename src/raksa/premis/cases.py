"""Read premis case exports from the hive-structured YAML directory."""
from pathlib import Path

import yaml

from raksa.models import YAMLCase


def load_cases(yaml_dir: Path) -> list[tuple[YAMLCase, Path]]:
    """Load all cases from a premis hive directory.

    Expects structure: year=*/house=*/*.yaml
    Skips *_chat.yaml files.
    """
    cases = []
    for path in sorted(yaml_dir.rglob("*.yaml")):
        if path.stem.endswith("_chat"):
            continue
        raw = yaml.safe_load(path.read_text())
        if raw is None:
            continue
        case = YAMLCase.model_validate(raw)
        cases.append((case, path))
    return cases


def load_renovation_cases(yaml_dir: Path) -> list[tuple[YAMLCase, Path]]:
    """Load only renovation notification cases (Huoneistomuutosilmoitus)."""
    return [(c, p) for c, p in load_cases(yaml_dir) if c.is_renovation]


def load_fault_cases(yaml_dir: Path) -> list[tuple[YAMLCase, Path]]:
    """Load only non-renovation cases (fault reports, inquiries, etc.)."""
    return [(c, p) for c, p in load_cases(yaml_dir) if not c.is_renovation]


def get_chat_path(case_path: Path) -> Path | None:
    """Get the chat YAML path for a case, or None if it doesn't exist."""
    chat_path = case_path.with_name(case_path.stem + "_chat.yaml")
    return chat_path if chat_path.exists() else None
