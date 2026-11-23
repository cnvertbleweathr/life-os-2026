"""
Create checkin/priorities.md from the template, unless it already exists.

priorities.md is yours to edit by hand and is gitignored (the repo is public);
this never overwrites it.

    uv run python -m checkin.init_priorities
"""

from __future__ import annotations

import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "priorities.template.md"
PRIORITIES = HERE / "priorities.md"


def init_priorities(path: Path = PRIORITIES, template: Path = TEMPLATE) -> bool:
    """Copy the template to `path`. Returns True if created, False if it already existed."""
    if path.exists():
        return False
    shutil.copyfile(template, path)
    return True


def main() -> int:
    created = init_priorities()
    print(f"{'created' if created else 'kept existing'} {PRIORITIES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
