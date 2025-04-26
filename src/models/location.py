from pydantic import BaseModel

class Location(BaseModel):
    country: str
    city: str
    lat: float
    lon: float