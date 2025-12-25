from pydantic import BaseModel, Field, field_validator
from typing import Set
from datetime import date
import logging
from model.exec_summary_prereq import Prerequisities
from model.exec_summary_timeline import Timeline
from model.exec_summary_raci import RACI

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())

class ExecSummary(BaseModel):
    """Model that contains executive summary data to be displayed in confluence"""
    confluence_id: int = Field(description="ID of confluence page to update")
    name: str = Field(description="Name of the project executive summary is made for.")
    description: str = Field(description="Description what this project is solving.")
    status: str = Field(description="Overall status of project either green, yellow or red")
    statusdesc: str = Field(description="Description of the status of the project.")
    duedate: date = Field(description="Estimated due date for specific project.")
    achievements: Set[str] = Field(description="List of achievements")
    deliverables: Set[str] = Field(description="List of deliverables")
    prerequisites: Set[Prerequisities] = Field(description="List of prerequisities with name, accountable and due date")
    focus: Set[str] = Field(description="List of items to focus on")
    next_steps: Set[str] = Field(description="List of next steps")
    risks: Set[str] = Field(description="List of risks")
    decisions: Set[str] = Field(description="List of decisions to take")
    timeline: Set[Timeline] = Field(description="List of timeline items")
    links: Set[str] = Field(description="List of links")
    raci: Set[RACI] = Field(description="List of RACI items")

    __hash__ = object.__hash__
