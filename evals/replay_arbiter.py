#!/usr/bin/env python3
"""Replay recorded failing/succeeding consortium arbiter prompts through
legacy-inline vs system-channel modes against currently-available models."""
import sqlite3, json, re, sys, time, random
import llm

DB = "/home/thomas/.config/io.datasette.llm/logs.db"
OUT = "/tmp/replay/results.json"
MODELS = sys.argv[1].split(",") if len(sys.argv) > 1 else ["kimi-k3"]
LIMIT_FAIL = int(sys.argv[2]) if len(sys.argv) > 2 else 6
LIMIT_OK = int(sys.argv[3]) if len(sys.argv) > 3 else 3
MAX_PLEN = int(sys.argv[4]) if len(sys.argv) > 4 else 80000

db = sqlite3.connect(DB); db.row_factory = sqlite3.Row
def fetch(fail, limit):
    cond = "NOT LIKE" if fail else "LIKE"
    rows = db.execute(f"""
        SELECT id, model, prompt FROM responses
        WHERE prompt LIKE '<arbiter_prompt>%' AND prompt LIKE '%</arbiter_prompt>%'
          AND length(prompt) < {MAX_PLEN}
          AND response {cond} '%<confidence>%'
        ORDER BY length(prompt) DESC LIMIT {limit}""").fetchall()
    return [dict(r) for r in rows]

def split_prompt(p):
    i = p.find("</arbiter_prompt>")
    j = i + len("</arbiter_prompt>")
    data = p[:j]
    instr = p[j:].lstrip("\n")
    return data, instr

CONF_RE = re.compile(r"<confidence>\s*([\d.]+)\s*</confidence>", re.S)

def score(resp):
    m = CONF_RE.search(resp or "")
    if m:
        try: return dict(ok=True, conf=float(m.group(1)), mode="tagged")
        except ValueError: pass
    if (resp or "").strip() == "": return dict(ok=False, conf=0.0, mode="empty")
    if len(resp or "") < 400: return dict(ok=False, conf=0.0, mode="truncated")
    return dict(ok=False, conf=0.0, mode="malformed")

cases = [("FAIL", r) for r in fetch(True, LIMIT_FAIL)] + [("OK", r) for r in fetch(False, LIMIT_OK)]
print(f"cases: {len(cases)} (fail={sum(1 for c,_ in cases if c=='FAIL')}, ok={sum(1 for c,_ in cases if c=='OK')})")

results = []
for model_id in MODELS:
    model = llm.get_model(model_id)
    for cls, case in cases:
        data, instr = split_prompt(case["prompt"])
        for mode in ("inline", "system"):
            rec = dict(model=model_id, cls=cls, src_id=case["id"], src_model=case["model"],
                       mode=mode, plen=len(case["prompt"]), instr_len=len(instr))
            try:
                t0 = time.time()
                if mode == "inline":
                    r = model.prompt(case["prompt"])
                else:
                    r = model.prompt(data, system=instr)
                resp = r.text()
                rec.update(score(resp)); rec["dur_s"] = round(time.time()-t0, 1)
                rec["resp_head"] = resp[:180]
            except Exception as e:
                rec.update(ok=False, conf=0.0, mode=f"error: {type(e).__name__}: {str(e)[:120]}")
            results.append(rec)
            print(f"{model_id:16s} {cls:4s} {mode:6s} plen={rec['plen']:6d} -> ok={rec['ok']} {rec['mode']} conf={rec.get('conf')}")
            json.dump(results, open(OUT, "w"), indent=1)

print("\n=== SUMMARY ===")
for model_id in MODELS:
    for mode in ("inline", "system"):
        rs = [r for r in results if r["model"] == model_id and r["mode"] == mode]
        fails = [r for r in rs if r["cls"] == "FAIL"]
        okn = sum(1 for r in fails if r["ok"])
        print(f"{model_id:16s} {mode:6s}: FAIL-cases recovered {okn}/{len(fails)}")
