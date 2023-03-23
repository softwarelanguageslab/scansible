from __future__ import annotations

from typing import Any, Optional, Union, overload

from datetime import datetime, timedelta

from .constants import ATOM as ATOM
from .constants import COOKIE as COOKIE
from .constants import MINUTES_PER_HOUR as MINUTES_PER_HOUR
from .constants import MONTHS_PER_YEAR as MONTHS_PER_YEAR
from .constants import RFC822 as RFC822
from .constants import RFC850 as RFC850
from .constants import RFC1036 as RFC1036
from .constants import RFC1123 as RFC1123
from .constants import RFC2822 as RFC2822
from .constants import RSS as RSS
from .constants import SATURDAY as SATURDAY
from .constants import SECONDS_PER_DAY as SECONDS_PER_DAY
from .constants import SECONDS_PER_MINUTE as SECONDS_PER_MINUTE
from .constants import SUNDAY as SUNDAY
from .constants import W3C as W3C
from .constants import YEARS_PER_CENTURY as YEARS_PER_CENTURY
from .constants import YEARS_PER_DECADE as YEARS_PER_DECADE
from .date import Date as Date
from .exceptions import PendulumException as PendulumException
from .helpers import add_duration as add_duration
from .helpers import timestamp as timestamp
from .period import Period as Period
from .time import Time as Time
from .tz import UTC as UTC
from .tz.timezone import Timezone as Timezone

class DateTime(datetime, Date):
    @overload  # type: ignore
    def __sub__(self, other: datetime) -> Period: ...
    @overload
    def __sub__(self, other: timedelta) -> DateTime: ...
    def __rsub__(self, other: datetime) -> Period: ...
    def __add__(self, other: timedelta) -> DateTime: ...
    __radd__ = __add__
    def to_rfc3339_string(self) -> str: ...
