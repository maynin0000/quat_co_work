import json
import os
from pathlib import Path

from shared.schemas.etf import EtfRawData


def _path() -> Path:
    configured = os.getenv("ETF_SNAPSHOT_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "data_pipeline" / "data" / "etf_snapshot.json"


class EtfRepo:
    def __init__(self, path: Path | None = None):
        self.path = path or _path()

    def load_payload(self):
        if not self.path.exists():
            return {"etfs": [], "limitations": ["ETF 스냅샷이 생성되지 않았습니다."]}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def get_all(self):
        return [EtfRawData(**row) for row in self.load_payload().get("etfs", [])]
