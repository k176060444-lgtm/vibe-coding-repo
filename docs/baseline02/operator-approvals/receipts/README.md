# Real operator approval receipts

This directory contains **real** (non-draft) operator approval receipt YAML files
that have been operator-authorized and applied (or are pending apply via
`--apply`).

Files in `../draft/` are stale-invariant test fixtures that deliberately carry
outdated `base_sha` values to validate fail-closed behavior.  Files in this
directory carry the actual `base_sha` matching the main SHA at creation time.
