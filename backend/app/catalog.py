"""Load the PDPL OSCAL catalog into plain objects, and write them back out as OSCAL.

catalog/pdpl-catalog.json is the canonical source. The app never keeps a second copy of
requirement text in the database; answers and results reference requirement ids.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .config import REPO_DIR
from .oscal import NS, NS_AR, canon_ns
from .oscal.validate import errors as oscal_errors

CATALOG_PATH = REPO_DIR / "catalog" / "pdpl-catalog.json"


@dataclass(frozen=True)
class Text:
    en: str
    ar: str = ""

    def as_dict(self) -> dict:
        return {"en": self.en, "ar": self.ar}


@dataclass(frozen=True)
class Requirement:
    id: str
    label: str
    area_id: str
    title: Text
    statement: Text
    question: Text
    guidance: Text
    weight: int
    technical: bool
    verified: bool
    source_status: str
    source: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id, "label": self.label, "area_id": self.area_id,
            "title": self.title.as_dict(), "statement": self.statement.as_dict(),
            "question": self.question.as_dict(), "guidance": self.guidance.as_dict(),
            "weight": self.weight, "technical": self.technical, "verified": self.verified,
            "source_status": self.source_status, "source": self.source,
        }


@dataclass(frozen=True)
class Area:
    id: str
    label: str
    title: Text
    overview: Text
    requirements: tuple[Requirement, ...] = field(default_factory=tuple)

    @property
    def weight(self) -> int:
        return sum(r.weight for r in self.requirements)

    def as_dict(self, with_requirements: bool = True) -> dict:
        d = {"id": self.id, "label": self.label, "title": self.title.as_dict(),
             "overview": self.overview.as_dict(), "weight": self.weight,
             "requirement_count": len(self.requirements)}
        if with_requirements:
            d["requirements"] = [r.as_dict() for r in self.requirements]
        return d


@dataclass(frozen=True)
class Catalog:
    uuid: str
    title: str
    version: str
    last_modified: str
    remarks: str
    areas: tuple[Area, ...]
    back_matter: dict

    @property
    def requirements(self) -> list[Requirement]:
        return [r for a in self.areas for r in a.requirements]

    def requirement(self, rid: str) -> Requirement | None:
        return self._index().get(rid)

    def area(self, aid: str) -> Area | None:
        return next((a for a in self.areas if a.id == aid), None)

    def _index(self) -> dict[str, Requirement]:
        return {r.id: r for r in self.requirements}


class CatalogError(ValueError):
    pass


def _prop(props: list[dict], name: str, ns: str | None = None, default: str = "") -> str:
    for p in props or []:
        if p.get("name") == name and (ns is None or canon_ns(p.get("ns")) == ns):
            return p.get("value", default)
    return default


def _part(parts: list[dict], name: str, ar: bool = False) -> str:
    for p in parts or []:
        if p.get("name") == name and (canon_ns(p.get("ns")) == NS_AR) == ar:
            return p.get("prose", "")
    return ""


def parse(doc: dict, validate: bool = True) -> Catalog:
    if validate:
        errs = oscal_errors(doc, "catalog")
        if errs:
            raise CatalogError("catalog does not validate against the OSCAL schema: " + "; ".join(errs[:5]))
    cat = doc.get("catalog") or {}
    md = cat.get("metadata", {})
    areas = []
    for g in cat.get("groups", []):
        reqs = []
        for c in g.get("controls", []):
            props = c.get("props", [])
            reqs.append(Requirement(
                id=c["id"],
                label=_prop(props, "label") or c["id"].upper(),
                area_id=g["id"],
                title=Text(c.get("title", ""), _prop(props, "title-ar", NS)),
                statement=Text(_part(c.get("parts"), "statement"), _part(c.get("parts"), "statement", True)),
                question=Text(_part(c.get("parts"), "assessment-objective"), _part(c.get("parts"), "assessment-objective", True)),
                guidance=Text(_part(c.get("parts"), "guidance"), _part(c.get("parts"), "guidance", True)),
                weight=int(_prop(props, "weight", NS, "1") or 1),
                technical=_prop(props, "evidence-type", NS) == "technical",
                verified=_prop(props, "verified", NS, "false").lower() == "true",
                source_status=_prop(props, "source-status", NS, "needed"),
                source=_prop(props, "source", NS),
            ))
        gp = g.get("props", [])
        areas.append(Area(
            id=g["id"], label=_prop(gp, "label") or g["id"].upper(),
            title=Text(g.get("title", ""), _prop(gp, "title-ar", NS)),
            overview=Text(_part(g.get("parts"), "overview"), _part(g.get("parts"), "overview", True)),
            requirements=tuple(reqs),
        ))
    result = Catalog(
        uuid=cat.get("uuid", ""), title=md.get("title", ""), version=md.get("version", ""),
        last_modified=md.get("last-modified", ""), remarks=md.get("remarks", ""),
        areas=tuple(areas), back_matter=cat.get("back-matter", {}),
    )
    _check_structure(result)
    return result


def _check_structure(cat: Catalog) -> None:
    ids = [r.id for r in cat.requirements]
    if len(ids) != len(set(ids)):
        raise CatalogError("duplicate requirement ids")
    for r in cat.requirements:
        if not r.title.en or not r.statement.en:
            raise CatalogError(f"{r.id}: title and statement are required")
        if r.weight < 1 or r.weight > 5:
            raise CatalogError(f"{r.id}: weight must be between 1 and 5")


def _ns_prop(name: str, value) -> dict:
    return {"name": name, "value": str(value), "ns": NS}


def _parts(cid: str, pairs: list[tuple[str, str, Text]]) -> list[dict]:
    out = []
    for suffix, name, text in pairs:
        if text.en:
            out.append({"id": f"{cid}_{suffix}", "name": name, "prose": text.en})
        if text.ar:
            out.append({"id": f"{cid}_{suffix}.ar", "name": name, "ns": NS_AR, "prose": text.ar})
    return out


def to_oscal(cat: Catalog) -> dict:
    """Serialise back to OSCAL. parse(to_oscal(c)) == c is enforced by tests."""
    groups = []
    for i, a in enumerate(cat.areas, start=1):
        controls = []
        for r in a.requirements:
            props = [{"name": "label", "value": r.label}]
            if r.title.ar:
                props.append(_ns_prop("title-ar", r.title.ar))
            props += [
                _ns_prop("weight", r.weight),
                _ns_prop("evidence-type", "technical" if r.technical else "organizational"),
                _ns_prop("verified", "true" if r.verified else "false"),
                _ns_prop("source-status", r.source_status),
            ]
            if r.source:
                props.append(_ns_prop("source", r.source))
            controls.append({
                "id": r.id, "class": "pdpl-requirement", "title": r.title.en, "props": props,
                "parts": _parts(r.id, [("smt", "statement", r.statement), ("obj", "assessment-objective", r.question),
                                       ("gdn", "guidance", r.guidance)]),
            })
        gprops = [{"name": "label", "value": a.label}]
        if a.title.ar:
            gprops.append(_ns_prop("title-ar", a.title.ar))
        gprops.append(_ns_prop("sort-id", f"{i:02d}"))
        groups.append({"id": a.id, "class": "pdpl-area", "title": a.title.en, "props": gprops,
                       "parts": _parts(a.id, [("ovw", "overview", a.overview)]), "controls": controls})
    md = {"title": cat.title, "last-modified": cat.last_modified, "version": cat.version,
          "oscal-version": "1.1.3"}
    unverified = sum(1 for r in cat.requirements if not r.verified)
    md["props"] = [
        _ns_prop("verified", "false" if unverified else "true"),
        _ns_prop("disclaimer", "Plain-language drafting for readiness tracking. Not legal advice. "
                               "Not verified against the official legal text." if unverified else
                               "Readiness tracking aid. Not legal advice."),
    ]
    if cat.remarks:
        md["remarks"] = cat.remarks
    doc = {"catalog": {"uuid": cat.uuid, "metadata": md, "groups": groups}}
    if cat.back_matter:
        doc["catalog"]["back-matter"] = cat.back_matter
    return doc


def load_path(path: Path) -> Catalog:
    return parse(json.loads(path.read_text(encoding="utf-8")))


@lru_cache
def get_catalog() -> Catalog:
    from .config import get_settings

    override = get_settings().data_dir / "catalog-override.json"
    if override.exists():
        try:
            return load_path(override)
        except (CatalogError, ValueError):
            pass  # fall back to the shipped catalog; the import endpoint validates before saving
    return load_path(CATALOG_PATH)


def reload_catalog() -> Catalog:
    get_catalog.cache_clear()
    return get_catalog()
