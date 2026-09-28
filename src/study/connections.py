"""Private connection choices. Detection suggests settings; it never selects a provider."""

from __future__ import annotations

import hashlib
import json
import os
import tomllib
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ConnectionMode = Literal["personal", "company"]


class CompanyConnection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    base_url: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9_.:/-]+$")
    effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"] | None = (
        None
    )
    api_key_env: str = Field(default="OPENAI_API_KEY", pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
    organization: str | None = Field(default=None, max_length=200)

    @field_validator("base_url")
    @classmethod
    def endpoint(cls, value):
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or any(c.isspace() for c in value)
        ):
            raise ValueError("Enter an HTTPS API base URL without credentials, query, or fragment.")
        _ = url.port
        return value.rstrip("/")

    @field_validator("organization")
    @classmethod
    def header(cls, value):
        if value and any(ord(c) < 32 or ord(c) > 126 for c in value):
            raise ValueError("The organization ID must contain printable ASCII characters.")
        return value or None

    @property
    def identity(self):
        route = json.dumps([self.base_url, self.organization], separators=(",", ":"))
        return "company-" + hashlib.sha256(route.encode()).hexdigest()[:24]

    @property
    def credential_available(self):
        return bool(os.environ.get(self.api_key_env, "").strip())


class ConnectionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selected: ConnectionMode | None = None
    company: CompanyConnection | None = None

    @model_validator(mode="after")
    def company_required(self):
        if self.selected == "company" and self.company is None:
            raise ValueError("Configure the company connection before selecting it.")
        return self

    @property
    def identity(self):
        return self.company.identity if self.selected == "company" else "personal"


class ConnectionUpdate(ConnectionSettings):
    selected: ConnectionMode


class ConnectionStatus(ConnectionSettings):
    recommendation: ConnectionMode
    reason: str
    detected: CompanyConnection | None
    credential_available: bool
    busy: bool


def detect_company(config_path: Path | None = None):
    path = config_path or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "config.toml"
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
        provider = config.get("model_providers", {}).get(config.get("model_provider"), {})
        if not provider:
            return None, "No company provider was detected. Personal ChatGPT is suggested."
        if (
            provider.get("wire_api", "responses") != "responses"
            or provider.get("requires_openai_auth")
            or not provider.get("env_key")
            or provider.get("auth")
            or provider.get("experimental_bearer_token")
            or provider.get("query_params")
        ):
            return (
                None,
                "The detected provider needs settings this company connection does not support.",
            )
        headers = {k.lower(): v for k, v in provider.get("http_headers", {}).items()}
        env_headers = {k.lower(): v for k, v in provider.get("env_http_headers", {}).items()}
        if (set(headers) | set(env_headers)) - {"openai-organization"}:
            return (
                None,
                "The detected provider uses additional headers. "
                "Configure the supported company connection explicitly.",
            )
        organization = headers.get("openai-organization")
        if "openai-organization" in env_headers:
            organization = os.environ.get(env_headers["openai-organization"])
            if not organization:
                return None, "The detected organization environment variable is unavailable."
        detected = CompanyConnection(
            base_url=provider.get("base_url", ""),
            model=config.get("model", ""),
            effort=config.get("model_reasoning_effort"),
            api_key_env=provider["env_key"],
            organization=organization,
        )
        return (
            detected,
            "A company-compatible provider is configured in Codex. "
            "Review its details before saving.",
        )
    except FileNotFoundError:
        return None, "No company provider was detected. Personal ChatGPT is suggested."
    except (OSError, ValueError, TypeError, AttributeError):
        return (
            None,
            "Local Codex settings could not be used. You can enter company settings manually.",
        )


def default_preferences(company: CompanyConnection | None = None):
    return {
        "automatic": False,
        "approach": False,
        "check": False,
        "model": company.model if company else None,
        "effort": company.effort if company else None,
    }
