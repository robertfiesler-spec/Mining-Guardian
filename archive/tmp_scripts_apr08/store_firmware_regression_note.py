"""Add an operator-correction note to knowledge.json so the system learns
from today's firmware regression.

This is the manual version of the eventual auto-detected regression flag.
Stores both miners' real root cause as an operator override that will
appear in future LLM context prompts.
"""
import os, sys
os.chdir('/root/Mining-Gaurdian')
sys.path.insert(0, '/root/Mining-Gaurdian/ai')

from knowledge_manager import KnowledgeManager
km = KnowledgeManager()

note = """OPERATOR LEARNING NOTE — April 8, 2026
========================================

CONTEXT: Both Auradine AH3880 miners in the fleet (192.168.188.28 and
192.168.188.55) recently received a firmware update from Auradine.
After the update, BOTH miners began exhibiting the same fault patterns:

- DVFS power overshoot alarms (power clipping at 11.5kW vs 10kW budget)
- PowerState voltage clipping at both Vmin (31V) and Vmax (47V)
- PSU IOUT 0x02 overcurrent shutdown trips
- PSU AC input fault (Status 0x10)
- PSU fan fault (Status 0x02)
- Hundreds of pool stratum panics in gcminer
- Hashrate stuck at ~79% of tune target

The dual-model LLM analysis (Qwen + Claude) on both miners diagnosed
"Replace PSU" with HIGH confidence. Both LLMs were reading symptoms
correctly but blamed the WRONG component.

ROOT CAUSE: The new firmware version is mismanaging DVFS power delivery
in a way that LOOKS like PSU instability to a logs-only diagnostic.
The PSUs are probably fine. Operator (Bobby) has emailed Auradine to
request the previous firmware version for rollback.

CORRECTED VERDICT for both auradine_28 and auradine_55:
- DO NOT replace PSU until firmware rollback is attempted first
- The fault is FIRMWARE REGRESSION, not hardware failure
- Roll back to previous firmware version when Auradine provides it

LEARNING FOR FUTURE LLM ANALYSES:
When MULTIPLE miners of the SAME MODEL exhibit the SAME fault pattern
within a SHORT time window of a firmware update, prefer "firmware
regression" over "individual hardware failure" as the diagnosis.
This is true even when the symptoms (PSU error codes, DVFS alarms)
look unambiguously like hardware faults — firmware bugs can produce
identical symptoms.

This is the canonical example of why daily log capture with rolling
14-day baseline retention is operationally critical: with pre-firmware
baselines available, the system would have detected the regression
immediately on the first post-update scan instead of misdiagnosing.

See docs/DAILY_LOG_CAPTURE_VISION.md for the build plan.
"""

km.add_llm_insight(note, miner_id='operator_learning:firmware_regression_2026_04_08')
print('Operator learning note stored in knowledge.json')
print('miner_id: operator_learning:firmware_regression_2026_04_08')
