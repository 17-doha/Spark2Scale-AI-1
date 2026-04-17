"""
Local smoke test for the BMC workflow — loads the three sample JSON files
sitting next to this script and runs the compiled graph.

Run with:  venv\\Scripts\\python -m app.graph.BMC.Mock_input
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from .workflow import bmc_app


HERE = Path(__file__).parent
MARKET_RESEARCH_PATH = HERE / "market_research.json"
EVALUATION_PATH = HERE / "evaluation.json"
RECOMMENDATION_PATH = HERE / "recommendation.json"


def _load_json(path: Path) -> dict:
    if not path.exists():
        print(f"[WARN] Missing file: {path.name} — passing empty dict.")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


async def main():
    market_research = _load_json(MARKET_RESEARCH_PATH)
    evaluation = _load_json(EVALUATION_PATH)
    recommendation = _load_json(RECOMMENDATION_PATH)

    # The samples are independent; pull whatever name/description we can.
    mr_unwrapped = market_research.get("data", market_research) if isinstance(market_research, dict) else {}
    idea_name = (
        mr_unwrapped.get("idea_name")
        or (recommendation.get("insights") or {}).get("company_name")
        or "Sample Startup"
    )
    idea_description = (
        recommendation.get("company_context")
        or (mr_unwrapped.get("opportunity_analysis") or {}).get("recommendation")
        or idea_name
    )

    state = {
        "idea_name": idea_name,
        "idea_description": idea_description,
        "region": "Global",
        "market_research": market_research,
        "evaluation": evaluation,
        "recommendation": recommendation,
    }

    print(f"[INFO] Running BMC for: {idea_name}")
    result = await bmc_app.ainvoke(state)

    canvas = result.get("business_model_canvas")
    if canvas:
        print(json.dumps({"business_model_canvas": canvas}, indent=2, ensure_ascii=False))
    else:
        print("[ERROR] No canvas produced.")
    if result.get("errors"):
        print("\nERRORS:", result["errors"])


if __name__ == "__main__":
    asyncio.run(main())
