"""Serving compiled protocol bundles (INT-058): verify, then pin per session.

:mod:`protocols.serving.trust` turns signed archive bytes into a
:class:`~protocols.serving.trust.VerifiedBundle` or a typed refusal;
:mod:`protocols.serving.pins` keeps the verified versions and pins each
session to the one it started on. files/04 §7; files/10 §8, §9
``protocol-registry``.
"""
