---
suggest_when:
  - signal: file_extension
    value: ".tsx"
    min_edits: 6
    cooldown: 45
    message: "Lots of UI changes? `/dogfood` runs systematic QA with screenshots and repro evidence"
  - signal: edits_since_commit
    value: 15
    cooldown: 45
    message: "Major changes in flight — `/dogfood` exploratory-tests the running app to catch bugs before PR"
---

# /dogfood

Systematically explore and test a web application to find bugs, UX issues, and quality problems. Produces a structured report with full reproduction evidence (screenshots, repro videos, step-by-step instructions).

## Usage

```
/dogfood <url> [options]
```

## Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| `<url>` | Target URL to test (required) | `http://localhost:3000`, `vercel.com` |
| `--scope <area>` | Focus on a specific area | `--scope "billing page"` |
| `--session <name>` | Custom session name | `--session my-qa` |
| `--output <dir>` | Output directory | `--output ./qa-results/` |
| `--auth` | Force authentication before exploring (auto-detected by default) | `--auth` |

## Process

1. **Load the dogfood skill** for the full QA workflow
2. **Initialize** session, output directories, and report file
3. **Authenticate** automatically if login page detected (reads `.env.local`)
4. **Orient** by taking initial screenshots and mapping app structure
5. **Explore** systematically -- visit pages, test interactions, check console
6. **Document** each issue with appropriate evidence (video + screenshots for interactive bugs, single screenshot for static issues)
7. **Wrap up** with severity counts and summary

## Evidence Standards

| Issue Type | Evidence Required |
|------------|-------------------|
| Interactive/behavioral bugs | Repro video + step-by-step screenshots |
| Static issues (typos, layout) | Single annotated screenshot |
| Console errors | Screenshot + error text |

## Output

```
dogfood-output/
├── report.md              # Structured findings report
├── screenshots/           # Annotated screenshots per issue
│   ├── initial.png
│   ├── issue-001-step-1.png
│   └── issue-001-result.png
└── videos/                # Repro videos for interactive bugs
    └── issue-001-repro.webm
```

## Examples

```bash
# Quick dogfood of a local app
/dogfood http://localhost:3000

# Focus on a specific area
/dogfood https://myapp.vercel.app --scope "settings page"

# With authentication
/dogfood https://staging.myapp.com --auth

# Custom output directory
/dogfood https://myapp.com --output ./qa/sprint-12/
```

## Prerequisites

Requires `agent-browser` CLI. Install with:

```bash
npm install -g agent-browser
```

## Related

| Command | Relationship |
|---------|-------------|
| `/verify-visual` | Quick visual snapshot (dogfood is comprehensive QA) |
| `/rams` | Accessibility + design audit (dogfood catches a11y from user perspective) |
| `/review` | Code review (dogfood is browser-based, not code-based) |

## Suggested Next

- `/debug-browser` — interactive browser debugging for issues found during QA
- `/debug` — hypothesis-driven debugging for specific failures
- `/review` — code review following QA findings
