from pydantic import BaseModel

class Device(BaseModel):
    id: str
    is_active: bool
    name: str
    type: str
    volume_percent: int