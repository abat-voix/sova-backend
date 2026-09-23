from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass
class ActionFeatureResult:
    target_type: str
    target_id: UUID
    data: dict


class ActionFeatureHandler(Protocol):
    code: str

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult: ...
