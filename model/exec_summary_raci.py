from pydantic import BaseModel, Field, field_validator
from typing import Set
from datetime import date
import logging

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())

class RACI(BaseModel):
    """Model that contains raci matrix"""
    name: str = Field(description="Description of timeline item.")
    team: str = Field(description="Start date for timeline item.")
    responsible: bool = Field(description="Responsible")
    accountable: bool = Field(description="Accountable")
    consulted: bool = Field(description="Consulted")
    informed: bool = Field(description="Informed")

    __hash__ = object.__hash__