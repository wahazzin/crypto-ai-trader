"""
lock.py -- the spec lock: code-enforced "you cannot move the goalposts".

CONCEPT:
  A cryptographic hash (SHA-256) is a fingerprint of a file: change one character and the
  fingerprint changes completely. At lock time we store the fingerprints of the three things
  that define the experiment:
      PREREGISTRATION.md   (the rules and verdict criteria)
      experiment.json      (universe, costs, risk limits, model, cadence)
      the trader prompt    (exactly what the AI is told)
  Every cycle the runner recomputes them and REFUSES TO RUN on any mismatch. Changing a
  parameter after seeing results then requires an explicit, logged `amend` -- see
  PREREGISTRATION.md section 9.

HONEST LIMIT: this is a speed bump plus an audit trail, not tamper-proofing. The owner can
still edit lock.json. What it really does is make quiet edits impossible by accident and loud
by design; git history (public, timestamped) is the second witness.

Line endings are normalised before hashing so Windows (CRLF) and the Linux cloud runner (LF)
produce the same fingerprint.

CLI:
  python -m crypto_ai.lock --create --state-dir STATE     # start the experiment clock
  python -m crypto_ai.lock --verify --state-dir STATE
  python -m crypto_ai.lock --amend "reason" --state-dir STATE
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crypto_ai.journal import Journal, iso, now_utc

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
# Code whose behaviour IS the experiment: strategy rules, risk rules, the universe rule.
# Editing these after the lock (even a "harmless" tweak) needs a logged amendment.
LOCKED_CODE = [os.path.join("strategies", "toolbox.py"), os.path.join("risk", "engine.py"), "universe.py"]


def load_config(pkg_dir=PKG_DIR):
    with open(os.path.join(pkg_dir, "experiment.json"), encoding="utf-8") as f:
        return json.load(f)


def _sha(path):
    with open(path, "rb") as f:
        data = f.read().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def compute_hashes(pkg_dir=PKG_DIR):
    cfg = load_config(pkg_dir)
    names = ["PREREGISTRATION.md", "experiment.json", cfg["llm"]["prompt_file"]] + LOCKED_CODE
    return {n: _sha(os.path.join(pkg_dir, n)) for n in names}


def _git_sha(pkg_dir):
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=pkg_dir, capture_output=True,
                             text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def create_lock(state_dir, pkg_dir=PKG_DIR):
    j = Journal(state_dir)
    if j.load_json("lock.json") is not None:
        raise RuntimeError("Already locked. The experiment clock cannot be restarted.")
    cfg = load_config(pkg_dir)
    if cfg["llm"]["provider"] == "mock":
        raise RuntimeError("Refusing to lock with the mock LLM provider.")
    if cfg["universe_rule"]["mode"] != "screen":
        raise RuntimeError("Refusing to lock with a fixed (test) universe; the rule must pick the coins.")
    lock = {
        "experiment_id": cfg["experiment_id"],
        "locked_at": iso(now_utc()),
        "code_git_sha": _git_sha(pkg_dir),
        "hashes": compute_hashes(pkg_dir),
        "amendments": [],
    }
    j.save_json("lock.json", lock)
    return lock


def verify_lock(state_dir, pkg_dir=PKG_DIR):
    """Returns (ok, problems). Compares current hashes to the latest accepted set."""
    lock = Journal(state_dir).load_json("lock.json")
    if lock is None:
        return False, ["no lock.json in state dir"]
    expected = lock["amendments"][-1]["hashes"] if lock["amendments"] else lock["hashes"]
    current = compute_hashes(pkg_dir)
    problems = [f"{name}: changed since lock (not amended)" for name, h in current.items()
                if expected.get(name) != h]
    return (not problems), problems


def apply_requests(state_dir, pkg_dir=PKG_DIR):
    """Applies amendment requests committed to the repo (amendment_requests.json: [{"id", "reason"}])
    that the lock hasn't recorded yet. This is how a change gets logged from GitHub without a human
    running a command: the request is public in git history, the application is in lock.json and
    AMENDMENTS.md. Returns the newly applied entries."""
    path = os.path.join(pkg_dir, "amendment_requests.json")
    lock = Journal(state_dir).load_json("lock.json")
    if lock is None or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        reqs = json.load(f)
    done = {a.get("id") for a in lock["amendments"]}
    out = []
    for r in reqs:
        if r["id"] not in done:
            out.append(amend(state_dir, r["reason"], pkg_dir, amendment_id=r["id"]))
    return out


def amend(state_dir, reason, pkg_dir=PKG_DIR, amendment_id=None):
    if not reason or len(reason.strip()) < 10:
        raise ValueError("An amendment needs a real reason (10+ characters).")
    j = Journal(state_dir)
    lock = j.load_json("lock.json")
    if lock is None:
        raise RuntimeError("No lock to amend.")
    entry = {"at": iso(now_utc()), "id": amendment_id, "reason": reason.strip(), "hashes": compute_hashes(pkg_dir),
             "code_git_sha": _git_sha(pkg_dir)}
    lock["amendments"].append(entry)
    j.save_json("lock.json", lock)
    with open(j.path("AMENDMENTS.md"), "a", encoding="utf-8", newline="\n") as f:
        f.write(f"- {entry['at']}{' [' + amendment_id + ']' if amendment_id else ''}: {entry['reason']}\n")
    return entry


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--create", action="store_true")
    g.add_argument("--verify", action="store_true")
    g.add_argument("--amend", metavar="REASON")
    g.add_argument("--apply-requests", action="store_true")
    a = ap.parse_args()
    if a.create:
        print(json.dumps(create_lock(a.state_dir), indent=2))
    elif a.apply_requests:
        for e in apply_requests(a.state_dir):
            print("applied amendment", e["id"], ":", e["reason"][:100])
    elif a.verify:
        ok, problems = verify_lock(a.state_dir)
        print("LOCK OK" if ok else "LOCK PROBLEMS: " + "; ".join(problems))
        sys.exit(0 if ok else 1)
    else:
        print(json.dumps(amend(a.state_dir, a.amend), indent=2))
