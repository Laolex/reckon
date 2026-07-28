"""Execution model (§4.8).

`path_digest` is the field that carries the OPA finding. Replay soundness is not
compositional: two runs with identical component versions can differ because one
resolved its policy from a place the other did not. The path digest covers the
resolution sources actually used, so those two runs hash differently.
"""

import hashlib
import platform
from importlib.metadata import distributions

SDK_VERSION = "0.1.0"

_deps_digest_cache: str | None = None


def runtime() -> str:
    return f"python{platform.python_version()}"


def deps_digest() -> str:
    """Digest of the resolved dependency set. Stable within a process."""
    global _deps_digest_cache
    if _deps_digest_cache is None:
        installed = sorted(
            f"{dist.metadata['Name']}=={dist.version}"
            for dist in distributions()
            if dist.metadata["Name"]
        )
        digest = hashlib.sha256("\n".join(installed).encode("utf-8"))
        _deps_digest_cache = f"sha256:{digest.hexdigest()}"
    return _deps_digest_cache


def path_digest(resolution_sources: list[str], emitter: str) -> str:
    """Digest over the whole execution path, not a composition of component versions.

    `resolution_sources` are the `provenance:source` pairs that actually resolved a
    policy in this decision. Two decisions with identical dependencies but different
    resolution regimes — the OPA bundle case versus the Data API case — produce
    different path digests, which is precisely what the bundle revision failed to do.
    """
    material = "\n".join(
        [deps_digest(), runtime(), SDK_VERSION, emitter, *sorted(resolution_sources)]
    )
    return f"sha256:{hashlib.sha256(material.encode('utf-8')).hexdigest()}"
