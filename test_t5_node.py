"""
Standalone smoke-test for t5_insight_node.
Run from the project root:
    .\\venv\\Scripts\\activate
    python test_t5_node.py
"""

import asyncio
import json
import time
from dotenv import load_dotenv

# .env MUST be loaded before helpers.py is imported (it reads HF_TOKEN at module level)
load_dotenv()

from app.graph.evaluation_agent.node import t5_insight_node
from app.graph.evaluation_agent.helpers import t5_client

# Quick sanity-check before we bother with the full async call
if t5_client is None:
    print("❌ t5_client is None — check your HF_TOKEN and that the Space is running.")
    exit(1)

print("✅ t5_client connected:", t5_client)

# ---------------------------------------------------------------------------
# Minimal fake state – only what t5_insight_node reads
# ---------------------------------------------------------------------------
SAMPLE_STATE = {
    "user_data": {
        "startup_evaluation": {
            "company_snapshot": {
                "company_name": "Spark2Scale",
                "current_stage": "Pre-Seed"
            },
            "problem_definition": {
                "problem_statement": (
                    "Early-stage founders lack a structured system to validate "
                    "ideas and reach investors."
                )
            }
        }
    }
}

async def main():
    print("\n" + "=" * 60)
    print("Running t5_insight_node with sample startup data...")
    print("=" * 60)

    start = time.time()
    result = await t5_insight_node(SAMPLE_STATE)
    elapsed = time.time() - start

    print(f"\n⏱  Took {elapsed:.1f}s")
    print("\n✅ t5_deep_insight:")
    print(result.get("t5_deep_insight", "<empty>"))
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
