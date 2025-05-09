from pydantic import BaseModel, Field
from typing import List, Dict


class Prompt(BaseModel):
    messages: List[Dict] = Field(default_factory=list)
    tools: List[Dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict) 