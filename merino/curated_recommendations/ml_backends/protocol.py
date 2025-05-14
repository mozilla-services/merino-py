"""Protocol and Pydantic models for the Local Model provider backend."""

from typing import Protocol, Dict, Any
from pydantic import BaseModel, ConfigDict


class InferredLocalModel(BaseModel):
    """Class that defines parameters on the local Firefox client for defining an interest vector from interaction
    events
    """

    model_id: str
    surface_id: str
    model_data: Dict[str, Any]

    model_config = ConfigDict(arbitrary_types_allowed=True)


class LocalModelBackend(Protocol):
    """Protocol for local model that is applied to New Tab article interactions on the client."""

    def get(self, surface_id: str | None = None) -> InferredLocalModel | None:
        """Fetch local model for the region"""
        ...
