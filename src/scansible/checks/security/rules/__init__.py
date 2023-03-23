from __future__ import annotations

from .admin_by_default import AdminByDefaultRule
from .base import Rule
from .base import RuleResult as RuleResult
from .empty_password import EmptyPasswordRule
from .hardcoded_secret import HardcodedSecretRule
from .http_without_ssl_tls import HTTPWithoutSSLTLSRule
from .missing_integrity_check import MissingIntegrityCheckRule
from .unrestricted_ip_address import UnrestrictedIPAddressRule
from .weak_crypto import WeakCryptoAlgorithmRule


def get_all_rules() -> list[Rule]:
    return [
        AdminByDefaultRule(),
        EmptyPasswordRule(),
        HardcodedSecretRule(),
        HTTPWithoutSSLTLSRule(),
        MissingIntegrityCheckRule(),
        UnrestrictedIPAddressRule(),
        WeakCryptoAlgorithmRule(),
    ]
