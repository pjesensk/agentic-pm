from pydantic import BaseModel, Field, field_validator
from typing import Set
from datetime import date
import logging

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())

class Prerequisities(BaseModel):
    """Model that contains prerequisities structure"""
    name: str = Field(description="Name of the prerequisity.")
    desc: str = Field(description="Description of the prerequisity.")
    accountable: str = Field(description="Email of the accountable for this prerequisity.")
    duedate: date = Field(description="Due date for this prerequisity to be done.")
    status: str = Field(description="Status progress for this prerequisity.")

    __hash__ = object.__hash__