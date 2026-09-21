"""Every link into this repository, from the write-up or the site, points at a file that exists.

Relative markdown links are resolved against the file that holds them. Absolute links to this
repository on GitHub are resolved against the checkout, since a blob URL cannot redirect. A target
counts only if git tracks it: a file that exists locally but is ignored is a dead link once pushed.
"""

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

MARKDOWN_LINK = re.compile(r"\]\(([^)\s]+)\)")
REPO_URL = re.compile(r"https://github\.com/jjd-lab/jev-synthetic-survey/(?:blob|tree)/main/([^\s\"')#]+)")


def tracked() -> set[Path]:
    listed = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True,
                            check=True).stdout.splitlines()
    files = {REPO_ROOT / name for name in listed}
    return files | {parent for f in files for parent in f.parents}


def test_links_into_the_repository_resolve():
    known = tracked()
    broken = []
    for source in sorted(f for f in known if f.suffix in (".md", ".html")):
        text = source.read_text(encoding="utf-8")
        targets = [(source.parent / t.split("#")[0]) for t in MARKDOWN_LINK.findall(text)
                   if source.suffix == ".md" and not re.match(r"[a-z]+:|#", t)]
        targets += [REPO_ROOT / t for t in REPO_URL.findall(text)]
        broken += [f"{source.relative_to(REPO_ROOT)} -> {target}"
                   for target in targets if target.resolve() not in known]
    assert not broken, "\n".join(broken)
