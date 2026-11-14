"""Request schemas for safe historical-reading administration."""

from pydantic import BaseModel, Field


class ResetReadingsRequest(BaseModel):
    """Explicit acknowledgement required before removing reading history."""

    confirm: bool = Field(description="Must be true to delete monitoring readings.")
