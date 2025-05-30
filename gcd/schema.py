from __future__ import annotations

from pydantic import BaseModel


class CodeElement(BaseModel):
    name: str
    type: str  # 'function' or 'class'
    line_number: int
    file_path: str
    docstring: str = ""
    signature: str = ""
    code: str = ""
    score: float = 0.0
