import re
import zipfile

import pytest

import install_skills
from conftest import REPO

SKILL_NAMES = ["client-intake", "document-drafting", "filing-prep-checklist"]


def _frontmatter(text: str) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, "SKILL.md must start with YAML frontmatter"
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_skill_frontmatter(name):
    fm = _frontmatter((REPO / "skills" / name / "SKILL.md").read_text(encoding="utf-8"))
    assert fm["name"] == name
    assert re.fullmatch(r"[a-z0-9-]{1,64}", fm["name"])
    assert 50 < len(fm["description"]) <= 1024
    assert "<" not in fm["description"] and ">" not in fm["description"]


def test_install_vendors_shared_module(tmp_path):
    installed = install_skills.install(tmp_path / "skills")
    assert [p.name for p in installed] == SKILL_NAMES
    for target in installed:
        assert (target / "SKILL.md").is_file()
        assert (target / "scripts" / "client_state.py").is_file()
    with pytest.raises(FileExistsError):
        install_skills.install(tmp_path / "skills")
    install_skills.install(tmp_path / "skills", force=True)


def test_installed_skill_runs_standalone(tmp_path, state_dir):
    """The vendored copy must work without the repo's shared/ directory."""
    import subprocess
    import sys

    target = install_skills.install(tmp_path / "skills")[0]
    example = target / "templates" / "intake_answers.example.json"
    proc = subprocess.run(
        [sys.executable, "-I", str(target / "scripts" / "validate_intake.py"), str(example), "--dry-run"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_zip_packages(tmp_path):
    archives = install_skills.package(tmp_path / "dist")
    with zipfile.ZipFile(archives[0]) as zf:
        names = zf.namelist()
    assert "client-intake/SKILL.md" in names
    assert "client-intake/scripts/client_state.py" in names
