import threading
from typing import Any

from ruamel.yaml import YAML

CONFIG_PATH = "config.yaml"
config_lock = threading.Lock()

yaml = YAML()
yaml.preserve_quotes = True


def load_key(key: str) -> Any:
    with config_lock:
        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            data = yaml.load(file)

    keys = key.split(".")
    value = data
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            raise KeyError(f"Key '{k}' not found in configuration")
    return value


def update_key(key: str, new_value: Any) -> bool:
    with config_lock:
        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            data = yaml.load(file)

        keys = key.split(".")
        current = data
        for k in keys[:-1]:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return False

        if isinstance(current, dict) and keys[-1] in current:
            current[keys[-1]] = new_value
            with open(CONFIG_PATH, "w", encoding="utf-8") as file:
                yaml.dump(data, file)
            return True
        else:
            raise KeyError(f"Key '{keys[-1]}' not found in configuration")


# basic utils
def get_joiner(language):
    if language in load_key("language_split_with_space"):
        return " "
    elif language in load_key("language_split_without_space"):
        return ""
    else:
        raise ValueError(f"Unsupported language code: {language}")


if __name__ == "__main__":
    print(load_key("language_split_with_space"))
