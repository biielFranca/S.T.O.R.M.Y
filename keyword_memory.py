import json
from pathlib import Path

import config


def _file_path() -> Path:
    return Path(__file__).parent / config.CUSTOM_KEYWORDS_FILE


def load_custom_keywords() -> dict[str, str]:
    path = _file_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k).lower().strip(): str(v).strip() for k, v in data.items()}
        return {}
    except (json.JSONDecodeError, OSError):
        return {}


def add_custom_keyword(keyword: str, action: str) -> bool:
    keyword = keyword.lower().strip()
    action = action.strip()
    if not keyword or not action:
        return False

    keywords = load_custom_keywords()
    keywords[keyword] = action

    _file_path().write_text(
        json.dumps(keywords, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True
