---
suggest_when:
  - signal: total_tool_calls
    value: 20
    cooldown: 60
    message: "Using a toolkit skill heavily this session? `/log-skill` records it to ~/.ai/events.jsonl for PAOPAIA tracking"
---

# /log-skill

Log a toolkit event to `~/.ai/events.jsonl` for PAOPAIA to pick up.

## Usage

```
/log-skill <skill-name> [project-name]
```

## Process

1. Generate a UUID for the event
2. Capture the current timestamp (ISO 8601)
3. Detect the current project from the working directory name
4. Append a JSON line to `~/.ai/events.jsonl`:

```json
{
  "id": "<uuid>",
  "timestamp": "<iso-timestamp>",
  "type": "skill_used",
  "name": "<skill-name>",
  "project": "<project-name or cwd basename>",
  "success": true
}
```

## Implementation

Run this bash one-liner to append the event:

```bash
echo "{\"id\":\"$(uuidgen | tr '[:upper:]' '[:lower:]')\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"type\":\"skill_used\",\"name\":\"$1\",\"project\":\"${2:-$(basename $PWD)}\",\"success\":true}" >> ~/.ai/events.jsonl
```

## Example

```
/log-skill react-component my-saas-app
# → Appends event to ~/.ai/events.jsonl
# → PAOPAIA daemon detects the new line
# → ACS creates/updates a memory entry
# → Web viewer at localhost:37777 shows the event
```

## Notes

- This is a manual bridge for the hello world demo
- Future: hooks will auto-emit events when skills are loaded by the agent
- The events.jsonl file is append-only; PAOPAIA tails new lines

## Suggested Next

- `/iterate` — continue plan execution after logging
- `/wrap-up` — end session with skill tracking included
- `/learn` — document patterns discovered while using the skill
