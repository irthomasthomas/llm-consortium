"""A/B: XML contract vs JSON contract vs JSON-schema API mode for the arbiter.
Same payload (truncated reference run d114fff4 iter-1), same system prompt.
Measures: parse success, latency, tokens."""
import json, time, statistics, sys, pathlib
import llm

import os
FULL = os.environ.get('FULL_PAYLOAD') == '1'
PFILE = 'experiments/d114fff4_arbiter_prompt_iter1.txt' if FULL else 'experiments/payload.txt'
PAYLOAD = pathlib.Path(PFILE).read_text()
SYS_XML = pathlib.Path('llm_consortium/arbiter_system.xml').read_text()

JSON_CONTRACT = """You are the arbiter of an LLM consortium. Multiple model responses to an original prompt are provided in the user message.

OUTPUT CONTRACT — reply with ONE JSON object and nothing else:
{
  "analysis": "how you arrived at the synthesis",
  "dissent": "notable dissenting views, if any",
  "synthesis": "comprehensive synthesized answer; no meta-analysis",
  "confidence": 0.55,
  "refinement_areas": ["area1", "area2"],
  "needs_iteration": false,
  "ranking": [650, 748]
}
Rules:
- "ranking" lists ALL response IDs best-to-worst.
- "confidence" is a decimal 0.0-1.0.
- Do not use Markdown. Do not add commentary outside the JSON.
Analyze rigorously: extract unique points per response, compare, identify agreement/disagreement, then synthesize."""

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "analysis": {"type": "string"},
        "dissent": {"type": "string"},
        "synthesis": {"type": "string"},
        "confidence": {"type": "number"},
        "refinement_areas": {"type": "array", "items": {"type": "string"}},
        "needs_iteration": {"type": "boolean"},
        "ranking": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["synthesis", "confidence", "needs_iteration", "ranking"],
    "additionalProperties": False,
}

def parse_xml(text):
    ok = bool(re.search(r"<synthesis>[\s\S]*?</synthesis>", text, re.I))
    rk = re.findall(r'<rank position="\d+">(\d+)</rank>', text, re.I)
    return ok, [int(x) for x in rk]

import re
def parse_json(text):
    m = re.search(r"\{[\s\S]*\}", text)
    if not m: return False, []
    try:
        d = json.loads(m.group(0))
        return bool(d.get("synthesis")), list(d.get("ranking") or [])
    except Exception:
        return False, []

ARMS = {
    "xml":  dict(system=SYS_XML, schema=None),
    "json": dict(system=JSON_CONTRACT, schema=None),
    "schema": dict(system=JSON_CONTRACT, schema=JSON_SCHEMA),
}

MODELS = sys.argv[1].split(",") if len(sys.argv) > 1 else ["deepseek-v4-pro"]
R = int(sys.argv[2]) if len(sys.argv) > 2 else 3

results = []
for mid in MODELS:
    try:
        model = llm.get_model(mid)
    except Exception as e:
        print(f"{mid}: SKIP {e}"); continue
    supports = getattr(model, "supports_schema", False)
    for arm, cfg in ARMS.items():
        if arm == "schema" and not supports:
            results.append(dict(model=mid, arm=arm, status="unsupported")); continue
        for i in range(R):
            t0 = time.time()
            try:
                r = model.prompt(PAYLOAD, system=cfg["system"], schema=cfg["schema"], stream=False)
                text = r.text()
                dt = time.time() - t0
                if arm == "xml":
                    ok, rk = parse_xml(text)
                else:
                    ok, rk = parse_json(text)
                results.append(dict(model=mid, arm=arm, rep=i, ok=ok, ranking=rk,
                                    latency=round(dt,1), out_tok=r.output_tokens,
                                    in_tok=r.input_tokens, chars=len(text)))
                print(f"{mid:28s} {arm:7s} r{i} ok={ok} rank={rk} {dt:5.1f}s out={r.output_tokens}")
            except Exception as e:
                dt = time.time() - t0
                try: text = ''
                except: pass
                results.append(dict(model=mid, arm=arm, rep=i, ok=False, err=str(e)[:120], latency=round(dt,1)))
                print(f"{mid:28s} {arm:7s} r{i} ERR {str(e)[:100]}")

pathlib.Path('experiments/ab_results.jsonl').open('a').write(
    "\n".join(json.dumps(x) for x in results) + "\n")

# summary
print("\n=== SUMMARY ===")
from collections import defaultdict
agg = defaultdict(lambda: dict(n=0, ok=0, lat=[], out=[]))
for x in results:
    if 'ok' not in x: continue
    k = (x['model'], x['arm'])
    agg[k]['n'] += 1
    agg[k]['ok'] += int(x['ok'])
    agg[k]['lat'].append(x['latency'])
    if x.get('out_tok'): agg[k]['out'].append(x['out_tok'])
for (m, a), v in sorted(agg.items()):
    lat = statistics.median(v['lat']) if v['lat'] else 0
    out = statistics.median(v['out']) if v['out'] else 0
    print(f"{m:28s} {a:7s} ok {v['ok']}/{v['n']}  med_lat {lat:5.1f}s  med_out_tok {out}")
