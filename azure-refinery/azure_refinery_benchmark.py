#!/usr/bin/env python3
"""EDEN Azure LLM refinery benchmark.

Calls Azure OpenAI Responses API, applies a deterministic refinery envelope to
input/output records, hashes every record, and emits an auditable Merkle root.
No secrets are written to output.
"""
import concurrent.futures as cf
import hashlib, json, os, statistics, time, urllib.request, urllib.error
from pathlib import Path

ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
KEY = os.environ["AZURE_OPENAI_API_KEY"]
MODEL = os.environ["AZURE_OPENAI_DEPLOYMENT"]
N = int(os.getenv("EDEN_REQUESTS", "100"))
CONCURRENCY = int(os.getenv("EDEN_CONCURRENCY", "8"))
MAX_OUTPUT = int(os.getenv("EDEN_MAX_OUTPUT_TOKENS", "96"))
OUT = Path(os.getenv("EDEN_OUTPUT_DIR", "azure-refinery/results"))
OUT.mkdir(parents=True, exist_ok=True)

# Public, deterministic workload generator. Every prompt is reproducible from
# this source file + request index; no private benchmark data is required.
def prompt_for(i: int) -> str:
    a = (i * 7919 + 104729) % 1000003
    b = (i * 15485863 + 32452843) % 10000019
    return (
        "Independent verification workload. Return STRICT JSON with keys "
        "index, checksum, classification, summary. "
        f"index={i}; a={a}; b={b}; checksum={(a*b + i) % 2147483647}. "
        "classification must be KEEP, STRUCTURE, DETAIL, or VOID. "
        "summary must be <= 12 words."
    )

def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def sha(obj):
    return hashlib.sha256(canon(obj)).hexdigest()

def refinery_envelope(i, prompt, response_text):
    # Deterministic evidence envelope; this does not claim semantic correctness.
    return {
        "schema": "eden.refinery.azure.v1",
        "index": i,
        "input_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "output_sha256": hashlib.sha256(response_text.encode()).hexdigest(),
        "input_bytes": len(prompt.encode()),
        "output_bytes": len(response_text.encode()),
    }

def call_one(i):
    prompt = prompt_for(i)
    payload = {"model": MODEL, "input": prompt, "max_output_tokens": MAX_OUTPUT}
    req = urllib.request.Request(
        ENDPOINT + "/openai/v1/responses",
        data=json.dumps(payload).encode(),
        headers={"Content-Type":"application/json", "api-key":KEY},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
        elapsed = time.perf_counter() - t0
        obj = json.loads(raw)
        text = obj.get("output_text")
        if text is None:
            parts=[]
            for item in obj.get("output",[]):
                for c in item.get("content",[]):
                    if c.get("type") in ("output_text","text") and c.get("text"):
                        parts.append(c["text"])
            text="\n".join(parts)
        usage = obj.get("usage", {}) or {}
        env = refinery_envelope(i, prompt, text or "")
        rec = {
            **env,
            "ok": True,
            "latency_s": elapsed,
            "azure_response_id": obj.get("id"),
            "usage": usage,
            "record_sha256": "",
        }
        rec["record_sha256"] = sha({k:v for k,v in rec.items() if k != "record_sha256"})
        return rec
    except Exception as e:
        elapsed=time.perf_counter()-t0
        rec={
            "schema":"eden.refinery.azure.v1", "index":i, "ok":False,
            "latency_s":elapsed, "error":type(e).__name__,
            "input_sha256":hashlib.sha256(prompt.encode()).hexdigest(),
            "record_sha256":""
        }
        rec["record_sha256"] = sha({k:v for k,v in rec.items() if k != "record_sha256"})
        return rec

def merkle_root(hex_leaves):
    if not hex_leaves:
        return hashlib.sha256(b"").hexdigest()
    level=[bytes.fromhex(x) for x in hex_leaves]
    while len(level)>1:
        if len(level)%2: level.append(level[-1])
        level=[hashlib.sha256(level[j]+level[j+1]).digest() for j in range(0,len(level),2)]
    return level[0].hex()

def main():
    started=time.time()
    with cf.ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        records=list(ex.map(call_one, range(N)))
    records.sort(key=lambda r:r["index"])
    jsonl=OUT/"records.jsonl"
    with jsonl.open("w", encoding="utf-8") as f:
        for r in records: f.write(json.dumps(r,sort_keys=True)+"\n")
    ok=[r for r in records if r["ok"]]
    lat=[r["latency_s"] for r in ok]
    total_in=sum(int((r.get("usage") or {}).get("input_tokens",0) or 0) for r in ok)
    total_out=sum(int((r.get("usage") or {}).get("output_tokens",0) or 0) for r in ok)
    manifest={
        "schema":"eden.azure.benchmark.manifest.v1",
        "model":MODEL,
        "endpoint_host":urllib.parse.urlparse(ENDPOINT).hostname,
        "requests_requested":N,
        "requests_succeeded":len(ok),
        "requests_failed":N-len(ok),
        "concurrency":CONCURRENCY,
        "max_output_tokens":MAX_OUTPUT,
        "input_tokens_reported":total_in,
        "output_tokens_reported":total_out,
        "wall_seconds":time.time()-started,
        "latency_mean_s":statistics.mean(lat) if lat else None,
        "latency_p95_s":sorted(lat)[min(len(lat)-1,int(len(lat)*.95))] if lat else None,
        "merkle_root_sha256":merkle_root([r["record_sha256"] for r in records]),
        "records_file_sha256":hashlib.sha256(jsonl.read_bytes()).hexdigest(),
        "claim_class":"MEASURED" if ok else "CONFIGURED_NOT_MEASURED",
    }
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print(json.dumps(manifest,indent=2,sort_keys=True))
    if not ok: raise SystemExit(2)

if __name__ == "__main__":
    main()
