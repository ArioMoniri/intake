"""INT-205 — the deployment plan, and the two things it refuses to guess.

**The host.** A Wazuh manager, a Wazuh indexer with a JVM heap and a Falco agent
with a kernel driver do not fit on this machine, and files/05 already says so:
"Defer Wazuh (12 GB + a part-time SRE)". The bounds below are read out of the
open blocker rows rather than chosen — HB-I1 asks for 80–100 GB of free disk,
HB-I2 records that "the security + observability tiers alone need 22 GB" of
container memory. The refusal names the rows, because the fix is a person's
action and not a smaller stack.

**The retention window.** files/06 §3's retention matrix has rows for audio,
lane windows, notes, tokens, audit and 5651 traffic logs, and no row for SIEM
alert storage; files/10 §6's "30 d hot / 1 y cold" is the application logging
pipeline, not the alert store. So nothing here sets one: ossec.conf writes no
``<rotation>``, the indexer gets no lifecycle policy, and the deploy refuses
until someone supplies ``INTAKE_SIEM_RETENTION_DAYS``. The failure mode of the
refusal is that the store keeps everything, which loses no evidence — the same
posture INT-202 took with pgBackRest expiry.
"""

from __future__ import annotations

from dataclasses import dataclass

from intake_platform.siem.errors import RetentionNotConfiguredError

__all__ = [
    "DeployBlocked",
    "DeployStep",
    "MIN_CONTAINER_MEMORY_BYTES",
    "MIN_FREE_DISK_BYTES",
    "RETENTION_ASK",
    "RETENTION_ENV",
    "host_preflight",
    "plan_siem_deploy",
]

#: HB-I1: "Free 80–100 GB of disk". The lower end of the row's own range.
MIN_FREE_DISK_BYTES = 80 * 1024**3

#: HB-I2: "the security + observability tiers alone need 22 GB".
MIN_CONTAINER_MEMORY_BYTES = 22 * 1024**3

RETENTION_ENV = "INTAKE_SIEM_RETENTION_DAYS"

RETENTION_ASK = (
    "No retention window for the SIEM alert store. files/06 §3's retention matrix has no "
    "row for it and files/10 states none, so this is a KVKK-7 / DEST-2017 question rather "
    f"than an ops preference: it belongs to INT-212 (retention & destruction policy). Set "
    f"{RETENTION_ENV} once someone has answered it. Until then nothing expires, which loses "
    "no evidence."
)


@dataclass(frozen=True, slots=True)
class DeployBlocked:
    """A typed refusal that names the blocker rows which unblock it."""

    reason: str


@dataclass(frozen=True, slots=True)
class DeployStep:
    name: str
    argv: tuple[str, ...]


def host_preflight(free_disk_bytes: int, docker_memory_bytes: int) -> DeployBlocked | None:
    """Return a refusal when this host cannot run the tier, or ``None``."""
    shortfalls: list[str] = []
    if free_disk_bytes < MIN_FREE_DISK_BYTES:
        shortfalls.append(
            f"HB-I1 (disk): {free_disk_bytes / 1024**3:.0f} GiB free, "
            f"{MIN_FREE_DISK_BYTES / 1024**3:.0f} GiB needed"
        )
    if docker_memory_bytes < MIN_CONTAINER_MEMORY_BYTES:
        # Nobody passing a figure is not the same fact as a host with no memory,
        # and a refusal that misdescribes the host is one somebody argues with.
        allocated = (
            "not reported"
            if docker_memory_bytes <= 0
            else f"{docker_memory_bytes / 1024**3:.0f} GiB allocated"
        )
        shortfalls.append(
            f"HB-I2 (container memory): {allocated}, "
            f"{MIN_CONTAINER_MEMORY_BYTES / 1024**3:.0f} GiB needed"
        )
    if not shortfalls:
        return None
    return DeployBlocked(
        reason=(
            "this host cannot run the SIEM tier and the tier is not shrunk to fit: "
            + "; ".join(shortfalls)
        )
    )


def plan_siem_deploy(retention_days: int | None) -> tuple[DeployStep, ...]:
    """The commands `make siem` runs, rendered without running anything."""
    if retention_days is None or retention_days <= 0:
        raise RetentionNotConfiguredError(RETENTION_ASK)
    compose = (
        "docker",
        "compose",
        "-f",
        "infra/docker-compose.siem.yml",
        "--profile",
        "siem",
    )
    return (
        DeployStep(name="secrets", argv=("scripts/security/siem_secrets.sh", "--export")),
        DeployStep(name="up", argv=(*compose, "up", "-d", "--wait")),
        DeployStep(
            name="verify-rules",
            argv=(*compose, "exec", "wazuh-manager", "/var/ossec/bin/wazuh-logtest", "-t"),
        ),
        DeployStep(
            name="verify-falco",
            argv=(*compose, "exec", "falco", "falco", "--dry-run"),
        ),
    )
