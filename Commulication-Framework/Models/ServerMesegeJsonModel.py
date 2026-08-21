from pydantic import BaseModel
from typing import Optional


class LoraItem(BaseModel):
    data_type: str
    data: list
    received_at: Optional[float] = None


class MissionStateItem(BaseModel):
    mission_id: str
    phase: str
    active_source: Optional[str] = None
    airborne: Optional[bool] = None
