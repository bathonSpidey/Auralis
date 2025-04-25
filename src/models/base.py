from pydantic import BaseModel

class BaseItem(BaseModel):
    name: str
    id: str