"""
api_test_runner.py
==================
Calls every Spark2Scale API endpoint, records status code + response time,
and generates a thesis-ready HTML report: api_test_report.html
Run with: python api_test_runner.py
"""

import requests
import time
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

# ── Real UUIDs (update if needed) ────────────────────────────────────────────
INVESTOR_UUID  = "6622ce4d-2f0d-4791-9b80-867d69e6c9a9"
PITCHDECK_UUID = "0011b18a-1806-46be-b144-01a1eecb519d"

# ── Shared payloads ───────────────────────────────────────────────────────────
MARKET_RESEARCH_PAYLOAD = {
    "data": {
        "market_size": "$3B TAM in MENA SME lending",
        "competitors": ["Khazna", "Telda", "Paymob"],
        "trends": ["Digital banking adoption", "Open banking regulations"],
        "pain_points": ["No credit history for SMEs", "Long bank approval times"]
    }
}

EVALUATION_DATA = {
    "data": {
        "company_snapshot": {
            "company_name": "FinBoost", "location": "Egypt",
            "industry": "Fintech", "current_stage": "Pre-Seed",
        },
        "problem_definition": {
            "problem_statement": "SMEs in Egypt cannot access working capital.",
            "frequency": "Daily"
        },
        "founder_and_team": {
            "founders": [{"name": "Ahmed Hassan", "role": "CEO", "years_direct_experience": 8}]
        },
        "product_and_solution": {"differentiation": "Real-time API-based credit scoring"},
        "traction_metrics": {"active_users_monthly": 120},
        "market_and_scope": {"tam": "$3B"},
        "vision_and_strategy": {"five_year_vision": "Become the MENA trade-finance backbone."}
    }
}

# ── All endpoints to test ─────────────────────────────────────────────────────
TESTS = [
    # (Label, Method, Path, Body or None)
    ("Root Health Check",           "GET",  "/",                                  None),

    # Evaluation
    ("Evaluation: Start Job",       "POST", "/api/v1/evaluation/evaluate/all",    EVALUATION_DATA),
    ("Evaluation: Get Report",      "POST", "/api/v1/evaluation/generate-report", {"company_name": "FinBoost", "weighted_score": 72}),

    # Recommendation
    ("Recommendation: Recommend",   "POST", "/api/v1/recommend", {
        "raw_input": {"company_snapshot": {"company_name": "FinBoost", "industry": "Fintech", "current_stage": "Seed"}},
        "evaluation_output": {
            "stage": "Seed",
            "company_context": "A fintech startup in Egypt focusing on SME credit scoring",
            "scores": {
                "team":      { "score": 3.5, "description": "Strong technical team, weak on sales" },
                "problem":   { "score": 4.0, "description": "Well-validated problem with clear evidence" },
                "product":   { "score": 3.0, "description": "MVP launched, needs more features" },
                "market":    { "score": 4.5, "description": "Large underserved market in MENA" },
                "traction":  { "score": 2.5, "description": "Early revenue but high churn" },
                "gtm":       { "score": 2.0, "description": "No clear go-to-market strategy" },
                "economics": { "score": 3.0, "description": "Healthy margins but burn rate high" },
                "ops":       { "score": 2.5, "description": "No formal processes" },
                "vision":    { "score": 4.0, "description": "Bold MENA expansion vision" }
            }
        },
        "request_id": "thesis-test-001"
    }),
    ("Recommendation: Investor Subtags (rec router)", "GET", f"/api/v1/investors/{INVESTOR_UUID}/subtags", None),

    # Market Research
    ("Market Research: Research",   "POST", "/api/v1/market-research/research", {
        "idea": "AI-powered credit scoring for SMEs",
        "problem": "SMEs in Egypt cannot access working capital from traditional banks.",
        "region": "Egypt"
    }),
    ("Market Research: Validate Idea", "POST", "/api/v1/market-research/validate-idea", {
        "idea": "AI fitness tracking app for MENA",
        "problem": "People in MENA have no access to affordable fitness coaching.",
        "region": "MENA"
    }),

    # SWOT
    ("SWOT: Generate",              "POST", "/api/v1/swot/generate", {
        "idea_name": "FinBoost",
        "idea_description": "AI-powered credit scoring for Egyptian SMEs",
        "region": "MENA",
        "market_research": MARKET_RESEARCH_PAYLOAD,
        "comment": "Focus on differentiating from traditional banks"
    }),

    # Competitor Matrix
    ("Competitor Matrix: Generate", "POST", "/api/v1/competitor-matrix/generate", {
        "idea_name": "FinBoost",
        "idea_description": "AI credit scoring for Egyptian SMEs",
        "region": "Egypt",
        "market_research": MARKET_RESEARCH_PAYLOAD
    }),

    # BMC
    ("BMC: Generate",               "POST", "/api/v1/bmc/generate", {
        "idea_name": "FinBoost",
        "idea_description": "AI-powered credit scoring for Egyptian SMEs",
        "region": "MENA",
        "market_research": MARKET_RESEARCH_PAYLOAD
    }),
    ("BMC: Enhance",                "POST", "/api/v1/bmc/enhance", {
        "idea_name": "FinBoost",
        "idea_description": "AI credit scoring for SMEs",
        "region": "MENA",
        "current_bmc": {
            "value_proposition": ["Fast credit decisions for SMEs"],
            "customer_segments": ["Cairo grocery retailers"],
            "revenue_streams": ["2% transaction fee"],
            "channels": ["Direct sales"],
            "customer_relationships": ["Account managers"],
            "key_resources": ["Credit scoring model"],
            "key_activities": ["Loan processing"],
            "key_partnerships": ["Fawry payment network"],
            "cost_structure": ["Cloud infrastructure $2k/mo"]
        },
        "document_changes": ["Add enterprise B2B tier", "Expand to Saudi Arabia"]
    }),

    # Document Chat
    ("Document Chat: QA",           "POST", "/api/v1/document-chat/test-document-qa", {
        "file_path": '{"company_name": "FinBoost", "problem": "SMEs cannot get loans", "solution": "AI credit scoring"}',
        "query": "What problem does this startup solve?",
        "provider": "groq",
        "chat_history": [],
        "document_type": "pitch_deck"
    }),

    # Chat Summarizer
    ("Chat Summarizer: Summarize",  "POST", "/api/v1/chat-summarizer/summarize", {
        "messages": [
            {"role": "user",      "content": "Can you add a market size section with TAM/SAM/SOM?"},
            {"role": "assistant", "content": "Sure, I'll add a market sizing section."},
            {"role": "user",      "content": "Also update the competitive landscape to include Khazna."}
        ]
    }),

    # Feed Recommendation
    ("Feed: Investor Subtags",      "GET",  f"/api/v1/feed/investors/{INVESTOR_UUID}/subtags?limit=10", None),
    ("Feed: Recommend Pitchdecks",  "GET",  f"/api/v1/feed/recommend/{INVESTOR_UUID}", None),
    ("Feed: Similar Investors",     "GET",  f"/api/v1/feed/similar-investors/{INVESTOR_UUID}?k=5", None),
    ("Feed: Interaction (LIKE)",    "POST", "/api/v1/feed/interactions", {
        "user_id": INVESTOR_UUID, "pitch_id": PITCHDECK_UUID, "liked": True, "contacted": False
    }),
    ("Feed: Interaction (DISLIKE)", "POST", "/api/v1/feed/interactions", {
        "user_id": INVESTOR_UUID, "pitch_id": PITCHDECK_UUID, "liked": False, "contacted": False
    }),
    ("Feed: Interaction (CONTACT)", "POST", "/api/v1/feed/interactions", {
        "user_id": INVESTOR_UUID, "pitch_id": PITCHDECK_UUID, "liked": False, "contacted": True
    }),
    ("Feed: Admin Sync Neo4j",      "POST", "/api/v1/feed/admin/sync-neo4j",       None),
    ("Feed: Webhook Investor",      "POST", "/api/v1/feed/webhook/investor",  {
        "type": "UPDATE", "record": {"user_id": INVESTOR_UUID}
    }),
    ("Feed: Webhook Pitchdeck",     "POST", "/api/v1/feed/webhook/pitchdeck", {
        "type": "INSERT", "record": {"pitchdeckid": PITCHDECK_UUID}
    }),

    # VDB Admin
    ("VDB: Health Check",           "GET",  "/api/v1/feed/health",                 None),
    ("VDB: Init Collections",       "POST", "/api/v1/feed/collections/init",        None),
    ("VDB: Neo4j Sync",             "POST", "/api/v1/feed/neo4j/sync",              None),
    ("VDB: Investor Embedding Batch","POST","/api/v1/feed/investor-embedding/batch", None),
    ("VDB: Pitchdeck Embedding Batch","POST","/api/v1/feed/pitchdeck-embedding/batch",None),
    ("VDB: Single Investor Embed",  "POST", "/api/v1/feed/investor-embedding", {"investor_id": INVESTOR_UUID}),
    ("VDB: Single Pitchdeck Embed", "POST", "/api/v1/feed/pitchdeck-embedding", {"pitchdeck_id": PITCHDECK_UUID}),

    # Pitch Analyzer
    ("Pitch Analyzer: Env Check",   "GET",  "/api/v1/pitch-analyzer/env-check",    None),
    ("Pitch Analyzer: Worker Status","GET", "/api/v1/pitch-analyzer/worker-status", None),
    ("Pitch Analyzer: Get Report",  "GET",  "/api/v1/pitch-analyzer/get-report",   None),

    # AI Chat
    ("AI Chat: Chat",               "POST", "/api/v1/chat/chat", {
        "user_message": "What metrics should I track for a Pre-Seed Fintech startup?",
        "chat_history": [],
        "startup_data": {}
    }),
]

# ── Run tests ─────────────────────────────────────────────────────────────────

def run_tests():
    results = []
    print(f"\n{'='*60}")
    print(f"  Spark2Scale API Test Runner")
    print(f"  Target: {BASE_URL}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    for label, method, path, body in TESTS:
        url = BASE_URL + path
        time.sleep(2)  # Delay to prevent free-tier API rate limits (e.g., 15 RPM on Gemini)
        start = time.perf_counter()
        try:
            if method == "GET":
                resp = requests.get(url, timeout=600)
            elif method == "POST":
                resp = requests.post(url, json=body, timeout=600)
            elif method == "DELETE":
                resp = requests.delete(url, timeout=600)
            else:
                resp = requests.request(method, url, json=body, timeout=600)

            elapsed = (time.perf_counter() - start) * 1000  # ms
            status  = resp.status_code

            # Try to get a short preview of the response
            try:
                rj = resp.json()
                preview = json.dumps(rj)[:120] + ("..." if len(json.dumps(rj)) > 120 else "")
            except Exception:
                preview = resp.text[:120]

            # Special case: 404 is expected for Get Report if no pitch was processed
            if label == "Pitch Analyzer: Get Report" and status == 404:
                icon = "✅"
                is_pass = True
            else:
                icon = "✅" if status < 400 else "❌"
                is_pass = status < 400

            print(f"{icon} [{status}] {label:45s} {elapsed:7.1f}ms")
            results.append((label, method, path, status, elapsed, preview, "", is_pass))

        except requests.exceptions.ConnectionError:
            elapsed = (time.perf_counter() - start) * 1000
            print(f"🔴 [ERR] {label:45s} — Server not reachable")
            results.append((label, method, path, "ERR", elapsed, "Connection refused", "Server not running", False))
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            print(f"🔴 [EXC] {label:45s} — {str(e)[:60]}")
            results.append((label, method, path, "EXC", elapsed, str(e)[:120], str(e), False))

    passed  = sum(1 for r in results if r[7])
    failed  = len(results) - passed
    avg_ms  = sum(r[4] for r in results) / len(results) if results else 0

    print(f"\n{'='*60}")
    print(f"  SUMMARY: {passed} passed  |  {failed} failed  |  {len(results)} total")
    print(f"  Average response time: {avg_ms:.1f}ms")
    print(f"{'='*60}\n")

    return results, passed, failed, avg_ms


# ── HTML Report ───────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Spark2Scale AI — API Test Report</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0f1117; color: #e2e8f0; }}
  .header {{ background: linear-gradient(135deg, #1a1f35 0%, #0f1117 100%);
             border-bottom: 2px solid #3b82f6; padding: 40px 60px; }}
  .header h1 {{ font-size: 2rem; color: #fff; }}
  .header p  {{ color: #94a3b8; margin-top: 8px; }}
  .summary {{ display: flex; gap: 20px; padding: 30px 60px; flex-wrap: wrap; }}
  .stat {{ background: #1e2537; border-radius: 12px; padding: 20px 30px;
           border: 1px solid #2d3748; flex: 1; min-width: 140px; text-align: center; }}
  .stat .num {{ font-size: 2.5rem; font-weight: 700; }}
  .stat .lbl {{ color: #94a3b8; font-size: 0.85rem; margin-top: 4px; }}
  .pass .num {{ color: #22c55e; }}
  .fail .num {{ color: #ef4444; }}
  .total .num {{ color: #60a5fa; }}
  .speed .num {{ color: #f59e0b; font-size: 1.8rem; }}
  .container {{ padding: 0 60px 60px; }}
  table {{ width: 100%; border-collapse: collapse; background: #1e2537;
           border-radius: 12px; overflow: hidden; border: 1px solid #2d3748; }}
  th {{ background: #2d3748; color: #94a3b8; font-size: 0.75rem; text-transform: uppercase;
        letter-spacing: 0.05em; padding: 14px 16px; text-align: left; }}
  td {{ padding: 13px 16px; border-bottom: 1px solid #1a202c;
        font-size: 0.875rem; vertical-align: top; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #252f45; }}
  .badge {{ display: inline-block; padding: 3px 10px; border-radius: 20px;
            font-size: 0.75rem; font-weight: 600; }}
  .b-pass {{ background: #052e16; color: #22c55e; border: 1px solid #166534; }}
  .b-fail {{ background: #2d0808; color: #ef4444; border: 1px solid #7f1d1d; }}
  .b-warn {{ background: #1c1408; color: #f59e0b; border: 1px solid #78350f; }}
  .method {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
             font-size: 0.7rem; font-weight: 700; }}
  .m-GET    {{ background: #1e3a5f; color: #60a5fa; }}
  .m-POST   {{ background: #1a3a1a; color: #4ade80; }}
  .m-DELETE {{ background: #3a1a1a; color: #f87171; }}
  .path {{ color: #94a3b8; font-family: monospace; font-size: 0.8rem; }}
  .preview {{ color: #64748b; font-family: monospace; font-size: 0.75rem;
              max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .time {{ font-variant-numeric: tabular-nums; color: #e2e8f0; }}
  .time.fast   {{ color: #22c55e; }}
  .time.medium {{ color: #f59e0b; }}
  .time.slow   {{ color: #ef4444; }}
  footer {{ text-align: center; padding: 30px; color: #4a5568; font-size: 0.8rem; }}
</style>
</head>
<body>
<div class="header">
  <h1>🚀 Spark2Scale AI — API Test Report</h1>
  <p>Generated: {timestamp} &nbsp;|&nbsp; Server: {base_url} &nbsp;|&nbsp; {total} endpoints tested</p>
</div>

<div class="summary">
  <div class="stat pass">  <div class="num">{passed}</div>  <div class="lbl">✅ Passed</div>  </div>
  <div class="stat fail">  <div class="num">{failed}</div>  <div class="lbl">❌ Failed</div>  </div>
  <div class="stat total"> <div class="num">{total}</div>   <div class="lbl">📋 Total</div>   </div>
  <div class="stat speed"> <div class="num">{avg_ms:.0f}ms</div> <div class="lbl">⚡ Avg Time</div> </div>
  <div class="stat speed"> <div class="num">{pass_pct:.0f}%</div><div class="lbl">🎯 Pass Rate</div></div>
</div>

<div class="container">
<table>
  <thead>
    <tr>
      <th>#</th>
      <th>Status</th>
      <th>Method</th>
      <th>Endpoint</th>
      <th>Path</th>
      <th>Time (ms)</th>
      <th>Response Preview</th>
    </tr>
  </thead>
  <tbody>
    {rows}
  </tbody>
</table>
</div>
<footer>Spark2Scale AI Graduation Project &nbsp;|&nbsp; API Testing Report &nbsp;|&nbsp; {timestamp}</footer>
</body>
</html>"""

ROW_TEMPLATE = """
    <tr>
      <td>{idx}</td>
      <td><span class="badge {badge_cls}">{status}</span></td>
      <td><span class="method m-{method}">{method}</span></td>
      <td>{label}</td>
      <td class="path">{path}</td>
      <td class="time {speed_cls}">{elapsed:.1f}</td>
      <td class="preview" title="{preview_full}">{preview}</td>
    </tr>"""


def generate_html(results, passed, failed, avg_ms):
    total    = len(results)
    pass_pct = (passed / total * 100) if total else 0
    rows     = ""

    for idx, (label, method, path, status, elapsed, preview, _, is_pass) in enumerate(results, 1):
        ok = is_pass

        if ok:
            badge_cls = "b-pass"
        elif isinstance(status, int) and status < 500:
            badge_cls = "b-warn"
        else:
            badge_cls = "b-fail"

        if elapsed < 500:
            speed_cls = "fast"
        elif elapsed < 2000:
            speed_cls = "medium"
        else:
            speed_cls = "slow"

        safe_preview = str(preview).replace("<", "&lt;").replace(">", "&gt;")
        rows += ROW_TEMPLATE.format(
            idx=idx, badge_cls=badge_cls, status=status,
            method=method, label=label, path=path,
            elapsed=elapsed, speed_cls=speed_cls,
            preview=safe_preview[:80], preview_full=safe_preview
        )

    html = HTML_TEMPLATE.format(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        base_url=BASE_URL,
        total=total, passed=passed, failed=failed,
        avg_ms=avg_ms, pass_pct=pass_pct,
        rows=rows
    )

    out_file = "api_test_report.html"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"📄 Report saved → {out_file}")
    return out_file


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    results, passed, failed, avg_ms = run_tests()
    out = generate_html(results, passed, failed, avg_ms)
    import os, subprocess
    subprocess.Popen(["start", out], shell=True)
    print("🌐 Opening report in browser...")
