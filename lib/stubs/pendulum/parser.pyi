import typing
from .datetime import DateTime
from .tz import UTC as UTC

def parse(text: str, **options: typing.Any) -> typing.Any: ...
