"""Validate documents against the vendored official NIST OSCAL JSON schemas.

The schemas use Unicode property escapes (\\p{L}) in `pattern`, which Python's `re`
cannot compile, so `pattern` is re-implemented with the `regex` package.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import regex
from jsonschema import Draft7Validator, FormatChecker, validators
from jsonschema.exceptions import ValidationError

SCHEMA_DIR = Path(__file__).parent / "schemas"
MODELS = {
    "catalog": "oscal_catalog_schema.json",
    "assessment-results": "oscal_assessment-results_schema.json",
    "plan-of-action-and-milestones": "oscal_poam_schema.json",
}


def _pattern(validator, patrn, instance, schema):
    if not validator.is_type(instance, "string"):
        return
    if not regex.search(patrn, instance):
        yield ValidationError(f"{instance!r} does not match {patrn!r}")


_OscalValidator = validators.extend(Draft7Validator, {"pattern": _pattern})


@lru_cache
def _validator(model: str):
    schema = json.loads((SCHEMA_DIR / MODELS[model]).read_text(encoding="utf-8"))
    return _OscalValidator(schema, format_checker=FormatChecker())


def errors(doc: dict, model: str | None = None, limit: int = 20) -> list[str]:
    """Return human-readable schema errors (empty list = valid)."""
    if model is None:
        model = next((m for m in MODELS if m in doc), None)
        if model is None:
            return [f"document has none of the root keys {sorted(MODELS)}"]
    out = []
    for err in _validator(model).iter_errors(doc):
        path = "/".join(str(p) for p in err.absolute_path)
        out.append(f"{path or '<root>'}: {err.message[:300]}")
        if len(out) >= limit:
            break
    return out


def is_valid(doc: dict, model: str | None = None) -> bool:
    return not errors(doc, model, limit=1)
