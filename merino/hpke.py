"""Configuration for HPKE."""
import base64
from typing import Any, cast

import hybrid_pke

hpke_ctx: dict[str, Any] = {}


def configure_hpke() -> None:
    """Configure HPKE."""
    hpke = hybrid_pke.default()
    info = b""
    aad = b""
    secret_key_raw, public_key_raw = hpke.generate_key_pair()
    hpke_ctx.update(
        {
            "hpke": hpke,
            "info": info,
            "aad": aad,
            "secret_key_raw": secret_key_raw,
            "secret_key": base64.b64encode(secret_key_raw).decode("ascii"),
            "public_key_raw": public_key_raw,
            "public_key": base64.b64encode(public_key_raw).decode("ascii"),
        }
    )


def pub_key() -> str:
    """Return the public key."""
    return cast(str, hpke_ctx["public_key"])


def get_ctx() -> dict:
    """Return the HPKE context."""
    return hpke_ctx
