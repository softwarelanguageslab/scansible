from __future__ import annotations

from typing import Any

class AnsibleError(Exception):
    def __init__(
        self,
        message: str = ...,
        obj: Any = ...,
        show_content: bool = ...,
        suppress_extended_error: bool = ...,
        orig_exc: BaseException | None = ...,
    ) -> None: ...

class AnsibleAssertionError(AnsibleError, AssertionError): ...
class AnsibleOptionsError(AnsibleError): ...
class AnsibleParserError(AnsibleError): ...
class AnsibleInternalError(AnsibleError): ...
class AnsibleRuntimeError(AnsibleError): ...
class AnsibleModuleError(AnsibleRuntimeError): ...
class AnsibleConnectionFailure(AnsibleRuntimeError): ...
class AnsibleAuthenticationFailure(AnsibleConnectionFailure): ...
class AnsibleCallbackError(AnsibleRuntimeError): ...
class AnsibleTemplateError(AnsibleRuntimeError): ...
class AnsibleFilterError(AnsibleTemplateError): ...
class AnsibleLookupError(AnsibleTemplateError): ...
class AnsibleUndefinedVariable(AnsibleTemplateError): ...
class AnsibleFileNotFound(AnsibleRuntimeError): ...
class AnsibleAction(AnsibleRuntimeError): ...
class AnsibleActionSkip(AnsibleAction): ...
class AnsibleActionFail(AnsibleAction): ...
class _AnsibleActionDone(AnsibleAction): ...
