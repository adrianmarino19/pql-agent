import json
from pathlib import Path
from typing import Literal

FeedbackValue = Literal["up", "down"]


def write_feedback(log_path: Path, row_id: str, feedback: FeedbackValue) -> bool:
    if feedback not in {"up", "down"}:
        raise ValueError("feedback must be 'up' or 'down'.")
    if not row_id or not log_path.exists():
        return False

    lines = log_path.read_text().splitlines()
    updated = False
    rewritten: list[str] = []

    for line in lines:
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("row_id") == row_id:
            record["user_feedback"] = feedback
            updated = True
        rewritten.append(json.dumps(record))

    if updated:
        log_path.write_text("\n".join(rewritten) + "\n")
    return updated
