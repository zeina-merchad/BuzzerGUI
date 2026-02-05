import json
from pathlib import Path
from typing import List, Tuple

from app.constants import MediaType
from app.core.models import GameConfig, Media, Question

class PackError(Exception):
    pass

def load_pack(pack_dir: Path) -> Tuple[GameConfig, List[Question]]:
    pack_dir = pack_dir.resolve()
    pack_json = pack_dir / "pack.json"
    if not pack_json.exists():
        raise PackError(f"Missing pack.json: {pack_json}")

    pack = _read_json(pack_json)

    cfg = GameConfig(
        name=str(pack.get("name", pack_dir.name)),
        version=int(pack.get("version", 1)),
        rounds=int(pack.get("rounds", 1)),
        questions_per_round=int(pack.get("questions_per_round", 10)),
        timer_seconds=int(pack.get("timer_seconds", 20)),
        answer_seconds=int(pack.get("answer_seconds", 8)),
        shuffle_questions=bool(pack.get("shuffle_questions", False)),
        question_files=list(pack.get("question_files", [])),
        pack_dir=pack_dir,
    )

    if cfg.rounds <= 0:
        raise PackError("rounds must be >= 1")
    if cfg.questions_per_round <= 0:
        raise PackError("questions_per_round must be >= 1")
    if cfg.timer_seconds <= 0:
        raise PackError("timer_seconds must be >= 1")
    if cfg.answer_seconds <= 0:
        raise PackError("answer_seconds must be >= 1")
    if not cfg.question_files:
        raise PackError("question_files is empty")

    questions: List[Question] = []
    for rel in cfg.question_files:
        q_path = (cfg.pack_dir / rel).resolve()
        if not q_path.exists():
            raise PackError(f"Missing question file: {q_path}")
        questions.append(_load_question(cfg.pack_dir, q_path))

    return cfg, questions

def _load_question(pack_dir: Path, q_path: Path) -> Question:
    q = _read_json(q_path)

    qid = str(q.get("id", q_path.stem))
    rnd = int(q.get("round", 1))
    text = str(q.get("text", "")).strip()

    options = q.get("options", [])
    if not isinstance(options, list) or len(options) < 2:
        raise PackError(f"{q_path.name}: options must be a list with at least 2 items")
    options = [str(x) for x in options]

    correct_index = int(q.get("correct_index", -1))
    if correct_index < 0 or correct_index >= len(options):
        raise PackError(f"{q_path.name}: correct_index out of range")

    media_obj = q.get("media") or {"type": "none", "path": None}
    media_type_str = str(media_obj.get("type", "none")).lower()
    if media_type_str not in ("none", "image", "audio", "video"):
        raise PackError(f"{q_path.name}: invalid media.type '{media_type_str}'")

    media_type = MediaType(media_type_str)
    media_path = media_obj.get("path", None)

    if media_type != MediaType.NONE:
        if not media_path or not isinstance(media_path, str):
            raise PackError(f"{q_path.name}: media.path required for media.type={media_type.value}")
        abs_media = (pack_dir / media_path).resolve()
        if not abs_media.exists():
            raise PackError(f"{q_path.name}: missing media file '{media_path}'")

    if rnd <= 0:
        raise PackError(f"{q_path.name}: round must be >= 1")
    if not text:
        raise PackError(f"{q_path.name}: text is empty")

    return Question(
        id=qid,
        round=rnd,
        text=text,
        options=options,
        correct_index=correct_index,
        media=Media(type=media_type, path=media_path),
    )

def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise PackError(f"Failed to read JSON {path.name}: {e}")
