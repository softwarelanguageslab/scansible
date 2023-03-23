from __future__ import annotations

from typing import Optional, Union

import datetime as _datetime

from .constants import DAYS_PER_WEEK as DAYS_PER_WEEK
from .constants import FRIDAY as FRIDAY
from .constants import HOURS_PER_DAY as HOURS_PER_DAY
from .constants import MINUTES_PER_HOUR as MINUTES_PER_HOUR
from .constants import MONTHS_PER_YEAR as MONTHS_PER_YEAR
from .constants import SATURDAY as SATURDAY
from .constants import SECONDS_PER_DAY as SECONDS_PER_DAY
from .constants import SECONDS_PER_HOUR as SECONDS_PER_HOUR
from .constants import SECONDS_PER_MINUTE as SECONDS_PER_MINUTE
from .constants import THURSDAY as THURSDAY
from .constants import TUESDAY as TUESDAY
from .constants import WEDNESDAY as WEDNESDAY
from .constants import WEEKS_PER_YEAR as WEEKS_PER_YEAR
from .constants import YEARS_PER_CENTURY as YEARS_PER_CENTURY
from .constants import YEARS_PER_DECADE as YEARS_PER_DECADE
from .date import Date
from .datetime import DateTime as DateTime
from .duration import Duration as Duration
from .helpers import format_diff as format_diff
from .helpers import get_locale as get_locale
from .helpers import set_locale as set_locale
from .helpers import set_test_now as set_test_now
from .helpers import test as test
from .helpers import week_ends_at as week_ends_at
from .helpers import week_starts_at as week_starts_at
from .parser import parse as parse
from .period import Period
from .time import Time
from .tz import PRE_TRANSITION as PRE_TRANSITION
from .tz import TRANSITION_ERROR as TRANSITION_ERROR
from .tz import set_local_timezone as set_local_timezone
from .tz import test_local_timezone as test_local_timezone
from .tz import timezones as timezones
from .tz.timezone import Timezone as _Timezone

def datetime(
    year: int,
    month: int,
    day: int,
    hour: int = ...,
    minute: int = ...,
    second: int = ...,
    microsecond: int = ...,
    tz: Optional[Union[str, float, _Timezone]] = ...,
    dst_rule: str = ...,
) -> DateTime: ...
def local(
    year: int,
    month: int,
    day: int,
    hour: int = ...,
    minute: int = ...,
    second: int = ...,
    microsecond: int = ...,
) -> DateTime: ...
def naive(
    year: int,
    month: int,
    day: int,
    hour: int = ...,
    minute: int = ...,
    second: int = ...,
    microsecond: int = ...,
) -> DateTime: ...
def date(year: int, month: int, day: int) -> Date: ...
def time(
    hour: int, minute: int = ..., second: int = ..., microsecond: int = ...
) -> Time: ...
def instance(
    dt: _datetime.datetime, tz: Optional[Union[str, _Timezone]] = ...
) -> DateTime: ...
def now(tz: Optional[Union[str, _Timezone]] = ...) -> DateTime: ...
def today(tz: Union[str, _Timezone] = ...) -> DateTime: ...
def tomorrow(tz: Union[str, _Timezone] = ...) -> DateTime: ...
def yesterday(tz: Union[str, _Timezone] = ...) -> DateTime: ...
def from_format(
    string: str, fmt: str, tz: Union[str, _Timezone] = ..., locale: Optional[str] = ...
) -> DateTime: ...
def from_timestamp(
    timestamp: Union[int, float], tz: Union[str, _Timezone] = ...
) -> DateTime: ...
def duration(
    days: float = ...,
    seconds: float = ...,
    microseconds: float = ...,
    milliseconds: float = ...,
    minutes: float = ...,
    hours: float = ...,
    weeks: float = ...,
    years: float = ...,
    months: float = ...,
) -> Duration: ...
def period(start: DateTime, end: DateTime, absolute: bool = ...) -> Period: ...
