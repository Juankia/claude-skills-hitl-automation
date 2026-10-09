#!/usr/bin/env python3
"""Install the skills into Claude Code, or package them for Claude.ai upload.

    python scripts/install_skills.py                 # -> ~/.claude/skills (personal)
    python scripts/install_skills.py --project DIR   # -> DIR/.claude/skills (shared with a repo)
    python scripts/install_skills.py --zip dist/     # -> dist/<skill>.zip for Claude.ai

Each skill folder is copied as-is and the shared ``client_state.py`` module is
vendored into its ``scripts/`` directory so the installed skill is
self-contained. Works the same on macOS, Linux and Windows (pathlib only).
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
SHARED = REPO / "shared" / "client_state.py"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


def skill_dirs() -> list[Path]:
    return sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())


def install(dest_root: Path, force: bool = False) -> list[Path]:
    dest_root.mkdir(parents=True, exist_ok=True)
    installed = []
    for skill in skill_dirs():
        target = dest_root / skill.name
        if target.exists():
            if not force:
                raise FileExistsError(f"{target} exists (use --force to overwrite)")
            shutil.rmtree(target)
        shutil.copytree(skill, target, ignore=IGNORE)
        shutil.copy2(SHARED, target / "scripts" / "client_state.py")
        installed.append(target)
    return installed


def package(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    archives = []
    for skill in skill_dirs():
        archive = out_dir / f"{skill.name}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(skill.rglob("*")):
                if file.is_file() and "__pycache__" not in file.parts:
                    zf.write(file, Path(skill.name) / file.relative_to(skill))
            zf.write(SHARED, Path(skill.name) / "scripts" / "client_state.py")
        archives.append(archive)
    return archives


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dest", type=Path, help="custom skills directory")
    group.add_argument("--project", type=Path, help="install into PROJECT/.claude/skills")
    group.add_argument("--zip", type=Path, metavar="OUT_DIR", help="build one zip per skill for Claude.ai")
    parser.add_argument("--force", action="store_true", help="overwrite existing installs")
    args = parser.parse_args(argv)

    if args.zip:
        for archive in package(args.zip):
            print(f"packaged {archive}")
        return 0
    dest = args.dest or (args.project / ".claude" / "skills" if args.project else Path.home() / ".claude" / "skills")
    try:
        for target in install(dest, force=args.force):
            print(f"installed {target}")
    except FileExistsError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
