"""Protocol and Pydantic models for the Local Model provider backend."""

from typing import Protocol
from pydantic import BaseModel, ConfigDict


class InferredLocalModel(BaseModel):
    model_id: str
    surface_id: str
    model_data: [dict, any]

    class Config:
        arbitrary_types_allowed = True


class LocalModelBackend(Protocol):
    """Protocol for Engagement backend that the provider depends on."""

    def get(self, surface_id: str | None = None) -> InferredLocalModel | None:
        """Fetch local model for the region """
        ...
