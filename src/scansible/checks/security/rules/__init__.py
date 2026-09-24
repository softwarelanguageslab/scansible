from __future__ import annotations

from typing import TYPE_CHECKING

from .admin_by_default import AdminByDefaultRule
from .disabled_integrity_check import DisabledIntegrityCheckRule
from .empty_password import EmptyPasswordRule
from .hardcoded_secret import HardcodedSecretRule
from .http_without_ssl_tls import HTTPWithoutSSLTLSRule
from .missing_integrity_check import MissingIntegrityCheckRule
from .unrestricted_ip_address import UnrestrictedIPAddressRule
from .weak_crypto import WeakCryptoAlgorithmRule

if TYPE_CHECKING:
    from .base import GraphDBRule as GraphDBRule


def get_all_rules() -> list[GraphDBRule]:
    return [
        AdminByDefaultRule(),
        EmptyPasswordRule(),
        HardcodedSecretRule(),
        HTTPWithoutSSLTLSRule(),
        MissingIntegrityCheckRule(),
        DisabledIntegrityCheckRule(),
        UnrestrictedIPAddressRule(),
        WeakCryptoAlgorithmRule(),
    ]
