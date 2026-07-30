from collections.abc import Callable

def behaves_like(
    shared_behavior: Callable[[], None],
) -> Callable[[Callable[[], None]], None]: ...
