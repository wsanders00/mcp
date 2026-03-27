from .tool_models import DomainContextModel


def _first_label(host: str) -> str:
    return host.split(".", 1)[0]


def _parse_region(host: str) -> str:
    return host.split(".iot.", 1)[1].split(".oci.oraclecloud.com", 1)[0]


def derive_domain_context(*, iot_domain: dict, iot_domain_group: dict) -> DomainContextModel:
    device_region = _parse_region(iot_domain["device_host"])
    data_region = _parse_region(iot_domain_group["data_host"])
    if device_region != data_region:
        raise ValueError("device_host and data_host must share the same OCI region.")

    return DomainContextModel(
        iot_domain_id=iot_domain["id"],
        iot_domain_display_name=iot_domain.get("name"),
        iot_domain_group_id=iot_domain_group["id"],
        iot_domain_group_display_name=iot_domain_group.get("name"),
        device_host=iot_domain["device_host"],
        data_host=iot_domain_group["data_host"],
        domain_short_id=_first_label(iot_domain["device_host"]),
        domain_group_short_id=_first_label(iot_domain_group["data_host"]),
        region=device_region,
        db_token_scope=iot_domain_group.get("db_token_scope"),
        db_allowed_identity_domain_host=iot_domain.get("db_allowed_identity_domain_host"),
    )
