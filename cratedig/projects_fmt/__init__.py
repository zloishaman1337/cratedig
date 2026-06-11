"""Best-effort parsers for non-Ableton DAW project files (Bitwig, Nuendo).

These formats are proprietary binary; the parsers extract the reliably-recoverable
signal — referenced sample files and plugin/device names — rather than full track
device trees. Shared helpers live in ``common``.
"""
