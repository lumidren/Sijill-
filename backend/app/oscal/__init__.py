"""OSCAL is the data contract: the catalog, assessment results and POA&M live in OSCAL JSON."""

OSCAL_VERSION = "1.1.3"
NS = "urn:sijill:oscal"
NS_AR = "urn:sijill:oscal:ar"
# The project was called PDPL-Ready until 2026-11-18; catalogs and exports from then still load.
LEGACY_NS = {"urn:pdpl-ready:oscal": NS, "urn:pdpl-ready:oscal:ar": NS_AR}


def canon_ns(ns: str | None) -> str | None:
    return LEGACY_NS.get(ns, ns) if ns else ns
