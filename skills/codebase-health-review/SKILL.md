---
name: codebase-health-review
description: Review explicit cleanup, technical-debt, architecture-hygiene, or repository-health work.
---

# Codebase health review

1. Keep the review within the requested scope and inspect established project
   conventions before labeling a pattern as drift.
2. Look for duplicate utilities, competing conventions, stale code, flaky
   verification, obsolete dependencies, temporary workarounds, and generated
   artifacts detached from their source.
3. Remove or consolidate only with evidence; absence of an obvious caller is not
   proof that code is unused.
4. Fix small, safe, in-scope issues directly. Report larger findings without
   silently expanding the task.
5. Keep cleanup reviewable and verify affected behavior through Docker.
