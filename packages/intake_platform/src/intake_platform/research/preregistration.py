"""INT-231 — pre-registered analysis scripts, hash-pinned.

A study analysis must be fixed *before* the data is seen and must not change
after the fact: the garden-of-forking-paths defence, made a checkable property
rather than a promise. An analysis is pre-registered by an id-shaped id, the
track it belongs to, the path of the exact script that runs it, and the
SHA-256 of that script's bytes. Running an analysis that was never registered,
or whose bytes have drifted from the recorded hash, is REFUSED — fail closed.

Two boundaries live here and nowhere else:

- :class:`RegisteredAnalysis` — *what was declared*. Every field is id- or
  hash-shaped; the ``script`` path is confined to the analyses directory so a
  registration cannot point the hash gate at a file outside the package
  (invariant 14, path-traversal).
- :class:`PreRegistration` — *the closed set of declared analyses*, loaded from
  ``analysis_registry.yaml``. :meth:`PreRegistration.verify` is the gate: it
  refuses an unregistered id and refuses a hash mismatch, echoing neither the
  id-less source nor the drifted bytes (invariant 6).

The registry ships **filled**, because unlike a study (which needs an ethics
approval no human has granted, HB-R1) an analysis script is code this repo
authors: the four track notebooks are declared here and their hashes are the
hashes of the shipped files. A test proves the recorded hash equals the file's
hash, so a silent edit of a pre-registered analysis fails CI.
"""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from intake_platform.research.studies import STUDY_FIELD_SHAPE

__all__ = [
    "AnalysisHashMismatchError",
    "AnalysisNotRegisteredError",
    "PreRegistration",
    "PreRegistrationError",
    "RegisteredAnalysis",
    "analyses_root",
    "content_sha256",
    "default_preregistration_path",
    "load_default_preregistration",
    "load_preregistration",
    "verify_analysis_file",
]

#: A registered script is a ``.py`` file inside the analyses directory, named in
#: the same conservative alphabet the rest of the research package uses, with a
#: single optional subdirectory. No ``..``, no absolute path, no separator that
#: reads as a climb: the hash gate must never be pointed outside the package.
_SCRIPT_PATH_SHAPE = re.compile(r"(?:[A-Za-z0-9][A-Za-z0-9._-]*/)?[A-Za-z0-9][A-Za-z0-9._-]*\.py")

#: A SHA-256 digest as lower-case hex.
_SHA256_SHAPE = re.compile(r"[0-9a-f]{64}")


class PreRegistrationError(ValueError):
    """A pre-registration that must not load, or a gate that must not pass."""


class AnalysisNotRegisteredError(PreRegistrationError):
    """No analysis with this id is pre-registered. Fail closed: an id nobody
    declared in advance cannot be run."""


class AnalysisHashMismatchError(PreRegistrationError):
    """The script's bytes do not match the hash recorded at registration. A
    pre-registered analysis was changed after the fact, which is exactly the
    move this gate exists to refuse."""


def content_sha256(source: bytes) -> str:
    """The content address of a script: the plain SHA-256 of its bytes, hex."""
    return hashlib.sha256(source).hexdigest()


class RegisteredAnalysis(BaseModel):
    """One pre-registered analysis. Frozen and closed: a registration with an
    extra key is a registration that drifted from the schema."""

    # hide_input_in_errors mirrors the study registry's reasoning: a paste error
    # in the registry must not travel into a traceback or a log (invariant 6).
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    analysis_id: str
    track: str
    #: Path to the script, RELATIVE to :func:`analyses_root`. Confined to the
    #: analyses directory so a registration cannot aim the hash gate elsewhere.
    script: str
    #: SHA-256 of the script bytes, recorded at registration.
    sha256: str
    #: A short human description of what the analysis does. Not clinical copy,
    #: not patient-facing; it never carries a figure (invariant 20).
    description: str = Field(min_length=1, max_length=300)

    @field_validator("analysis_id", "track", mode="after")
    @classmethod
    def _id_shaped(cls, value: str, info: Any) -> str:
        if STUDY_FIELD_SHAPE.fullmatch(value) is None:
            raise ValueError(
                f"pre-registration field {info.field_name!r} must be id-shaped "
                "([A-Za-z0-9._:-], ≤64); the refused value is not echoed"
            )
        return value

    @field_validator("script", mode="after")
    @classmethod
    def _script_is_confined(cls, value: str) -> str:
        if _SCRIPT_PATH_SHAPE.fullmatch(value) is None or ".." in value:
            raise ValueError(
                "a registered script path must be a .py file inside the analyses "
                "directory with no parent-directory climb (invariant 14); the refused "
                "value is not echoed"
            )
        return value

    @field_validator("sha256", mode="after")
    @classmethod
    def _sha_shaped(cls, value: str) -> str:
        if _SHA256_SHAPE.fullmatch(value) is None:
            raise ValueError("sha256 must be 64 lower-case hex characters")
        return value


class PreRegistration(BaseModel):
    """The closed set of pre-registered analyses an analyst's tooling may run."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    analyses: tuple[RegisteredAnalysis, ...] = ()

    def get(self, analysis_id: str) -> RegisteredAnalysis:
        """The registered analysis, or a refusal. Fail closed on an unknown id."""
        for analysis in self.analyses:
            if analysis.analysis_id == analysis_id:
                return analysis
        raise AnalysisNotRegisteredError(
            f"no analysis {analysis_id!r} is pre-registered; an analysis is declared by a "
            "human into analysis_registry.yaml before the data is seen, never at run time"
        )

    def verify(self, analysis_id: str, source: bytes) -> RegisteredAnalysis:
        """Return the record iff ``source`` hashes to its recorded ``sha256``;
        refuse otherwise. Neither the id-less source nor the digest is echoed."""
        record = self.get(analysis_id)
        actual = content_sha256(source)
        if actual != record.sha256:
            raise AnalysisHashMismatchError(
                f"analysis {analysis_id!r} does not match its pre-registered hash: the "
                "script was changed after it was registered (the refused bytes are not echoed)"
            )
        return record


def analyses_root() -> Path:
    """The directory the pre-registered scripts live in, beside this module."""
    return Path(__file__).with_name("analyses")


def default_preregistration_path() -> Path:
    """The packaged pre-registration file, beside this module."""
    return Path(__file__).with_name("analysis_registry.yaml")


def load_preregistration(path: Path) -> PreRegistration:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise PreRegistrationError(f"{path} is not a mapping document")
    return PreRegistration.model_validate(loaded)


@lru_cache(maxsize=1)
def load_default_preregistration() -> PreRegistration:
    """The shipped pre-registration, parsed once; the models are frozen, so the
    cached instance is safe to share."""
    return load_preregistration(default_preregistration_path())


def verify_analysis_file(
    analysis_id: str,
    *,
    registry: PreRegistration | None = None,
    root: Path | None = None,
) -> RegisteredAnalysis:
    """Read the registered script from disk and verify it against its recorded
    hash. Refuses an unregistered id (:class:`AnalysisNotRegisteredError`) and a
    drifted file (:class:`AnalysisHashMismatchError`)."""
    reg = registry if registry is not None else load_default_preregistration()
    base = root if root is not None else analyses_root()
    record = reg.get(analysis_id)
    source = (base / record.script).read_bytes()
    return reg.verify(analysis_id, source)
