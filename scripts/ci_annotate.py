"""Turn failed tests in a JUnit XML report into GitHub Actions error annotations.

Annotations are readable through the public checks API, so a failing run explains itself without
anyone signing in to read the raw log. Usage: python scripts/ci_annotate.py backend/report.xml
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


def _clean(text: str, limit: int = 900) -> str:
    # Workflow commands end at a newline; GitHub decodes %0A back into one.
    text = (text or "").strip()
    if len(text) > limit:
        text = "..." + text[-limit:]
    return text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")


def main(path: str) -> int:
    root = ET.parse(path).getroot()
    failed = 0
    for case in root.iter("testcase"):
        for kind in ("failure", "error"):
            node = case.find(kind)
            if node is None:
                continue
            failed += 1
            if failed > 10:  # GitHub keeps ten error annotations per step
                continue
            name = f"{case.get('classname', '')}::{case.get('name', '')}"
            detail = (node.get("message") or "") + "\n" + (node.text or "")
            print(f"::error title={_clean(name, 200)}::{_clean(detail)}")
    print(f"{failed} failing test(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
