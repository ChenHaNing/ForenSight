import json
import time
from pathlib import Path
from typing import Any, Dict


def log_step(output_dir: Path, step: str, payload: Dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "run.log"
    entry = {"ts": time.time(), "step": step, "payload": payload}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
