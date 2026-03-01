"""
Standalone smoke-test for get_t5_insight / t5_insight_node.
Run from the project root:
    .\\venv\\Scripts\\activate
    python test_t5_node.py
"""

import asyncio
import time
from dotenv import load_dotenv

# .env MUST be loaded before llm.py is imported (it reads HF_TOKEN at module level)
load_dotenv()

# Option 1: test get_t5_insight directly (the canonical function in app.core.llm)
from app.core.llm import get_t5_insight

# Option 2: test the full LangGraph node end-to-end
from app.graph.evaluation_agent.node import t5_insight_node

SAMPLE_PROMPT = (
    "Evaluate the following startup context: "
    "Company: Spark2Scale, Stage: Pre-Seed. "
    "Problem: Early-stage founders lack a structured system to validate "
    "ideas and reach investors."
)

SAMPLE_STATE = {
    "user_data": {
        "startup_evaluation": {
            "company_snapshot": {"company_name": "Spark2Scale", "current_stage": "Pre-Seed"},
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
    print("=" * 60)

    # --- Test 1: direct get_t5_insight call ---
    print("Test 1: app.core.llm.get_t5_insight()")
    print("=" * 60)
    start = time.time()
    result = await get_t5_insight(SAMPLE_PROMPT)
    print(f"⏱  {time.time() - start:.1f}s\n✅ Result:\n{result}")
    print("=" * 60)

    # --- Test 2: full node ---
    print("\nTest 2: t5_insight_node(state)")
    print("=" * 60)
    start = time.time()
    state_result = await t5_insight_node(SAMPLE_STATE)
    print(f"⏱  {time.time() - start:.1f}s\n✅ t5_deep_insight:\n{state_result.get('t5_deep_insight', '<empty>')}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
