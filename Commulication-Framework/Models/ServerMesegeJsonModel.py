from pydantic import BaseModel


class LoraItem(BaseModel):
    data_type: str
    data: list
