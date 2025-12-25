from pydantic import BaseModel, Field, field_validator
import logging

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())

class JiraContext(BaseModel):
    """Model that contains information about a Jira issue"""
    key: str = Field(description="Jira issue key")
    summary: str = Field(description="Concise jira issue summary")
    achievements: str = Field(description="What was achieved with this ticket in relation to project goals.")
    deliverable: str = Field(description="The concrete deliverable from this ticket.")
    focus: str = Field(description="The main focus area of this ticket (e.g., bug fix, new feature, backend,  frontend, etc.).")
    risks: str = Field(description="Any potential risks that could arise from or are highlighted by this ticket.")

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not value:
            raise ValueError("You must provide key. ")
        return value 
    @field_validator("summary")
    @classmethod
    def validate_key(cls, value: str) -> str:
        log.debug (f"Validating field summary with cls {cls} and value {value}")
        if not value:
            raise ValueError("You must provide summary")
        return value 
    @field_validator("achievements")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not value:
            raise ValueError("You must provide achievements")
        return value 
    @field_validator("deliverable")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not value:
            raise ValueError("You must provide deliverable")
        return value 
    @field_validator("focus")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not value:
            raise ValueError("You must provide focus")
        return value 
    @field_validator("risks")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not value:
            raise ValueError("You must provide risks")
        return value 