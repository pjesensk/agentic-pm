
from pydantic import BaseModel, Field
from typing import List, Optional

class JiraTaskEnrichment(BaseModel):
    """Enriched Jira task information from AI analysis."""
    
    summary: str = Field(description="Concise task summary (max 255 chars)")
    description: str = Field(description="Detailed task description")
    priority: str = Field(description="Task priority: Highest, High, Medium, Low, Lowest")
    labels: List[str] = Field(description="List of relevant labels for the task")
    story_points: Optional[int] = Field(description="Estimated story points (1-13)", default=None)
    acceptance_criteria: str = Field(description="Clear acceptance criteria for the task")
    technical_notes: str = Field(description="Technical implementation notes or considerations")
