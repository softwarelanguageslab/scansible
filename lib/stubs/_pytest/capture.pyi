from typing import NamedTuple

class CaptureFixture:
    def readouterr(self) -> CaptureResult: ...

CaptureResult = NamedTuple('CaptureResult', [('out', str), ('err', str)])
