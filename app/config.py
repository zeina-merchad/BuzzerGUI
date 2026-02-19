from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class AppConfig:
    base_dir: Path
    packs_dir: Path
    assets_dir: Path
    default_pack_name: str = "default_pack"


    default_timer_seconds: int = 20
    default_answer_seconds: int = 8

def get_config() -> AppConfig:
    base = Path(__file__).resolve().parents[1]
    return AppConfig(
        base_dir=base,
        packs_dir=base / "packs",
        assets_dir=base / "assets",
    )
