import json
import os


def load_config(path="config.json"):
    """
    Load a UTF-8 JSON configuration file.

    The function raises a clear exception when the file is missing or contains
    invalid JSON so the application does not continue with incomplete settings.
    """
    config_path = os.path.abspath(path)

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in configuration file: {config_path}\n"
            f"Line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(f"Configuration root must be a JSON object: {config_path}")

    return data
