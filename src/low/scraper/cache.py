from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Optional


class FileCache:
    """Tiny content-addressed file cache: keys are namespaced, values are bytes or JSON."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._stats_lock = threading.Lock()
        self.hits: Counter[str] = Counter()
        self.misses: Counter[str] = Counter()

    def _path(self, namespace: str, key: str, suffix: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        ns_dir = self.root / namespace
        ns_dir.mkdir(parents=True, exist_ok=True)
        return ns_dir / f"{digest}{suffix}"

    def _atomic_write(self, path: Path, data: str) -> None:
        fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _bump(self, attr: str, namespace: str) -> None:
        with self._stats_lock:
            getattr(self, attr)[namespace] += 1

    def get_or_set_json(self, namespace: str, key: str, producer: Callable[[], Any]) -> Any:
        path = self._path(namespace, key, ".json")
        if path.exists():
            self._bump("hits", namespace)
            return json.loads(path.read_text(encoding="utf-8"))
        value = producer()
        self._atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2))
        self._bump("misses", namespace)
        return value

    def get_or_set_text(self, namespace: str, key: str, producer: Callable[[], Optional[str]]) -> Optional[str]:
        path = self._path(namespace, key, ".txt")
        if path.exists():
            self._bump("hits", namespace)
            data = path.read_text(encoding="utf-8")
            return data if data else None
        value = producer()
        self._atomic_write(path, value or "")
        self._bump("misses", namespace)
        return value

    def stats_summary(self) -> str:
        with self._stats_lock:
            namespaces = sorted(set(self.hits) | set(self.misses))
            parts = []
            for ns in namespaces:
                h, m = self.hits[ns], self.misses[ns]
                parts.append(f"{ns}: {h} hit / {m} miss")
            return "; ".join(parts) if parts else "no cache activity"
