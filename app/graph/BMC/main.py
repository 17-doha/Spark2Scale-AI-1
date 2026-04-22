"""
Standalone entry point for the BMC agent.

Runs the workflow against the three sample JSON files
(`market_research.json`, `evaluation.json`, `recommendation.json`) sitting
next to this script.

Run from anywhere with either:
    venv\\Scripts\\python app\\graph\\BMC\\main.py
    cd app/graph/BMC && python main.py
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Make `app.*` importable no matter where this script is launched from.
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]  # .../Spark2Scale-AI-1
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from app.graph.BMC.workflow import bmc_app  # noqa: E402
from app.graph.BMC.renderer import render_bmc_image  # noqa: E402

MARKET_RESEARCH_PATH = HERE / "market_research.json"
EVALUATION_PATH = HERE / "evaluation.json"
RECOMMENDATION_PATH = HERE / "recommendation.json"
OUTPUT_DIR = PROJECT_ROOT / "output" / "bmc"


def _load_json(path: Path) -> dict:
    if not path.exists():
        print(f"[WARN] Missing file: {path.name} — passing empty dict.")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


async def run() -> None:
    market_research = _load_json(MARKET_RESEARCH_PATH)
    evaluation = _load_json(EVALUATION_PATH)
    recommendation = _load_json(RECOMMENDATION_PATH)

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
        payload = {"business_model_canvas": canvas}
        print(json.dumps(payload, indent=2, ensure_ascii=False))

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / "bmc.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"\n[SAVED] {out_path}")

        img_path = render_bmc_image(canvas, idea_name, OUTPUT_DIR / "bmc.png")
        print(f"[SAVED] {img_path}")
    else:
        print("[ERROR] No canvas produced.")
    if result.get("errors"):
        print("\nERRORS:", result["errors"])


if __name__ == "__main__":
    asyncio.run(run())
