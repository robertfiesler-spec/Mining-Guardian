#!/usr/bin/env python3
"""Fix approval API URL and CORS for dashboard iframe."""
# Fix 1: Update APPROVAL_API to use Cloudflare tunnel
with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/ai_dashboard_api.py") as f:
    c = f.read()

c = c.replace(
    'APPROVAL_API = "http://localhost:8686"',
    'APPROVAL_API = "https://slack.fieslerfamily.com"'
)

with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/ai_dashboard_api.py", "w") as f:
    f.write(c)
print("Fixed: APPROVAL_API now uses Cloudflare tunnel")

# Fix 2: Add CORS to approval API
with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/approval_api.py") as f:
    c = f.read()

# Check if CORS already added
if "CORSMiddleware" not in c:
    # Add CORS import and middleware after app creation
    c = c.replace(
        'app = FastAPI(',
        '''from fastapi.middleware.cors import CORSMiddleware

app = FastAPI('''
    )
    # Find where app is defined and add middleware after
    c = c.replace(
        'app = FastAPI(title=',
        'app = FastAPI(title='
    )
    # Add CORS middleware after the app definition block
    # Find the first @app route and insert before it
    import re
    match = re.search(r'\n@app\.', c)
    if match:
        insert_pos = match.start()
        cors_code = '''
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dashboard.fieslerfamily.com",
        "https://grafana.fieslerfamily.com",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

'''
        c = c[:insert_pos] + cors_code + c[insert_pos:]
        with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/approval_api.py", "w") as f:
            f.write(c)
        print("Fixed: Added CORS to approval API")
    else:
        print("WARNING: Could not find @app route to insert CORS")
else:
    # Just update allowed origins
    if "dashboard.fieslerfamily.com" not in c:
        c = c.replace(
            "allow_origins=[",
            'allow_origins=[\n        "https://dashboard.fieslerfamily.com",\n        "https://grafana.fieslerfamily.com",'
        )
        with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/approval_api.py", "w") as f:
            f.write(c)
        print("Fixed: Updated CORS origins in approval API")
    else:
        print("CORS already configured correctly")
