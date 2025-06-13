from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from scansible.sca import CONSOLE
from scansible.sca.constants import DEBIAN_NAME_MAPPINGS
from scansible.sca.types import Vulnerability

CACHE_PATH = Path("cache")

_debian_advisories_cache: dict[str, dict[str, Any]] | None = None


class EcosystemsCache:
    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._cache_path = CACHE_PATH / "ecosystems_cache.json"
        if self._cache_path.is_file():
            self._read_cache()

    def _read_cache(self) -> None:
        cache_text = self._cache_path.read_text()
        self._cache = json.loads(cache_text)

    def _write_cache(self) -> None:
        self._cache_path.write_text(json.dumps(self._cache))

    def _params_to_key(self, ecosystem: str, package: str) -> str:
        return f"{ecosystem}:{package}"

    def __contains__(self, key: tuple[str, str]) -> bool:
        return self._params_to_key(*key) in self._cache

    def set(self, ecosystem: str, package: str, value: Any) -> None:
        self._cache[self._params_to_key(ecosystem, package)] = value
        self._write_cache()

    def get(self, ecosystem: str, package: str) -> Any:
        return self._cache[self._params_to_key(ecosystem, package)]


ECOSYSTEMS_CACHE = EcosystemsCache()


def find_vulnerabilities(package_name: str, package_type: str) -> list[Vulnerability]:
    if package_type == "OS":
        return _find_debian_vulnerabilities(package_name)
    else:
        return _find_pypi_vulnerabilities(package_name)


def _get_debian_advisories() -> dict[str, dict[str, Any]]:
    global _debian_advisories_cache
    if _debian_advisories_cache is not None:
        return _debian_advisories_cache

    adv_path = CACHE_PATH / "debian_advisories.json"
    if not adv_path.is_file():
        resp = requests.get("https://security-tracker.debian.org/tracker/data/json")
        resp.raise_for_status()
        adv_path.write_text(resp.text)

    with adv_path.open("rt") as f:
        content = json.load(f)
        _debian_advisories_cache = content
        return content


def _find_debian_vulnerabilities(package_name: str) -> list[Vulnerability]:
    debian_advisories = _get_debian_advisories()
    pkg_name_debian = DEBIAN_NAME_MAPPINGS.get(package_name, package_name)

    cves = debian_advisories.get(
        pkg_name_debian, debian_advisories.get("lib" + pkg_name_debian, {})
    )

    return [
        _build_vuln_from_debian(package_name, cve, content)
        for cve, content in cves.items()
        if not cve.startswith("TEMP-")
    ]


def _find_pypi_vulnerabilities(package_name: str) -> list[Vulnerability]:
    package_meta = _search_ecosystems(ecosystem="pypi.org", package=package_name)
    if package_meta is None:
        CONSOLE.print(
            f"[bold yellow]WARNING:[/bold yellow] Could not resolve package {package_name}"
        )
        return []
    return [
        _build_vuln_from_ecosystems(package_name, adv)
        for adv in package_meta.get("advisories", [])
    ]


def _build_vuln_from_debian(
    package_name: str, cve: str, content: dict[str, Any]
) -> Vulnerability:
    severity = content["releases"]["bookworm"]["urgency"]
    if severity == "not yet assigned":
        severity = "unknown"
    return Vulnerability(
        package_name,
        cve,
        content.get("description", "")[:100],
        severity,
        content.get("description", ""),
    )


def _build_vuln_from_ecosystems(
    package_name: str, adv: dict[str, Any]
) -> Vulnerability:
    return Vulnerability(
        package_name,
        _get_ecosystems_id(adv),
        adv.get("title", ""),
        adv["severity"].lower(),
        adv["description"],
    )


def _get_ecosystems_id(adv: dict[str, Any]) -> str:
    for ident in adv["identifiers"]:
        if ident.startswith("CVE-"):
            return ident

    return adv["identifiers"][0]


def _search_ecosystems(ecosystem: str, package: str) -> dict[str, Any] | None:
    if (ecosystem, package) in ECOSYSTEMS_CACHE:
        return ECOSYSTEMS_CACHE.get(ecosystem, package)

    resp = requests.get(
        f"https://packages.ecosyste.ms/api/v1/registries/{ecosystem}/packages/{package}"
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    result = resp.json()
    ECOSYSTEMS_CACHE.set(ecosystem, package, result)
    return result
