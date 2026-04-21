from __future__ import annotations

from enum import Enum


class SupportLevel(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    PLANNED = "planned"


class RuntimePointerMode(str, Enum):
    DIRECTORY = "directory"
    POINTER_FILE = "pointer_file"

