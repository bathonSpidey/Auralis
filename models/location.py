from pydantic import BaseModel, Field


class Location(BaseModel):
    country: str
    city: str = Field(..., alias="name")
    lat: float
    lon: float
