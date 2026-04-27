# OpenClaw Integration — Design Document
## Branch: `openclaw-integration`
## Goal: Make OpenClaw the real AI brain, restore full Slack interactivity

---

## Current State (What's Wrong)

1. **OpenClaw owns Slack Socket Mode** but only posts morning briefings
2. **Mining Guardian polls Slack via API** for APPROVE/DENY text — loses all Block Kit interactivity
3. **OpenClaw's LLM is disconnected** — Ollama config points to stopped local instance, not Windows PC GPU
4. **Zero actions in audit log** involve OpenClaw — it contributes nothing to fleet intelligence
5. **Text-based approve/deny** instead of buttons, checkboxes, dropdowns

## Target State (What We're Building)

1. **OpenClaw is the Slack interface** — all messages to #mining-guardian go through OpenClaw
2. **Block Kit interactions** — approve/deny buttons, denial reason dropdowns, batch actions via checkboxes
3. **Real-time LLM scan analysis** — every scan summary gets LLM commentary ("3 miners running hot, recommend stepping down .45 before afternoon heat")
4. **Denial reason processing** — LLM immediately interprets denial reasons into operational rules
5. **Conversational queries** — operator asks "why did .35 restart 3 times?" and gets intelligent answer

---

## Architecture

```
Mining Guardian (Python daemon)
    │
    ├── Scans fleet via AMS WebSocket (every hour)
    ├── Stores all data in guardian.db
    ├── Runs predictors, action diversity, outcome checker
    │
    └── Posts structured payload to OpenClaw webhook
            │
            ▼
OpenClaw (Docker, Socket Mode)
    │
    ├── Receives scan data via webhook
    ├── Sends to local LLM (Ollama on Windows PC RTX 4090)
    │     └── LLM analyzes scan, writes natural language summary
    │
    ├── Posts to Slack with Block Kit formatting
    │     ├── Scan summary (LLM-written)
    │     ├── Action recommendations with APPROVE/DENY buttons
    │     ├── Batch approve checkboxes for multiple miners
    │     ├── Denial reason dropdown (pre-populated common reasons)
    │     └── Morning briefing with interactive elements
    │
    ├── Handles Slack interactions (button clicks, dropdowns)
    │     ├── APPROVE button → calls Mining Guardian approval API
    │     ├── DENY button → opens denial reason modal
    │     ├── Batch checkbox → approve/deny selected miners
    │     └── Conversational messages → routes to LLM for answer
    │
    └── Feeds responses back to Mining Guardian via API
```

---

## Implementation Plan

### Phase 1: Fix LLM Connection (Today)
- [ ] Update OpenClaw config: point Ollama to Windows PC `100.110.87.1:11434`
- [ ] Verify LLM responds through OpenClaw
- [ ] Test: OpenClaw can generate text via local LLM

### Phase 2: Webhook Integration (Today)
- [ ] Fix Mining Guardian → OpenClaw webhook payload
- [ ] OpenClaw receives scan data and passes to LLM
- [ ] LLM writes natural language scan summary
- [ ] OpenClaw posts LLM summary to #mining-guardian

### Phase 3: Block Kit Messages (Today/Tomorrow)
- [ ] Build Block Kit templates for:
  - Scan summary with action buttons
  - Approval request with APPROVE/DENY buttons per miner
  - Batch approval with checkboxes
  - Denial reason modal with dropdown + free text
  - Morning briefing with interactive sections
- [ ] OpenClaw action handler processes button clicks
- [ ] Route actions to Mining Guardian approval API

### Phase 4: Conversational Interface (Tomorrow)
- [ ] When operator types a question in #mining-guardian, OpenClaw routes to LLM
- [ ] LLM has access to guardian.db context (via prompt injection of relevant data)
- [ ] Answers questions like "why did .35 restart 3 times?" or "which miners are running hottest?"

### Phase 5: Real-time Denial Processing (Tomorrow)
- [ ] When operator provides denial reason, LLM immediately processes it
- [ ] Generates operational rule suggestion: "Don't recommend actions within 20 min of restart"
- [ ] Posts rule to Slack for operator confirmation
- [ ] Confirmed rules get written to knowledge.json immediately (not waiting for weekly training)

---

## OpenClaw Configuration Changes

### openclaw.json updates needed:
```json
{
  "models": {
    "providers": {
      "ollama": {
        "baseUrl": "http://100.110.87.1:11434/v1",
        "models": [
          {
            "id": "qwen2.5:32b-instruct-q4_K_M",
            "name": "Qwen 2.5 32B (RTX 4090)",
            "contextWindow": 32768,
            "maxTokens": 4096
          }
        ]
      }
    }
  },
  "hooks": {
    "enabled": true,
    "token": "hooks_oyHS8MXeZmCRulnQWzs4r5qmEozOCr8Z",
    "actions": {
      "scan_analysis": {
        "enabled": true,
        "prompt_template": "mining_guardian_scan"
      }
    }
  }
}
```

### Mining Guardian config.json updates:
```json
{
  "openclaw_webhook_url": "http://127.0.0.1:58910/hooks",
  "openclaw_gateway_token": "hooks_oyHS8MXeZmCRulnQWzs4r5qmEozOCr8Z"
}
```

---

## Block Kit Message Templates

### Scan Summary with Actions
```json
{
  "blocks": [
    {
      "type": "header",
      "text": { "type": "plain_text", "text": "🤖 Mining Guardian Scan — 2026-04-06 15:00" }
    },
    {
      "type": "section",
      "text": { "type": "mrkdwn", "text": "Fleet: *58 miners* | 🟢 37 online | 🔴 12 offline" }
    },
    {
      "type": "section",
      "text": { "type": "mrkdwn", "text": "🌡️ Outside: *59°F* | HVAC Supply: *75°F* | Return: *87°F*" }
    },
    {
      "type": "section",
      "text": { "type": "mrkdwn", "text": "🧠 *AI Analysis:* Three miners running above thermal threshold..." }
    },
    {
      "type": "divider"
    },
    {
      "type": "section",
      "text": { "type": "mrkdwn", "text": "⚠️ *192.168.188.97* (S19JPro) — HR: 76% | Temp: 72°C" },
      "accessory": {
        "type": "actions",
        "elements": [
          { "type": "button", "text": { "type": "plain_text", "text": "✅ Approve Restart" }, "action_id": "approve_restart_97", "style": "primary" },
          { "type": "button", "text": { "type": "plain_text", "text": "❌ Deny" }, "action_id": "deny_restart_97", "style": "danger" }
        ]
      }
    }
  ]
}
```

### Denial Reason Modal
```json
{
  "type": "modal",
  "title": { "type": "plain_text", "text": "Denial Reason" },
  "submit": { "type": "plain_text", "text": "Submit" },
  "blocks": [
    {
      "type": "input",
      "label": { "type": "plain_text", "text": "Why are you denying this action?" },
      "element": {
        "type": "static_select",
        "placeholder": { "type": "plain_text", "text": "Select a reason..." },
        "options": [
          { "text": { "type": "plain_text", "text": "Miner just restarted — wait 20 min" }, "value": "recent_restart" },
          { "text": { "type": "plain_text", "text": "Outside temp rising — save headroom" }, "value": "thermal_headroom" },
          { "text": { "type": "plain_text", "text": "Known hardware issue — needs physical repair" }, "value": "hardware_issue" },
          { "text": { "type": "plain_text", "text": "Other (explain below)" }, "value": "other" }
        ]
      }
    },
    {
      "type": "input",
      "optional": true,
      "label": { "type": "plain_text", "text": "Additional details" },
      "element": {
        "type": "plain_text_input",
        "multiline": true,
        "placeholder": { "type": "plain_text", "text": "Tell the AI more about your reasoning..." }
      }
    }
  ]
}
```

### Batch Approval with Checkboxes
```json
{
  "blocks": [
    {
      "type": "header",
      "text": { "type": "plain_text", "text": "🔮 AI Recommendations — 5 actions pending" }
    },
    {
      "type": "actions",
      "elements": [
        {
          "type": "checkboxes",
          "action_id": "batch_select",
          "options": [
            { "text": { "type": "mrkdwn", "text": "*.97* — Restart (HR: 76%, Temp: 72°C)" }, "value": "restart_97" },
            { "text": { "type": "mrkdwn", "text": "*.45* — Profile Down (Temp: 74°C)" }, "value": "profile_down_45" },
            { "text": { "type": "mrkdwn", "text": "*.152* — Restart (HR: 64%, Temp: 60°C)" }, "value": "restart_152" }
          ]
        }
      ]
    },
    {
      "type": "actions",
      "elements": [
        { "type": "button", "text": { "type": "plain_text", "text": "✅ Approve Selected" }, "action_id": "batch_approve", "style": "primary" },
        { "type": "button", "text": { "type": "plain_text", "text": "✅ Approve All" }, "action_id": "approve_all" },
        { "type": "button", "text": { "type": "plain_text", "text": "❌ Deny All" }, "action_id": "deny_all", "style": "danger" }
      ]
    }
  ]
}
```

---

## What Stays the Same
- Mining Guardian daemon still does all scanning, DB storage, analysis
- guardian.db is still the single source of truth
- Weekly Claude training continues unchanged
- Approval API (:8686) still handles the actual approve/deny DB operations
- Overnight automation still runs independently

## What Changes
- Slack messages go through OpenClaw Block Kit instead of plain text
- Approve/deny handled by button clicks instead of text polling
- LLM provides real-time commentary on every scan
- Denial reasons collected via dropdown+modal instead of free text in threads
- Operator can ask questions and get LLM-powered answers

---

## Dependencies
- Windows PC (100.110.87.1) must be on and Ollama running
- OpenClaw Docker container stays running
- Slack app must have `chat:write`, `commands`, `im:history`, `groups:history` scopes
- OpenClaw Slack app needs `interactive_components` enabled for Block Kit

---

## Risk Assessment
- **Low risk:** OpenClaw is already running and connected to Slack
- **Medium risk:** LLM quality — Qwen 2.5 32B may need good prompts to give useful analysis
- **Medium risk:** OpenClaw hook/action handler may need custom code — need to understand OpenClaw's plugin system
- **Mitigation:** If OpenClaw can't handle custom actions, we build a lightweight FastAPI bridge that translates Block Kit actions into approval API calls

---

*Created: April 6, 2026*
*Branch: openclaw-integration*
*Target: Deploy Wednesday April 8 morning, before afternoon demo*
