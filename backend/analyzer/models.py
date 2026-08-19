from dataclasses import dataclass
from typing import Literal, Optional

LanguageName = Literal["python", "javascript", "typescript", "java"]


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    language: LanguageName
    file_path: str
    start_line: int
    end_line: int
    symbol_id: str = ""
    parent_id: Optional[str] = None
    start_column: int = 0
    end_column: int = 0
    exported: bool = False

    @property
    def id(self) -> str:
        return self.symbol_id


@dataclass(frozen=True)
class Relationship:
    source_id: str
    target_id: Optional[str]
    relationship_type: str
    language: LanguageName
    source_file: str
    target_file: Optional[str] = None
    detail: Optional[str] = None

    @property
    def source(self) -> str:
        return self.source_id

    @property
    def target(self) -> str:
        return self.target_id or ""

    @property
    def kind(self) -> str:
        return self.relationship_type

    @property
    def file_path(self) -> str:
        return self.source_file
