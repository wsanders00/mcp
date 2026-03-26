from .tool_models import ToolErrorPayload


def ambiguity_error(
    *,
    resource_type: str,
    message: str,
    input_payload: dict,
    candidates: list[dict],
) -> dict:
    return {
        "ok": False,
        "error": ToolErrorPayload(
            code="ambiguous_identifier",
            message=message,
            resource_type=resource_type,
            retry_hint="Retry with the OCID of the intended resource.",
            details={"input": input_payload, "candidates": candidates},
        ).model_dump(exclude_none=True),
    }
