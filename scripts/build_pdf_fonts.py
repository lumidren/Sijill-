"""Build the TTF fonts the PDF reports use, from the npm package @fontsource/ibm-plex-sans-arabic.

  python scripts/build_pdf_fonts.py      (needs `pip install fonttools` and `npm ci` in frontend/)

ReportLab needs TrueType files; the npm package ships WOFF subsets. This merges the arabic
and latin subsets of one weight into a single TTF (renamed "PDPL Sans", as the SIL OFL asks of
modified fonts) and writes backend/app/reports/fonts/. The output is committed, so running the
app never needs this script.
"""
from pathlib import Path

from fontTools.merge import Merger
from fontTools.ttLib import TTFont

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "frontend/node_modules/@fontsource/ibm-plex-sans-arabic"
OUT = REPO / "backend/app/reports/fonts"
WEIGHTS = {"Regular": 400, "Bold": 700}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for style, weight in WEIGHTS.items():
        parts = []
        for subset in ("arabic", "latin", "latin-ext"):
            woff = SRC / "files" / f"ibm-plex-sans-arabic-{subset}-{weight}-normal.woff"
            ttf = OUT / f"_tmp-{subset}.ttf"
            font = TTFont(woff)
            font.flavor = None
            font.save(ttf)
            parts.append(str(ttf))
        merged = Merger().merge(parts)
        name = merged["name"]
        for rec in list(name.names):
            if rec.nameID in (1, 4, 6, 16):
                value = {1: "PDPL Sans", 4: f"PDPL Sans {style}", 6: f"PDPLSans-{style}", 16: "PDPL Sans"}[rec.nameID]
                name.setName(value, rec.nameID, rec.platformID, rec.platEncID, rec.langID)
        out = OUT / f"PDPLSans-{style}.ttf"
        merged.save(out)
        for p in parts:
            Path(p).unlink()
        print("wrote", out.relative_to(REPO), out.stat().st_size, "bytes")
    (OUT / "OFL.txt").write_text((SRC / "LICENSE").read_text(encoding="utf-8"), encoding="utf-8")
    (OUT / "README.md").write_text(
        "PDPL Sans is IBM Plex Sans Arabic (arabic + latin + latin-ext subsets, from the npm package "
        "@fontsource/ibm-plex-sans-arabic) merged into one TrueType file per weight by "
        "scripts/build_pdf_fonts.py and renamed. Licensed under the SIL Open Font License 1.1 (OFL.txt).\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
