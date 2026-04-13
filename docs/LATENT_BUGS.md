# Latent Bugs in Mining Guardian

**Created:** April 13, 2026

## NameError Bugs (2 locations)

From April 12 code review:

1. predictor.py line ~4619 - Variable may not be defined
2. mining_guardian.py line ~4040 - NameError in _escalate_board_issue

**Status:** Not triggered in 1,482 scans
**Priority:** Fix when next editing those files

See REPAIR_LOG.md 2026-04-12 for discovery details.
