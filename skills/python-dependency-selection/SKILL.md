---
name: python-dependency-selection
description: Select or replace a Python dependency when a material library choice is open.
---

# Python dependency selection

1. Inspect the existing implementation, dependency metadata, and established
   packages.
2. State only the requirements that materially constrain the choice.
3. Prefer an adequate existing project dependency and keep trivial logic in the
   standard library.
4. For non-trivial commodity behavior with meaningful edge cases, compare
   mature libraries before choosing bespoke code.
5. Verify current authoritative information when maintenance, compatibility,
   security, performance, or licensing could change the decision.
6. Do not introduce overlapping libraries or ceremonial wrappers without a
   concrete capability or contract boundary.
7. Add, install, and verify the selected dependency through Docker, and record
   the decision when its rationale is likely to matter later.
