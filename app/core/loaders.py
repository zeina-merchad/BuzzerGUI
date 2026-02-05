import json
from pathlib import Path
from typing import List, Tuple, Optional
import uuid

from app.constants import MediaType
from app.core.models import GameConfig, Media, Question


class PackError(Exception):
    """Custom exception for pack loading/saving errors"""
    pass


def load_pack(pack_dir: Path) -> Tuple[GameConfig, List[Question]]:
    """
    Load a question pack from a directory.
    
    Args:
        pack_dir: Path to pack directory
        
    Returns:
        Tuple of (GameConfig, List[Question])
        
    Raises:
        PackError: If pack cannot be loaded
    """
    pack_dir = pack_dir.resolve()
    
    if not pack_dir.exists():
        raise PackError(f"Pack directory does not exist: {pack_dir}")
    
    if not pack_dir.is_dir():
        raise PackError(f"Path is not a directory: {pack_dir}")
    
    pack_json = pack_dir / "pack.json"
    if not pack_json.exists():
        raise PackError(f"Missing pack.json: {pack_json}")
    
    try:
        pack = _read_json(pack_json)
    except Exception as e:
        raise PackError(f"Failed to read pack.json: {e}")
    
    # Load configuration with cascading attempts support
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
        # NEW: Cascading attempts fields
        enable_cascading_attempts=bool(pack.get("enable_cascading_attempts", True)),
        reset_timer_each_attempt=bool(pack.get("reset_timer_each_attempt", False)),
        penalty_for_wrong=int(pack.get("penalty_for_wrong", 0)),
        bonus_for_speed=bool(pack.get("bonus_for_speed", False)),
    )
    
    # Validate configuration
    valid, error = cfg.validate()
    if not valid:
        raise PackError(error)
    
    # Load questions
    questions: List[Question] = []
    errors: List[str] = []
    
    for rel in cfg.question_files:
        q_path = (cfg.pack_dir / rel).resolve()
        if not q_path.exists():
            errors.append(f"Missing question file: {q_path}")
            continue
        
        try:
            question = _load_question(cfg.pack_dir, q_path)
            
            # Validate media if present
            if question.media.type != MediaType.NONE:
                valid, error = question.validate_media(cfg.pack_dir)
                if not valid:
                    errors.append(f"{q_path.name}: {error}")
                    continue
            
            questions.append(question)
        except Exception as e:
            errors.append(f"{q_path.name}: {e}")
    
    if errors:
        error_msg = "\n".join(errors)
        raise PackError(f"Errors loading questions:\n{error_msg}")
    
    if not questions:
        raise PackError("No valid questions loaded")
    
    return cfg, questions


def save_pack(pack_dir: Path, cfg: GameConfig, questions: List[Question]) -> None:
    """
    Save a question pack to a directory.
    
    Args:
        pack_dir: Path to pack directory
        cfg: Game configuration
        questions: List of questions
        
    Raises:
        PackError: If pack cannot be saved
    """
    pack_dir = pack_dir.resolve()
    
    # Create directory if it doesn't exist
    pack_dir.mkdir(parents=True, exist_ok=True)
    
    # Create questions subdirectory
    questions_dir = pack_dir / "questions"
    questions_dir.mkdir(exist_ok=True)
    
    # Save each question to separate file
    question_files = []
    for i, question in enumerate(questions):
        filename = f"question_{i+1:03d}.json"
        question_path = questions_dir / filename
        
        try:
            _save_question(question_path, question)
            question_files.append(f"questions/{filename}")
        except Exception as e:
            raise PackError(f"Failed to save question {question.id}: {e}")
    
    # Update config with new question files including cascading fields
    pack_data = {
        "name": cfg.name,
        "version": cfg.version,
        "rounds": cfg.rounds,
        "questions_per_round": cfg.questions_per_round,
        "timer_seconds": cfg.timer_seconds,
        "answer_seconds": cfg.answer_seconds,
        "shuffle_questions": cfg.shuffle_questions,
        "question_files": question_files,
        # NEW: Cascading attempts fields
        "enable_cascading_attempts": cfg.enable_cascading_attempts,
        "reset_timer_each_attempt": cfg.reset_timer_each_attempt,
        "penalty_for_wrong": cfg.penalty_for_wrong,
        "bonus_for_speed": cfg.bonus_for_speed,
    }
    
    # Save pack.json
    pack_json = pack_dir / "pack.json"
    try:
        _write_json(pack_json, pack_data)
    except Exception as e:
        raise PackError(f"Failed to save pack.json: {e}")


def create_demo_pack(pack_dir: Path) -> Tuple[GameConfig, List[Question]]:
    """Create a demo question pack with cascading attempts"""
    pack_dir = pack_dir.resolve()
    pack_dir.mkdir(parents=True, exist_ok=True)
    
    cfg = GameConfig(
        name="Demo Football Quiz Pack",
        version=1,
        rounds=1,
        questions_per_round=5,
        timer_seconds=20,
        answer_seconds=8,
        shuffle_questions=False,
        question_files=[],
        pack_dir=pack_dir,
        enable_cascading_attempts=True,  # NEW
        penalty_for_wrong=0,
        bonus_for_speed=False,
    )
    
    questions = [
        Question(
            id="demo1",
            round=1,
            text="Who won the 2014 FIFA World Cup?",
            options=["Germany", "Argentina", "Brazil", "France"],
            correct_index=0,
            media=Media(type=MediaType.NONE, path=None),
            difficulty="easy",
            tags=["world_cup", "2014"],
            # NEW: Cascading points
            points_first_attempt=3,
            points_second_attempt=2,
            points_third_attempt=1,
            max_attempts=3,
        ),
        Question(
            id="demo2",
            round=1,
            text="Which player is known as 'CR7'?",
            options=["Messi", "Cristiano Ronaldo", "Neymar", "Mbappé"],
            correct_index=1,
            media=Media(type=MediaType.NONE, path=None),
            difficulty="easy",
            tags=["players", "nicknames"],
            # NEW: Cascading points
            points_first_attempt=3,
            points_second_attempt=2,
            points_third_attempt=1,
            max_attempts=3,
        ),
        Question(
            id="demo3",
            round=1,
            text="How many players are on the field per team in football?",
            options=["9", "10", "11", "12"],
            correct_index=2,
            media=Media(type=MediaType.NONE, path=None),
            difficulty="easy",
            tags=["rules", "basics"],
            # NEW: Cascading points
            points_first_attempt=3,
            points_second_attempt=2,
            points_third_attempt=1,
            max_attempts=3,
        ),
        Question(
            id="demo4",
            round=1,
            text="Which country has won the most FIFA World Cups?",
            options=["Germany", "Brazil", "Italy", "Argentina"],
            correct_index=1,
            media=Media(type=MediaType.NONE, path=None),
            difficulty="medium",
            tags=["world_cup", "history"],
            # NEW: Cascading points (harder question, more points)
            points_first_attempt=5,
            points_second_attempt=3,
            points_third_attempt=2,
            max_attempts=3,
        ),
        Question(
            id="demo5",
            round=1,
            text="What is the duration of a standard football match (excluding extra time)?",
            options=["80 minutes", "90 minutes", "100 minutes", "120 minutes"],
            correct_index=1,
            media=Media(type=MediaType.NONE, path=None),
            difficulty="easy",
            tags=["rules", "time"],
            # NEW: Cascading points
            points_first_attempt=3,
            points_second_attempt=2,
            points_third_attempt=1,
            max_attempts=3,
        ),
    ]
    
    return cfg, questions


def _load_question(pack_dir: Path, q_path: Path) -> Question:
    """Load a single question from JSON file with cascading attempts support"""
    q = _read_json(q_path)
    
    qid = str(q.get("id", q_path.stem))
    rnd = int(q.get("round", 1))
    text = str(q.get("text", "")).strip()
    
    options = q.get("options", [])
    if not isinstance(options, list) or len(options) < 2:
        raise PackError(f"options must be a list with at least 2 items")
    options = [str(x) for x in options]
    
    correct_index = int(q.get("correct_index", -1))
    if correct_index < 0 or correct_index >= len(options):
        raise PackError(f"correct_index {correct_index} out of range")
    
    # Load media
    media_obj = q.get("media") or {"type": "none", "path": None}
    media_type_str = str(media_obj.get("type", "none")).lower()
    
    if media_type_str not in ("none", "image", "audio", "video"):
        raise PackError(f"invalid media.type '{media_type_str}'")
    
    media_type = MediaType(media_type_str)
    media_path = media_obj.get("path", None)
    
    if media_type != MediaType.NONE and not media_path:
        raise PackError(f"media.path required for media.type={media_type.value}")
    
    # Load optional fields
    difficulty = q.get("difficulty", "medium")
    tags = q.get("tags", [])
    
    points_first = int(q.get("points_first_attempt", 3))
    points_second = int(q.get("points_second_attempt", 2))
    points_third = int(q.get("points_third_attempt", 1))
    max_attempts = int(q.get("max_attempts", 3))
    
    # Legacy support: if old 'points' field exists, use it for first attempt
    if "points" in q and "points_first_attempt" not in q:
        points_first = int(q["points"])
    
    if rnd <= 0:
        raise PackError("round must be >= 1")
    if not text:
        raise PackError("text is empty")
    
    return Question(
        id=qid,
        round=rnd,
        text=text,
        options=options,
        correct_index=correct_index,
        media=Media(type=media_type, path=media_path),
        difficulty=difficulty,
        tags=tags,
        # NEW: Cascading points
        points_first_attempt=points_first,
        points_second_attempt=points_second,
        points_third_attempt=points_third,
        max_attempts=max_attempts,
    )


def _save_question(q_path: Path, question: Question) -> None:
    """Save a single question to JSON file"""
    data = question.to_dict()
    _write_json(q_path, data)


def _read_json(path: Path) -> dict:
    """Read JSON file"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise PackError(f"Invalid JSON in {path.name}: {e}")
    except Exception as e:
        raise PackError(f"Failed to read {path.name}: {e}")


def _write_json(path: Path, data: dict) -> None:
    """Write JSON file"""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        raise PackError(f"Failed to write {path.name}: {e}")


def validate_pack(pack_dir: Path) -> Tuple[bool, List[str]]:
    """
    Validate a pack without loading it fully.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    pack_dir = pack_dir.resolve()
    
    if not pack_dir.exists():
        return False, [f"Pack directory does not exist: {pack_dir}"]
    
    if not pack_dir.is_dir():
        return False, [f"Path is not a directory: {pack_dir}"]
    
    pack_json = pack_dir / "pack.json"
    if not pack_json.exists():
        return False, [f"Missing pack.json"]
    
    try:
        pack = _read_json(pack_json)
    except Exception as e:
        return False, [f"Failed to read pack.json: {e}"]
    
    # Check required fields
    required_fields = ["name", "question_files"]
    for field in required_fields:
        if field not in pack:
            errors.append(f"Missing required field: {field}")
    
    # Check question files exist
    question_files = pack.get("question_files", [])
    if not question_files:
        errors.append("question_files is empty")
    
    for rel in question_files:
        q_path = (pack_dir / rel).resolve()
        if not q_path.exists():
            errors.append(f"Missing question file: {rel}")
    
    return len(errors) == 0, errors


def list_available_packs(packs_dir: Path) -> List[Tuple[str, Path]]:
    """
    List all available packs in the packs directory.
    
    Returns:
        List of (pack_name, pack_path) tuples
    """
    if not packs_dir.exists():
        return []
    
    packs = []
    for item in packs_dir.iterdir():
        if item.is_dir():
            pack_json = item / "pack.json"
            if pack_json.exists():
                try:
                    data = _read_json(pack_json)
                    name = data.get("name", item.name)
                    packs.append((name, item))
                except:
                    # Skip invalid packs
                    continue
    
    return sorted(packs, key=lambda x: x[0])