#!/usr/bin/env python3
"""Add S19J Pro HVAC to Slack scan reports"""

with open('/root/Mining-Gaurdian/core/mining_guardian.py', 'r') as f:
    content = f.read()

# Fix 1: Update the send_scan call to pass both HVAC systems
old_call = 'thread_ts = self.slack.send_scan(miners, issues, wx, new_notifs, hvac_snapshot)'
new_call = 'thread_ts = self.slack.send_scan(miners, issues, wx, new_notifs, hvac_snapshot, hvac_s19jpro)'

if old_call in content:
    content = content.replace(old_call, new_call)
    print('Fixed: send_scan call now passes hvac_s19jpro')
else:
    print('send_scan call pattern not found')

# Fix 2: Update send_scan signature
old_sig = '''    def send_scan(self, miners: List[Dict], issues: List[Dict],
                  wx: Optional[Dict] = None,
                  ams_notifs: Optional[List[Dict]] = None,
                  hvac=None) -> None:'''

new_sig = '''    def send_scan(self, miners: List[Dict], issues: List[Dict],
                  wx: Optional[Dict] = None,
                  ams_notifs: Optional[List[Dict]] = None,
                  hvac=None,
                  hvac_s19jpro=None) -> None:'''

if old_sig in content:
    content = content.replace(old_sig, new_sig)
    print('Fixed: send_scan signature now accepts hvac_s19jpro')
else:
    print('send_scan signature pattern not found')

with open('/root/Mining-Gaurdian/core/mining_guardian.py', 'w') as f:
    f.write(content)

print('Saved - Part 1 complete!')
