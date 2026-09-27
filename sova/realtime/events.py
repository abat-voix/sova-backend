import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class RealtimeEvent:
    version: int
    id: str
    type: str
    occurred_at: str
    data: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "id": self.id,
            "type": self.type,
            "occurred_at": self.occurred_at,
            "data": self.data,
        }


def build_event(event_type: str, data: dict[str, Any]) -> RealtimeEvent:
    event = RealtimeEvent(
        version=1,
        id=str(uuid.uuid4()),
        type=event_type,
        occurred_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        data=data,
    )
    # Fail close while constructing events, not later inside the channel layer.
    json.dumps(event.as_dict())
    return event
