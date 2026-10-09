"""Bounded, authenticated OCI IoT read-only access for shared HTTP mode."""

from __future__ import annotations

import configparser
import contextvars
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

import oci
import jwt
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult
from oracle_mcp_common import AuthOptions, build_auth_context

from . import __project__, __version__

_CALLER: contextvars.ContextVar[str | None] = contextvars.ContextVar("iot_readonly_caller", default=None)
_REGION = re.compile(r"[a-z0-9-]{3,64}\Z")
_ID = re.compile(r"[A-Za-z0-9._:-]{1,512}\Z")
_FIELDS = {
    "version", "region", "profile", "config_file", "auth_tenancy_id",
    "credential_generation", "iot_domain_id", "iot_domain_group_id",
    "compartment_id", "model_ids", "allowed_callers",
}
ENABLED_TOOLS = ["get_digital_twin_model", "get_iot_domain"]


@dataclass(frozen=True)
class ReadPolicy:
    region: str
    profile: str
    config_file: Path
    auth_tenancy_id: str
    credential_generation: str
    iot_domain_id: str
    iot_domain_group_id: str
    compartment_id: str
    model_ids: frozenset[str]
    allowed_callers: frozenset[str]


def _read_private(path: Path, *, limit: int = 65536) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.getuid() or info.st_size > limit):
            raise ValueError
        with os.fdopen(fd, "rb", closefd=False) as private_file:
            content = private_file.read(limit + 1)
        if len(content) > limit:
            raise ValueError
        return content
    finally:
        os.close(fd)


def load_read_policy(path: Path) -> ReadPolicy:
    """Load a private immutable allowlist and verify its referenced config file."""
    try:
        policy_bytes = _read_private(path)
        if len(policy_bytes) > 65536:
            raise ValueError
        raw = json.loads(policy_bytes.decode("utf-8"))
        if (not isinstance(raw, dict) or set(raw) != _FIELDS
                or isinstance(raw["version"], bool) or raw["version"] != 1):
            raise ValueError
        scalar_names = _FIELDS - {"version", "model_ids", "allowed_callers"}
        if any(not isinstance(raw[key], str) or not raw[key].strip() for key in scalar_names):
            raise ValueError
        if _REGION.fullmatch(raw["region"]) is None:
            raise ValueError
        ids = (raw["auth_tenancy_id"], raw["iot_domain_id"], raw["iot_domain_group_id"], raw["compartment_id"])
        if any(_ID.fullmatch(value) is None or value in {".", ".."} for value in ids):
            raise ValueError
        if (not isinstance(raw["credential_generation"], str)
                or len(raw["credential_generation"]) > 128
                or not isinstance(raw["profile"], str) or not raw["profile"].strip()):
            raise ValueError
        if (not isinstance(raw["model_ids"], list) or len(raw["model_ids"]) != 1
                or any(not isinstance(value, str) or _ID.fullmatch(value) is None
                       or value in {".", ".."} for value in raw["model_ids"])
                or len(set(raw["model_ids"])) != len(raw["model_ids"])):
            raise ValueError
        if (not isinstance(raw["allowed_callers"], list) or len(raw["allowed_callers"]) != 2
                or any(not isinstance(value, str) or not value.strip() for value in raw["allowed_callers"])
                or len(set(raw["allowed_callers"])) != len(raw["allowed_callers"])):
            raise ValueError
        config_path = Path(raw["config_file"])
        config_bytes = _read_private(config_path)
        if len(config_bytes) > 65536:
            raise ValueError
        config = configparser.RawConfigParser()
        config.read_string(config_bytes.decode("utf-8"))
        if raw["profile"] not in config:
            raise ValueError
        token_file = config[raw["profile"]].get("security_token_file")
        if not token_file:
            raise ValueError
        token_path = Path(token_file)
        if not token_path.is_absolute():
            token_path = config_path.parent / token_path
        _read_private(token_path, limit=1024 * 1024)
        key_file = config[raw["profile"]].get("key_file")
        if not key_file:
            raise ValueError
        key_path = Path(key_file)
        if not key_path.is_absolute():
            key_path = config_path.parent / key_path
        _read_private(key_path, limit=1024 * 1024)
        return ReadPolicy(
            region=raw["region"], profile=raw["profile"], config_file=config_path,
            auth_tenancy_id=raw["auth_tenancy_id"], credential_generation=raw["credential_generation"],
            iot_domain_id=raw["iot_domain_id"], iot_domain_group_id=raw["iot_domain_group_id"],
            compartment_id=raw["compartment_id"], model_ids=frozenset(raw["model_ids"]),
            allowed_callers=frozenset(raw["allowed_callers"]),
        )
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, configparser.Error, json.JSONDecodeError):
        raise RuntimeError("shared_readonly_configuration_invalid") from None


class RestrictedIoTReader:
    """One process credential generation; only guarded SDK GETs are possible."""

    def __init__(self, policy: ReadPolicy):
        self.policy = policy
        self._client = None
        self._token_expiry = None
        self._host = f"iot.{policy.region}.oci.oraclecloud.com"

    def _ensure_client(self):
        if self._client is None:
            options = AuthOptions(
                auth_type="security_token", config_file=str(self.policy.config_file),
                profile_name=self.policy.profile, region=self.policy.region,
            )
            auth = build_auth_context(options)
            if auth.tenancy_id != self.policy.auth_tenancy_id or auth.region != self.policy.region:
                raise ToolError("Read-only OCI identity does not match policy.")
            token = getattr(auth.signer, "api_key", "")
            if not isinstance(token, str) or not token.startswith("ST$"):
                raise ToolError("Read-only OCI security token is unavailable.")
            claims = jwt.decode(token[3:], options={"verify_signature": False})
            self._token_expiry = datetime.fromtimestamp(claims["exp"], UTC)
            config = {**auth.config, "additional_user_agent": derived_user_agent()}
            client = oci.iot.IotClient(
                config, signer=auth.signer, retry_strategy=oci.retry.NoneRetryStrategy(),
                timeout=(10, 20),
            )
            session = client.base_client.session
            session.trust_env = False
            session.verify = True
            original_request = session.request
            allowed_paths = {
                f"/20250531/iotDomains/{quote(self.policy.iot_domain_id, safe='')}",
                *(f"/20250531/digitalTwinModels/{quote(model_id, safe='')}"
                  for model_id in self.policy.model_ids),
            }

            def guarded_request(method, url, **kwargs):
                parsed = urlsplit(url)
                valid = (
                    parsed.scheme == "https" and parsed.hostname == self._host
                    and parsed.port in (None, 443) and parsed.username is None and parsed.password is None
                    and not parsed.query and not parsed.fragment and method.upper() == "GET"
                    and parsed.path in allowed_paths
                )
                if not valid:
                    raise RuntimeError("readonly_request_rejected")
                kwargs["allow_redirects"] = False
                kwargs["timeout"] = (10, 20)
                return original_request(method, url, **kwargs)

            session.request = guarded_request
            self._client = client
        if self._token_expiry is None or self._token_expiry <= datetime.now(UTC):
            raise ToolError("Read-only OCI credential has expired; restart after reauthentication.")
        return self._client

    def get_domain(self, iot_domain_id: str):
        if iot_domain_id != self.policy.iot_domain_id:
            raise ToolError("Requested resource is outside the read-only policy.")
        try:
            response = self._ensure_client().get_iot_domain(
                iot_domain_id, retry_strategy=oci.retry.NoneRetryStrategy(),
            )
            data = response.data
            if (getattr(data, "id", None) != self.policy.iot_domain_id
                    or getattr(data, "iot_domain_group_id", None) != self.policy.iot_domain_group_id
                    or getattr(data, "compartment_id", None) != self.policy.compartment_id):
                raise ToolError("OCI response did not match the read-only policy.")
            return oci.util.to_dict(data)
        except ToolError:
            raise
        except Exception:
            raise ToolError("Read-only OCI request failed.") from None

    def get_model(self, model_id: str):
        if model_id not in self.policy.model_ids:
            raise ToolError("Requested resource is outside the read-only policy.")
        try:
            response = self._ensure_client().get_digital_twin_model(
                model_id, retry_strategy=oci.retry.NoneRetryStrategy(),
            )
            data = response.data
            if (getattr(data, "id", None) != model_id
                    or getattr(data, "iot_domain_id", None) != self.policy.iot_domain_id):
                raise ToolError("OCI response did not match the read-only policy.")
            return oci.util.to_dict(data)
        except ToolError:
            raise
        except Exception:
            raise ToolError("Read-only OCI request failed.") from None


class SharedReadOnlyMiddleware(Middleware):
    """Dispatch only two strictly shaped calls into the bounded reader."""

    def __init__(self, policy: ReadPolicy):
        self.policy = policy
        self.reader = RestrictedIoTReader(policy)

    async def on_call_tool(self, context: MiddlewareContext, call_next: CallNext):
        caller = _CALLER.get()
        if caller is None or caller not in self.policy.allowed_callers:
            raise ToolError("Caller is not authorized for read-only OCI access.")
        name = getattr(context.message, "name", None)
        args = getattr(context.message, "arguments", None)
        if not isinstance(args, dict) or set(args) != ({"iot_domain_id"} if name == "get_iot_domain" else {"digital_twin_model_id"}):
            raise ToolError("Tool arguments are outside the read-only policy.")
        if name == "get_iot_domain":
            value = args["iot_domain_id"]
            if not isinstance(value, str) or value != self.policy.iot_domain_id:
                raise ToolError("Requested resource is outside the read-only policy.")
            return ToolResult(structured_content=self.reader.get_domain(value))
        if name == "get_digital_twin_model":
            value = args["digital_twin_model_id"]
            if not isinstance(value, str) or value not in self.policy.model_ids:
                raise ToolError("Requested resource is outside the read-only policy.")
            return ToolResult(structured_content=self.reader.get_model(value))
        raise ToolError("Tool is not enabled in shared read-only mode.")


def derived_user_agent() -> str:
    return f"{__project__.split('oracle.', 1)[1].removesuffix('-server')}/{__version__}"

