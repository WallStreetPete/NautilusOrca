"""Model registry.

Versioned, file-backed model storage:

    data/models/<name>/<version>/model.pkl
    data/models/<name>/<version>/meta.json

The registry is a thin convenience layer; we deliberately avoid MLflow et al.
in v0. When/if we need experiment tracking later, swap the registry impl.
"""

from __future__ import annotations

import json
import pickle
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from blackorca.config import get_settings
from blackorca.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class ModelMeta:
    name: str
    version: str
    framework: str
    features: list[str]
    target: str
    train_start: str
    train_end: str
    metrics: dict[str, float] = field(default_factory=dict)
    notes: str = ""
    created_at: str = ""


class ModelRegistry:
    def __init__(self, root: str | Path | None = None) -> None:
        if root is None:
            root = Path(get_settings().repo_root) / "data" / "models"
        self.root = Path(root)

    def _path(self, name: str, version: str) -> Path:
        return self.root / name / version

    def save(self, name: str, version: str, model: Any, meta: ModelMeta) -> Path:
        target = self._path(name, version)
        target.mkdir(parents=True, exist_ok=True)
        (target / "model.pkl").write_bytes(pickle.dumps(model))
        meta.created_at = datetime.now(UTC).isoformat()
        (target / "meta.json").write_text(json.dumps(asdict(meta), indent=2), encoding="utf-8")
        log.info("model.saved", name=name, version=version, path=str(target))
        return target

    def load(self, name: str, version: str) -> tuple[Any, ModelMeta]:
        target = self._path(name, version)
        if not target.exists():
            raise FileNotFoundError(f"no model at {target}")
        model = pickle.loads((target / "model.pkl").read_bytes())
        meta = ModelMeta(**json.loads((target / "meta.json").read_text(encoding="utf-8")))
        return model, meta

    def list(self) -> dict[str, list[str]]:
        if not self.root.exists():
            return {}
        out: dict[str, list[str]] = {}
        for name_dir in self.root.iterdir():
            if not name_dir.is_dir():
                continue
            versions = sorted([v.name for v in name_dir.iterdir() if v.is_dir()])
            if versions:
                out[name_dir.name] = versions
        return out

    def delete(self, name: str, version: str) -> None:
        target = self._path(name, version)
        if target.exists():
            shutil.rmtree(target)


__all__ = ["ModelMeta", "ModelRegistry"]
