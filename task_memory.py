import json
from pathlib import Path

import config


def _file_path() -> Path:
    return Path(__file__).parent / config.CUSTOM_TASKS_FILE


def load_custom_tasks() -> dict[str, dict]:
    path = _file_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_custom_tasks(tasks: dict[str, dict]) -> None:
    _file_path().write_text(
        json.dumps(tasks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_custom_task(
    action_name: str,
    task_type: str,
    value: str,
    success_message: str,
) -> bool:
    action_name = action_name.strip()
    if not action_name or not task_type or not value:
        return False

    tasks = load_custom_tasks()
    tasks[action_name] = {
        "type": task_type.strip(),
        "value": value.strip(),
        "success_message": success_message.strip(),
    }
    save_custom_tasks(tasks)
    return True


def get_all_tasks() -> dict[str, dict]:
    tasks = dict(config.BASE_TASKS)
    tasks.update(load_custom_tasks())
    return tasks
