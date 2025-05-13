from pydantic import BaseModel, Field


class Weather(BaseModel):
    forecast: str = Field(..., alias="main")
    description: str
