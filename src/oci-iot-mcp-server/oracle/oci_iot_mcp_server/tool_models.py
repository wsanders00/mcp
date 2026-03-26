from pydantic import BaseModel, Field


class ToolErrorPayload(BaseModel):
    code: str
    message: str
    resource_type: str | None = None
    retry_hint: str | None = None
    details: dict = Field(default_factory=dict)


def success_result(data: dict) -> dict:
    return {"ok": True, "data": data}
