from pydantic import BaseModel, Field, field_validator
from typing import Set
from datetime import date
import logging

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())

class Timeline(BaseModel):
    """Model that contains timeline structure"""
    description: str = Field(description="Description of timeline item.")
    start_date: date = Field(description="Start date for timeline item.")
    end_date: date = Field(description="End date for timeline item.")
    metadata: Set[dict] = Field(description="Set of metadata objects.")
    context: Set[dict] = Field(description="Set of context objects.")

    __hash__ = object.__hash__