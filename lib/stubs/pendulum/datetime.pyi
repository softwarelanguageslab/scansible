from datetime import timedelta, datetime
from .constants import ATOM as ATOM, COOKIE as COOKIE, MINUTES_PER_HOUR as MINUTES_PER_HOUR, MONTHS_PER_YEAR as MONTHS_PER_YEAR, RFC1036 as RFC1036, RFC1123 as RFC1123, RFC2822 as RFC2822, RFC822 as RFC822, RFC850 as RFC850, RSS as RSS, SATURDAY as SATURDAY, SECONDS_PER_DAY as SECONDS_PER_DAY, SECONDS_PER_MINUTE as SECONDS_PER_MINUTE, SUNDAY as SUNDAY, W3C as W3C, YEARS_PER_CENTURY as YEARS_PER_CENTURY, YEARS_PER_DECADE as YEARS_PER_DECADE
from .date import Date as Date
from .exceptions import PendulumException as PendulumException
from .helpers import add_duration as add_duration, timestamp as timestamp
from .period import Period as Period
from .time import Time as Time
from .tz import UTC as UTC
from .tz.timezone import Timezone as Timezone
from typing import Any, Optional, Union, overload

class DateTime(datetime, Date):
    @overload  # type: ignore
    def __sub__(self, other: datetime) -> Period: ...
    @overload
    def __sub__(self, other: timedelta) -> DateTime: ...
    def __rsub__(self, other: datetime) -> Period: ...
    def __add__(self, other: timedelta) -> DateTime: ...
    __radd__ = __add__
    def to_rfc3339_string(self) -> str: ...
