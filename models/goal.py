from pydantic import BaseModel


class Goal(BaseModel):
    priority: int
    name: str
    description: str
    