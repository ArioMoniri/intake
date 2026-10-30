"""Patient passkeys and the step-up gate on sensitive actions (INT-582, D36).

- :mod:`.webauthn` — the WebAuthn registration and assertion checks.
- :mod:`.challenges` — single-use, short-lived challenges and step-up grants.
- :mod:`.store` — the patient's passkey public keys (``patient_passkeys``).
- :mod:`.service` — the ceremonies, audited and counted.
- :mod:`.gate` — ``require_step_up(action)`` in front of each sensitive route.
- :mod:`.routes` — ``/v1/me/passkeys``.
"""
