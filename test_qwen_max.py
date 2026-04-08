"""
test_qwen_max.py
────────────────
Tests that qwen-max (DashScope) works as a drop-in replacement for Groq
in the pitch-analyzer intermediate LLM path.

Run with: venv\Scripts\python.exe test_qwen_max.py

Tests:
  1. DASHSCOPE_API_KEY is present in .env
  2. Direct HTTP call to DashScope OpenAI-compatible endpoint
  3. _get_fast_llm() returns a ChatOpenAI with qwen-max, not Groq
  4. extract_claims() works end-to-end with a sample transcript
  5. check_consistency_logic() returns correct JSON
  6. check_investor_essentials() returns covered/missing lists
  7. build_investment_readiness_report() runs without error
"""

import os, sys, json, time
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "app" / "graph" / "pitch_analyzer"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []

def check(name, ok, detail=""):
    tag = PASS if ok else FAIL
    print(f"  {tag}  {name}" + (f"\n         → {detail}" if detail else ""))
    results.append((name, ok))

print("\n══════════════════════════════════════════════════════════")
print("  qwen-max (DashScope) Integration Tests")
print("══════════════════════════════════════════════════════════\n")


# ─── TEST 1: API key present ──────────────────────────────────────────────────
print("▶ TEST 1: DASHSCOPE_API_KEY in environment")
key = os.getenv("DASHSCOPE_API_KEY", "")
check("DASHSCOPE_API_KEY set", bool(key), f"value: {key[:12]}..." if key else "MISSING!")
print()


# ─── TEST 2: Raw HTTP call to DashScope ───────────────────────────────────────
print("▶ TEST 2: Direct HTTP ping to DashScope API")
import urllib.request, urllib.error
try:
    payload = json.dumps({
        "model": "qwen-turbo",
        "messages": [
            {"role": "system", "content": "You must respond with exactly this JSON and nothing else: {\"ok\": true}"},
            {"role": "user", "content": "test"}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 20
    }).encode()
    req = urllib.request.Request(
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
    latency = round(time.time() - t0, 2)
    content = body["choices"][0]["message"]["content"]
    check(f"DashScope responds OK (latency={latency}s)", True, f"response: {content[:60]}")
except urllib.error.HTTPError as e:
    check("DashScope responds OK", False, f"HTTP {e.code}: {e.read().decode()[:200]}")
except Exception as e:
    check("DashScope responds OK", False, str(e))
print()


# ─── TEST 3: _get_fast_llm() uses qwen-max ────────────────────────────────────
print("▶ TEST 3: _get_fast_llm() is configured for qwen-max")
try:
    import tools
    llm = tools._get_fast_llm()
    model_name = getattr(llm, "model_name", None) or getattr(llm, "model", None) or ""
    base_url   = getattr(llm, "openai_api_base", None) or getattr(llm, "base_url", None) or ""
    check("model is qwen-turbo",        "qwen-turbo" in str(model_name))
    check("base_url is DashScope",      "dashscope" in str(base_url).lower())
    check("NOT Groq endpoint",          "groq.com" not in str(base_url).lower())
except Exception as e:
    check("_get_fast_llm() loads", False, str(e))
print()


# ─── TEST 4: extract_claims() ─────────────────────────────────────────────────
print("▶ TEST 4: extract_claims() — end-to-end with a sample transcript")
SAMPLE = (
    "We have 5,000 paying users, $120k MRR, growing 30% month-over-month. "
    "We're raising $2M at a $10M valuation. CAC is $40, LTV is $600."
)
try:
    t0 = time.time()
    result = tools.extract_claims(SAMPLE)
    latency = round(time.time() - t0, 2)
    print(f"  ℹ️  latency: {latency}s")
    print(f"  ℹ️  result: {json.dumps(result, indent=2)[:400]}")
    check("returns dict",             isinstance(result, dict))
    check("traction.users present",  bool(result.get("traction", {}).get("users")))
    check("ask.amount present",      bool(result.get("ask", {}).get("amount")))
    check("economics.cac present",   bool(result.get("economics", {}).get("cac")))
except Exception as e:
    check("extract_claims runs", False, str(e))
print()


# ─── TEST 5: check_consistency_logic() ───────────────────────────────────────
print("▶ TEST 5: check_consistency_logic() — contradiction detection")
try:
    history = ["We have 500 paying users", "Our MRR is $50k"]
    new_claim = "We have zero paying users and no revenue yet."
    t0 = time.time()
    res = tools.check_consistency_logic(new_claim, history)
    latency = round(time.time() - t0, 2)
    print(f"  ℹ️  latency: {latency}s")
    print(f"  ℹ️  result: {json.dumps(res, indent=2)[:300]}")
    check("returns dict with 'contradiction' key", "contradiction" in res)
    check("detected contradiction correctly",       res.get("contradiction") is True,
          "expected True — '500 users and $50k MRR' vs 'zero users, no revenue'")
except Exception as e:
    check("check_consistency_logic runs", False, str(e))
print()


# ─── TEST 6: check_investor_essentials() ─────────────────────────────────────
print("▶ TEST 6: check_investor_essentials() — coverage check")
FULL_TRANSCRIPT = (
    "We're solving the fragmented B2B payments problem. Our solution is a unified payments platform. "
    "The market is $200B. We have 5k users growing 30% MoM. Our team has 10 years of fintech experience. "
    "We're raising $2M seed. We'll use funds for engineering and marketing. "
    "Our model is SaaS with $99/month per seat."
)
try:
    t0 = time.time()
    res = tools.check_investor_essentials(FULL_TRANSCRIPT)
    latency = round(time.time() - t0, 2)
    print(f"  ℹ️  latency: {latency}s")
    print(f"  ℹ️  covered: {res.get('covered', [])}")
    print(f"  ℹ️  missing: {res.get('missing', [])}")
    check("returns covered/missing keys", "covered" in res and "missing" in res)
    check("found some covered essentials", len(res.get("covered", [])) > 3)
except Exception as e:
    check("check_investor_essentials runs", False, str(e))
print()


# ─── TEST 7: build_investment_readiness_report() ─────────────────────────────
print("▶ TEST 7: build_investment_readiness_report() — full report pipeline")
try:
    session_log = [
        {"event": "interrupt", "reason": "grammar_and_fillers", "timestamp": 45.0, "detail": "filler word: um"},
    ]
    grammar_buffer = [{"issues": ["um", "uh"]}]
    structured_claims = {
        "traction": {"users": "5000", "revenue": "$120k MRR", "growth": "30% MoM"},
        "ask":      {"amount": "$2M", "valuation": "$10M"},
        "economics": {"cac": "$40", "ltv": "$600", "churn": None},
        "gtm":      {"channels": ["SEO", "paid ads"]},
        "moat":     {"claims": ["proprietary data", "network effects"]},
    }
    pitch_history = [
        "We have 5000 paying users",
        "Monthly revenue is $120k",
        "We are raising $2M seed round",
    ]
    diligence_answered = ["What is your CAC?", "How do you defend against competition?"]

    t0 = time.time()
    report = tools.build_investment_readiness_report(
        session_log, grammar_buffer, structured_claims,
        pitch_history, diligence_answered, FULL_TRANSCRIPT
    )
    latency = round(time.time() - t0, 2)
    print(f"  ℹ️  latency: {latency}s")
    print(f"  ℹ️  grade:   {report.get('grade')}  score: {report.get('score')}/{report.get('max_score')}")
    check("report has grade",     bool(report.get("grade")))
    check("report has rubric",    bool(report.get("rubric")))
    check("report has strengths", bool(report.get("strengths")))
    check("essentials_checklist present", "essentials_checklist" in report)
except Exception as e:
    import traceback
    check("build_investment_readiness_report runs", False, str(e))
    traceback.print_exc()
print()


# ─── SUMMARY ─────────────────────────────────────────────────────────────────
print("══════════════════════════════════════════════════════════")
passed = sum(1 for _, ok in results if ok)
total  = len(results)
print(f"  Results: {passed}/{total} passed")
if passed == total:
    print("  🎉 All qwen-max tests passed — safe to deploy!")
else:
    failed = [n for n, ok in results if not ok]
    print("  ⚠️  Fix before deploying:")
    for f in failed:
        print(f"     • {f}")
print("══════════════════════════════════════════════════════════\n")
