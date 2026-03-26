import os
from functools import lru_cache

import oci

from . import __project__, __version__


def _resolved_profile_name(profile_name: str | None) -> str:
    return profile_name or os.getenv("OCI_CONFIG_PROFILE", "DEFAULT")


@lru_cache(maxsize=None)
def _build_iot_client(profile_name: str):
    config = oci.config.from_file(profile_name=profile_name)
    user_agent_name = __project__.split("oracle.", 1)[1].split("-server", 1)[0]
    config["additional_user_agent"] = f"{user_agent_name}/{__version__}"
    private_key = oci.signer.load_private_key_from_file(config["key_file"])
    with open(config["security_token_file"], "r") as token_file:
        token = token_file.read()
    signer = oci.auth.signers.SecurityTokenSigner(token, private_key)
    return oci.iot.IotClient(config, signer=signer)


def get_iot_client(profile_name: str | None = None):
    return _build_iot_client(_resolved_profile_name(profile_name))


def clear_iot_client_cache():
    _build_iot_client.cache_clear()
