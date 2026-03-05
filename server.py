import os
import sys
from typing import Any, Dict, List, Optional

import requests
import yaml
from mcp.server.fastmcp import FastMCP
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CATALOG_URL_DEFAULT = (
    "https://raw.githubusercontent.com/ICICLE-ai/CI-Components-Catalog/dev/release_catalog.yml"
)

# IMPORTANT for stdio servers: never print to stdout (it breaks JSON-RPC).
def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _norm(s: Optional[str]) -> str:
    return (s or "").strip()


def _build_session() -> requests.Session:
    timeout_s = float(os.environ.get("CATALOG_TIMEOUT", "30"))
    retries = int(os.environ.get("CATALOG_RETRIES", "3"))
    backoff = float(os.environ.get("CATALOG_BACKOFF", "0.3"))

    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)

    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": "catalog-mcp/1.0"})
    # Store defaults for use in load_catalog_yaml.
    session._catalog_timeout = timeout_s  # type: ignore[attr-defined]
    return session


def get_catalog_url() -> str:
    return os.environ.get("ICICLE_CATALOG_URL", CATALOG_URL_DEFAULT)


def load_catalog_yaml(catalog_url: str, session: requests.Session) -> Dict[str, Any]:
    timeout = getattr(session, "_catalog_timeout", 30.0)
    r = session.get(catalog_url, timeout=timeout)
    r.raise_for_status()

    # This file is YAML; it should parse into {"components": [ ... ]}.
    data = yaml.safe_load(r.text)
    if not isinstance(data, dict) or "components" not in data:
        raise ValueError("Unexpected YAML format: expected top-level key 'components'.")
    if not isinstance(data["components"], list):
        raise ValueError("Unexpected YAML format: 'components' must be a list.")
    return data


def iter_components(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    comps = data.get("components", [])
    # Defensive: ensure dicts
    return [c for c in comps if isinstance(c, dict)]


def component_matches(
    c: Dict[str, Any],
    query: Optional[str] = None,
    primary_thrust: Optional[str] = None,
    target_release: Optional[str] = None,
    public_access: Optional[bool] = None,
) -> bool:
    if primary_thrust and _norm(c.get("primaryThrust")) != primary_thrust.strip():
        return False
    if target_release and _norm(c.get("targetIcicleRelease")) != target_release.strip():
        return False
    if public_access is not None:
        # YAML uses true/false; sometimes strings sneak in—normalize.
        val = c.get("publicAccess")
        if isinstance(val, str):
            val = val.strip().lower() in ("true", "yes", "1")
        if bool(val) != bool(public_access):
            return False

    if query:
        q = query.strip().lower()
        hay = " ".join(
            [
                _norm(str(c.get("id"))),
                _norm(str(c.get("name"))),
                _norm(str(c.get("owner"))),
                _norm(str(c.get("description"))),
                _norm(str(c.get("primaryThrust"))),
                _norm(str(c.get("targetIcicleRelease"))),
            ]
        ).lower()
        return q in hay
    return True


def brief_component(c: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": c.get("id"),
        "name": c.get("name"),
        "primaryThrust": c.get("primaryThrust"),
        "targetIcicleRelease": c.get("targetIcicleRelease"),
        "status": c.get("status"),
        "publicAccess": c.get("publicAccess"),
    }


def extract_links(c: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        "website",
        "sourceCodeUrl",
        "releaseNotesUrl",
        "usageDocumentationUrl",
        "developerDocumentationUrl",
        "trainingTutorialsUrl",
        "containerImage",
        "licenseUrl",
        "doi",
        "pypiPackage",
    ]
    out = {k: c.get(k) for k in keys if c.get(k) not in (None, "", False)}
    # Some entries include dependent components; include those IDs too.
    deps = c.get("hasDependentComponents")
    if isinstance(deps, list):
        out["hasDependentComponents"] = deps
    return out


# MCP server
mcp = FastMCP("ICICLE Catalog MCP", json_response=True)
_session = _build_session()


@mcp.tool()
def list_components(
    primary_thrust: Optional[str] = None,
    target_release: Optional[str] = None,
    public_access: Optional[bool] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    List catalog components with optional filters.
    - primary_thrust: like "core/Software" or "useInspired/SF"
    - target_release: like "2025-07"
    - public_access: true/false
    """
    try:
        data = load_catalog_yaml(get_catalog_url(), _session)
    except Exception as exc:
        log(f"list_components error: {exc}")
        return {"error": "Failed to load catalog", "details": str(exc)}

    comps = [
        brief_component(c)
        for c in iter_components(data)
        if component_matches(
            c,
            query=None,
            primary_thrust=primary_thrust,
            target_release=target_release,
            public_access=public_access,
        )
    ]
    return {"count": len(comps), "items": comps[: max(1, min(limit, 500))]}


@mcp.tool()
def search_components(
    query: str,
    primary_thrust: Optional[str] = None,
    target_release: Optional[str] = None,
    public_access: Optional[bool] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Search across id/name/owner/description/thrust/release."""
    try:
        data = load_catalog_yaml(get_catalog_url(), _session)
    except Exception as exc:
        log(f"search_components error: {exc}")
        return {"error": "Failed to load catalog", "details": str(exc)}

    comps = [
        brief_component(c)
        for c in iter_components(data)
        if component_matches(
            c,
            query=query,
            primary_thrust=primary_thrust,
            target_release=target_release,
            public_access=public_access,
        )
    ]
    return {"count": len(comps), "items": comps[: max(1, min(limit, 200))]}


@mcp.tool()
def get_component(component_id: str) -> Dict[str, Any]:
    """Return the full YAML object for a component by exact id match."""
    try:
        data = load_catalog_yaml(get_catalog_url(), _session)
    except Exception as exc:
        log(f"get_component error: {exc}")
        return {"error": "Failed to load catalog", "details": str(exc)}

    for c in iter_components(data):
        if _norm(str(c.get("id"))) == component_id.strip():
            return {"item": c}
    return {"error": f"Component not found: {component_id}"}


@mcp.tool()
def get_component_links(component_id: str) -> Dict[str, Any]:
    """Return the key URLs/links for a component (source code, docs, training, etc.)."""
    try:
        data = load_catalog_yaml(get_catalog_url(), _session)
    except Exception as exc:
        log(f"get_component_links error: {exc}")
        return {"error": "Failed to load catalog", "details": str(exc)}

    for c in iter_components(data):
        if _norm(str(c.get("id"))) == component_id.strip():
            return {"id": component_id, "links": extract_links(c)}
    return {"error": f"Component not found: {component_id}"}


@mcp.tool()
def list_thrusts() -> Dict[str, Any]:
    """List distinct primaryThrust values present in the catalog."""
    try:
        data = load_catalog_yaml(get_catalog_url(), _session)
    except Exception as exc:
        log(f"list_thrusts error: {exc}")
        return {"error": "Failed to load catalog", "details": str(exc)}

    thrusts = sorted(
        {
            str(c.get("primaryThrust")).strip()
            for c in iter_components(data)
            if c.get("primaryThrust")
        }
    )
    return {"count": len(thrusts), "items": thrusts}


@mcp.tool()
def list_releases() -> Dict[str, Any]:
    """List distinct targetIcicleRelease values present in the catalog."""
    try:
        data = load_catalog_yaml(get_catalog_url(), _session)
    except Exception as exc:
        log(f"list_releases error: {exc}")
        return {"error": "Failed to load catalog", "details": str(exc)}

    rels = sorted(
        {
            str(c.get("targetIcicleRelease")).strip()
            for c in iter_components(data)
            if c.get("targetIcicleRelease")
        }
    )
    return {"count": len(rels), "items": rels}


# Expose each component as a "resource" you can open by URI.
@mcp.resource("icicle://component/{component_id}")
def component_resource(component_id: str) -> str:
    try:
        data = load_catalog_yaml(get_catalog_url(), _session)
    except Exception as exc:
        log(f"component_resource error: {exc}")
        return f"Failed to load catalog: {exc}"

    for c in iter_components(data):
        if _norm(str(c.get("id"))) == component_id.strip():
            # Return YAML-ish text for easy LLM context use
            return yaml.safe_dump(c, sort_keys=False, allow_unicode=True)
    return f"Component not found: {component_id}"


if __name__ == "__main__":
    # Use STDIO for IDE-style MCP hosting.
    mcp.run(transport="stdio")
