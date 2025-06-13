from __future__ import annotations

from typing import Any

import json
from pathlib import Path

import requests

from scansible.sca.constants import DEBIAN_NAME_MAPPINGS, GH_API_TOKEN
from scansible.sca.types import Vulnerability

_debian_advisories_cache: dict[str, dict[str, Any]] | None = None

class GHSACache:
    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._cache_path = Path('ghsa_cache.json')
        if self._cache_path.is_file():
            self._read_cache()

    def _read_cache(self) -> None:
        cache_text = self._cache_path.read_text()
        self._cache = json.loads(cache_text)

    def _write_cache(self) -> None:
        self._cache_path.write_text(json.dumps(self._cache))

    def _params_to_key(self, params: dict[str, str]) -> str:
        return '|'.join(f'{param}:{value}' for param, value in params.items())

    def __contains__(self, params: dict[str, str]) -> bool:
        return self._params_to_key(params) in self._cache

    def set(self, params: dict[str, str], value: Any) -> None:
        self._cache[self._params_to_key(params)] = value
        self._write_cache()

    def get(self, params: dict[str, str]) -> Any:
        return self._cache[self._params_to_key(params)]


GHSA_CACHE = GHSACache()


def find_vulnerabilities(package_name: str, package_type: str) -> list[Vulnerability]:
    if package_type == 'OS':
        return _find_debian_vulnerabilities(package_name)
    else:
        return _find_pypi_vulnerabilities(package_name)

def _get_debian_advisories() -> dict[str, dict[str, Any]]:
    global _debian_advisories_cache
    if _debian_advisories_cache is not None:
        return _debian_advisories_cache

    adv_path = Path('debian_advisories.json')
    if not adv_path.is_file():
        resp = requests.get('https://security-tracker.debian.org/tracker/data/json')
        resp.raise_for_status()
        adv_path.write_text(resp.text)

    with adv_path.open('rt') as f:
        content = json.load(f)
        _debian_advisories_cache = content
        return content


def _find_debian_vulnerabilities(package_name: str) -> list[Vulnerability]:
    debian_advisories = _get_debian_advisories()
    pkg_name_debian = DEBIAN_NAME_MAPPINGS.get(package_name, package_name)

    cves = debian_advisories.get(pkg_name_debian, debian_advisories.get('lib' + pkg_name_debian, {}))

    return [_amend_debian_cve(package_name, cve, content) for cve, content in cves.items() if not cve.startswith('TEMP-')]


def _find_pypi_vulnerabilities(package_name: str) -> list[Vulnerability]:
    ghsa_results = _search_ghsa({'ecosystem': 'pip', 'affects': package_name})
    return [_build_vuln_from_ghsa(package_name, ghsa_result) for ghsa_result in ghsa_results]


def _build_vuln_from_debian(package_name: str, cve: str, content: dict[str, Any]) -> Vulnerability:
    severity = content['releases']['bookworm']['urgency']
    if severity == 'not yet assigned':
        severity = 'unknown'
    return Vulnerability(package_name, cve, '', severity, content.get('description', ''))

def _build_vuln_from_ghsa(package_name: str, ghsa_result: dict[str, Any]) -> Vulnerability:
    return Vulnerability(package_name, ghsa_result.get('cve_id') or ghsa_result['ghsa_id'], ghsa_result.get('summary', ''), ghsa_result['severity'], ghsa_result['description'])


def _amend_debian_cve(package_name: str, cve: str, content: dict[str, Any]) -> Vulnerability:
    if not cve.startswith('CVE-'):
        return _build_vuln_from_debian(package_name, cve, content)

    ghsa_results = _search_ghsa({'cve_id': cve})
    if not ghsa_results:
        return _build_vuln_from_debian(package_name, cve, content)
    ghsa_result = ghsa_results[0]
    return _build_vuln_from_ghsa(package_name, ghsa_result)


def _search_ghsa(params: dict[str, str]) -> list[dict[str, Any]]:
    if params in GHSA_CACHE:
        return GHSA_CACHE.get(params)

    headers = {
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {GH_API_TOKEN}',
    }
    resp = requests.get('https://api.github.com/advisories', params=params, headers=headers)
    resp.raise_for_status()
    result = resp.json()
    GHSA_CACHE.set(params, result)
    return result

