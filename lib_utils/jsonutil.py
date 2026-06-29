from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any


def to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj


def dumps(obj: Any, *, indent: int = 2) -> str:
    # Preserve insertion order of keys (Python 3.7+ dicts maintain insertion order)
    return json.dumps(to_jsonable(obj), indent=indent, sort_keys=False)


def dump_file(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(dumps(obj))
        f.write("\n")


def load_file(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
