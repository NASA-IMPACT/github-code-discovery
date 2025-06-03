from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator


class CodeElement(BaseModel):
    name: str
    type: Literal["function", "class"]
    line_number: int
    file_path: str
    docstring: str = ""
    signature: str = ""
    code: str = ""
    score: float = 0.0

    @field_validator("score")
    @classmethod
    def convert_score_to_float(cls, v):
        """Convert any numeric type to Python float."""
        return float(v)
