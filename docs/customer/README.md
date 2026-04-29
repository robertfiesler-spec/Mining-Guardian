# Customer-facing documentation

Three PDFs that ship with every Mining Guardian install kit. Built from
a shared brand template — same dark-navy + Bitcoin-orange visual system
as the installer wizard.

| File | Pages | Audience | When to read |
| ---- | ----- | -------- | ------------ |
| `MiningGuardian_Setup_Manual.pdf`         | 12 | Operator (one-time) | First time the Mac Mini is set up — install paths A and B, verify, first launch, troubleshooting. |
| `MiningGuardian_Program_Instructions.pdf` | 10 | Operator (daily)    | Day-to-day usage — orientation, importing data, monitoring, investigating, daily habits. |
| `MiningGuardian_Brochure.pdf`             |  4 | Prospect / customer | Features & benefits at a glance; mentions the iPhone companion app shipping in the next couple of weeks. |

## Source

Source files live in the `customer_docs/` folder of the workspace
(not in this repo) — `mg_brand.py` is the shared template; one
`build_*.py` per PDF; ReportLab + DM Sans (downloaded at build time
from googlefonts/dm-fonts).

## Updating

The screenshots embedded in these PDFs are placeholders pulled from
v1.0 development. Once the production UI ships, swap in the new
screenshots and rebuild — paths are in:

- `customer_docs/build_setup_manual.py` (`SHOT_*` vars near the top)
- `customer_docs/build_program_instructions.py`
- `customer_docs/build_brochure.py`

Then run:

```
cd customer_docs
python3 build_setup_manual.py
python3 build_program_instructions.py
python3 build_brochure.py
```

PDFs land in `customer_docs/output/`.

## iPhone app callout

All three PDFs reference an "iPhone companion app · shipping in the next
couple of weeks." When that ships, update the same callouts (search the
build scripts for "Coming soon").
