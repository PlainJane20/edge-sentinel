"""Static bearer-token authentication for devices and operators.

Tokens come from the environment:

    EDGE_DEVICE_TOKENS    token1,token2             (devices may POST /readings)
    EDGE_OPERATOR_TOKENS  alice:tokenA,bob:tokenB   (token -> operator identity)

If neither variable is set, authentication is DISABLED (local demo mode).
These are static shared secrets: no rotation, no expiry, no TLS here. This is
not an identity system; it only stops identity being typed into a request body.
"""
from __future__ import annotations

import hmac
import logging
import os
from dataclasses import dataclass, field

from fastapi import HTTPException, Request

log = logging.getLogger("edge-sentinel")

ANONYMOUS = "anonymous"


def _match(token: str, candidates) -> bool:
    """Constant-time check of `token` against every candidate (no early exit)."""
    ok = False
    for cand in candidates:
        ok |= hmac.compare_digest(token.encode(), cand.encode())
    return ok


@dataclass
class AuthConfig:
    device_tokens: tuple[str, ...] = ()
    operator_tokens: dict[str, str] = field(default_factory=dict)  # token -> identity

    @property
    def enabled(self) -> bool:
        return bool(self.device_tokens or self.operator_tokens)

    @classmethod
    def from_env(cls, env=None) -> "AuthConfig":
        env = os.environ if env is None else env
        devices = tuple(t.strip() for t in env.get("EDGE_DEVICE_TOKENS", "").split(",")
                        if t.strip())
        operators: dict[str, str] = {}
        for pair in env.get("EDGE_OPERATOR_TOKENS", "").split(","):
            pair = pair.strip()
            if not pair:
                continue
            name, sep, token = pair.partition(":")
            if not sep or not name.strip() or not token.strip():
                raise ValueError("EDGE_OPERATOR_TOKENS must look like alice:tokenA,bob:tokenB")
            operators[token.strip()] = name.strip()
        return cls(devices, operators)

    def warn_if_disabled(self) -> None:
        if not self.enabled:
            log.warning("*" * 70)
            log.warning("AUTHENTICATION IS DISABLED: EDGE_DEVICE_TOKENS and "
                        "EDGE_OPERATOR_TOKENS are unset. Anyone who can reach this "
                        "API can ingest readings and act as any operator.")
            log.warning("*" * 70)
        elif not self.device_tokens or not self.operator_tokens:
            log.warning("Auth is enabled but only partly configured; the endpoints "
                        "with no tokens configured reject every request.")

    # -- lookups -----------------------------------------------------------
    def operator_for(self, token: str) -> str | None:
        found = None
        for tok, name in self.operator_tokens.items():
            if hmac.compare_digest(token.encode(), tok.encode()):
                found = name
        return found

    def is_device(self, token: str) -> bool:
        return _match(token, self.device_tokens)


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _unauthorized() -> HTTPException:
    return HTTPException(401, "missing or invalid bearer token",
                         headers={"WWW-Authenticate": "Bearer"})


def make_dependencies(cfg: AuthConfig):
    """Build FastAPI dependencies bound to `cfg`."""

    def require_device(request: Request) -> str:
        if not cfg.enabled:
            return "device:unauthenticated"
        token = bearer_token(request)
        if token is None:
            raise _unauthorized()
        if cfg.is_device(token):
            return "device"
        if cfg.operator_for(token) is not None:
            raise HTTPException(403, "operator tokens cannot ingest readings")
        raise _unauthorized()

    def require_operator(request: Request) -> str:
        """Return the authenticated operator identity (from the token only)."""
        if not cfg.enabled:
            # Demo mode: identity is self-declared via header, defaulting to anonymous.
            return request.headers.get("x-operator", ANONYMOUS).strip() or ANONYMOUS
        token = bearer_token(request)
        if token is None:
            raise _unauthorized()
        who = cfg.operator_for(token)
        if who is not None:
            return who
        if cfg.is_device(token):
            raise HTTPException(403, "device tokens cannot use operator endpoints")
        raise _unauthorized()

    return require_device, require_operator
