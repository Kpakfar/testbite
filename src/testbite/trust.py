"""Which test command may the Stop hook run in which repo? Decided by the user, stored outside the repo."""
import json
import os
from pathlib import Path


def _file():
    return Path(os.environ.get("TESTBITE_CONFIG", "~/.config/testbite/trusted.json")).expanduser()


def load():
    try:
        return json.loads(_file().read_text())
    except (OSError, ValueError):
        return {}


def trust(root, cmd):
    data = load()
    data[str(root)] = cmd
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, indent=2))


def untrust(root):
    data = load()
    if data.pop(str(root), None) is not None:
        _file().write_text(json.dumps(data, indent=2))
        return True
    return False


def command_for(root):
    return load().get(str(root))
