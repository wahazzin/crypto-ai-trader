"""Smoke-test helper: pretend every open AI thesis has crossed its exit level, so the next
scanner tick must wake the AI. Throwaway smoke state only -- refuses a locked state dir."""
import glob
import json
import os
import sys

d = sys.argv[1]
if os.path.exists(os.path.join(d, "lock.json")):
    sys.exit("refusing: locked experiment state")
n = 0
for p in glob.glob(os.path.join(d, "theses", "*.json")):
    with open(p) as f:
        t = json.load(f)
    for v in t.values():
        v["exit_below"] = 1e12
        n += 1
    with open(p, "w") as f:
        json.dump(t, f)
print(f"force_wake: set exit_below on {n} theses")
