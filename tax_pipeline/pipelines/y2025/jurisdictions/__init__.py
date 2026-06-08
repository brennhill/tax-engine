"""Per-jurisdiction final-legal-output collectors.

Architecture review 2026-05-04 §5 Proposal 7 — decomposes the
944-line ``final_legal_output.py`` god-object into per-jurisdiction
collectors so adding a third jurisdiction is a registry edit rather
than a multi-place file edit.

Each module here owns one jurisdiction's validation block:

  - ``germany_final``  — § 26a EStG posture gate, ELSTER projection
                         consistency (KAP / N / Kind / Anlage N).
  - ``usa_final``      — 26 U.S.C. §§ 1211/1212/1256 capital sidecar
                         consistency, Form 8949 bucket projection,
                         Form 1040 line consistency, treaty-package
                         projection (DBA-USA Art. 23 / Pub. 514).

Treaty validators (``_validate_treaty_*``) remain inline in
``final_legal_output.py`` pending P3 (registry-driven treaty stages)
landing in parallel — extracting them now would conflict with that
work. Once treaty validators move out, the orchestrator dispatch
loop in ``build_final_legal_output_2025`` can become registry-driven
(architecture review §5 Proposal 7 Commit 5).

The collectors are imported by ``final_legal_output.py`` via the
existing private-name convention; their public surface is
deliberately narrow so that a jurisdiction registry (Proposal 2 +
Proposal 7 Commit 5) can dispatch to them by name.
"""
