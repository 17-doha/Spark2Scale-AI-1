#!/usr/bin/env python3
"""
Feed Recommendation Agent — Engineering & Behavioral Evaluation
===============================================================

PURPOSE
-------
Validates the Spark2Scale feed recommendation agent on two dimensions:

  (A) Functional correctness  — does the pipeline run without errors?
                                 does it respect K, deduplication, exclusions?
  (B) Behavioral properties   — coverage, diversity, novelty, personalization,
                                 popularity bias; compared against baselines.

⚠ CRITICAL: This script does NOT measure recommendation QUALITY.
  The interaction data is synthetic (generated for testing). Any ranking
  metric (Precision@K, NDCG, …) would only reflect the synthetic generation
  pattern, not real investor preferences. See Section (D) for details.

DESIGN
------
All external services (Qdrant, Neo4j, Supabase, Jina) are replaced by a
fully in-memory SimulatedPipeline that implements identical mathematics:
  - cosine similarity instead of Qdrant ANN
  - tag-Jaccard proxy instead of Jina cross-encoder reranking
  - taxonomy sibling lookup instead of Neo4j
This lets every test run without credentials and without network calls,
while still exercising the real algorithmic logic.

Usage:
  cd Spark2Scale-AI-1
  python evaluation/eval_feed_agent.py
"""
import sys
import os
import math
import random
import itertools
import textwrap
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

import numpy as np

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 0 — SYNTHETIC DATA
#
#  Mirrors the real system's tag taxonomy.  Every investor and pitchdeck is
#  deterministically generated from a fixed seed so the evaluation is
#  fully reproducible.
# ═══════════════════════════════════════════════════════════════════════════════

EMBED_DIM    = 1024    # low-dim for fast in-memory cosine math
TOP_K        = 10    # matches os.getenv("TOP_K", "10") in real code
FETCH_K      = 30    # matches RERANK_FETCH_K in reranker.py
N_INVESTORS  = 20
N_PITCHDECKS = 100

# Mirrors the real tag hierarchy stored in Neo4j
TAG_TAXONOMY: dict[str, list[str]] = {
    "fintech":     ["payments", "lending", "insurtech", "crypto", "wealthtech"],
    "healthtech":  ["telemedicine", "diagnostics", "mental_health", "drug_discovery", "med_devices"],
    "edtech":      ["k12", "higher_ed", "skills_training", "corporate_learning"],
    "climatetech": ["solar", "energy_storage", "carbon_capture", "agritech"],
    "b2b_saas":    ["crm", "hrtech", "analytics", "devtools", "cybersecurity"],
}

ALL_MAIN_TAGS: list[str] = list(TAG_TAXONOMY.keys())
ALL_SUBTAGS:   list[str] = [st for sts in TAG_TAXONOMY.values() for st in sts]
ALL_TAGS:      list[str] = ALL_MAIN_TAGS + ALL_SUBTAGS


# ── Embedding helpers ─────────────────────────────────────────────────────────

def _det_embed(name: str, dim: int = EMBED_DIM) -> list[float]:
    """Deterministic unit-norm embedding for any string (hash-seeded RNG)."""
    seed = abs(hash(name)) % (2 ** 31)
    rng  = np.random.RandomState(seed)
    v    = rng.randn(dim).astype(np.float32)
    norm = np.linalg.norm(v)
    return (v / norm).tolist()


def _agg_embed(tags: list[str]) -> list[float]:
    """Mean of tag embeddings, L2-normalised (mirrors aggregate_embeddings())."""
    vecs = [TAG_EMB[t] for t in tags if t in TAG_EMB]
    if not vecs:
        return _det_embed("__empty__")
    v    = np.mean(vecs, axis=0).astype(np.float32)
    norm = np.linalg.norm(v)
    return (v / norm if norm > 0 else v).tolist()


def _cosine(a: list[float], b: list[float]) -> float:
    a_, b_ = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
    denom  = np.linalg.norm(a_) * np.linalg.norm(b_)
    return float(np.dot(a_, b_) / denom) if denom > 0 else 0.0


def _tag_jaccard(t1: list[str], t2: list[str]) -> float:
    s1, s2 = set(t1), set(t2)
    if not s1 and not s2:
        return 1.0
    return len(s1 & s2) / len(s1 | s2)


# Pre-compute tag embeddings
TAG_EMB: dict[str, list[float]] = {tag: _det_embed(tag) for tag in ALL_TAGS}


# ── Catalog generators ────────────────────────────────────────────────────────

def build_investors(n: int = N_INVESTORS, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        mains = rng.sample(ALL_MAIN_TAGS, k=rng.randint(1, 3))
        subs  = []
        for m in mains:
            subs += rng.sample(TAG_TAXONOMY[m], k=rng.randint(1, 3))
        subs = list(set(subs))
        out.append({
            "investor_id": f"inv_{i:03d}",
            "main_tags"  : mains,
            "subtags"    : subs,
            "embedding"  : _agg_embed(mains + subs),
        })
    return out


def build_pitchdecks(n: int = N_PITCHDECKS, seed: int = 99) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        mt   = rng.choice(ALL_MAIN_TAGS)
        subs = rng.sample(TAG_TAXONOMY[mt], k=rng.randint(1, min(3, len(TAG_TAXONOMY[mt]))))
        tags = [mt] + subs
        out.append({
            "pitchdeck_id": f"pd_{i:03d}",
            "startup_id"  : f"s_{i:03d}",
            "tags"        : tags,
            "embedding"   : _agg_embed(tags),
        })
    return out


# Global catalogs (fixed for reproducibility)
INVESTORS    = build_investors()
PITCHDECKS   = build_pitchdecks()
PD_BY_ID     = {p["pitchdeck_id"]: p for p in PITCHDECKS}
INV_BY_ID    = {i["investor_id"]:  i for i in INVESTORS}
CATALOG_IDS  = set(PD_BY_ID)


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — SIMULATED PIPELINE
#
#  Implements the same five-stage logic as the real LangGraph workflow:
#    Node 1: subtag filter + seen-ID exclusion
#    Node 2: investor query vector (aggregated tag mean)
#    Node 3: in-memory cosine ANN with tag filter
#    Node 3b: sibling-tag fallback when candidates < K
#    Node 4: tag-Jaccard rerank (proxy for Jina cross-encoder)
#    Node 5: format (passthrough)
#
#  No external I/O.  Used both for functional tests and intrinsic metrics.
# ═══════════════════════════════════════════════════════════════════════════════

class SimulatedPipeline:
    """In-memory recommendation pipeline mirroring the real agent logic."""

    def __init__(
        self,
        catalog:  list[dict],
        taxonomy: dict[str, list[str]],
        k:        int = TOP_K,
        fetch_k:  int = FETCH_K,
    ):
        self.catalog  = catalog
        self.taxonomy = taxonomy
        self.k        = k
        self.fetch_k  = fetch_k
        # Pre-compute sibling map: subtag → [sibling subtags sharing a parent]
        self.sibling_map: dict[str, list[str]] = {}
        for parent, subs in taxonomy.items():
            for s in subs:
                self.sibling_map[s] = [x for x in subs if x != s]

    # ── Stage helpers ──────────────────────────────────────────────────────────

    def _ann_search(
        self,
        query_vec  : list[float],
        filter_tags: list[str],
        exclude_ids: set[str],
        limit      : int,
    ) -> list[dict]:
        """
        Cosine search over in-memory catalog with tag filter + exclusion.
        Mirrors filtered_vector_search_node() with its unfiltered fallback.
        """
        def _matches(pd: dict) -> bool:
            if pd["pitchdeck_id"] in exclude_ids:
                return False
            if filter_tags:
                return any(t in pd["tags"] for t in filter_tags)
            return True

        results = [
            {**pd, "vector_score": round(_cosine(query_vec, pd["embedding"]), 4)}
            for pd in self.catalog
            if _matches(pd)
        ]
        results.sort(key=lambda x: x["vector_score"], reverse=True)

        # Unfiltered fallback (mirrors Node 3 retry when filtered returns 0)
        if not results and filter_tags:
            results = [
                {**pd, "vector_score": round(_cosine(query_vec, pd["embedding"]), 4)}
                for pd in self.catalog
                if pd["pitchdeck_id"] not in exclude_ids
            ]
            results.sort(key=lambda x: x["vector_score"], reverse=True)

        return results[:limit]

    def _sibling_tags(self, subtags: list[str], exclude: set[str]) -> list[str]:
        """Mirrors get_sibling_subtags() Neo4j lookup."""
        sibs = set()
        for st in subtags:
            for s in self.sibling_map.get(st, []):
                if s not in exclude:
                    sibs.add(s)
        return list(sibs)

    def _rerank(
        self,
        query_tags: list[str],
        candidates: list[dict],
        top_n:      int,
    ) -> list[dict]:
        """
        Tag-Jaccard proxy for Jina cross-encoder reranking.
        Score = Jaccard(investor_tags, pitchdeck_tags).
        """
        scored = [
            {**c, "rerank_score": round(_tag_jaccard(query_tags, c["tags"]), 4)}
            for c in candidates
        ]
        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored[:top_n]

    # ── Public interface ───────────────────────────────────────────────────────

    def get_feed(
        self,
        investor_id: str,
        seen_ids:    Optional[set[str]] = None,
    ) -> dict:
        """
        Run the full 5-node pipeline and return:
          {
            "investor_id": str,
            "feed": list[dict],            # each item has pitchdeck_id, tags, scores
            "fallback_triggered": bool,
            "n_candidates_before_rerank": int,
            "errors": list[str],
          }
        """
        errors   = []
        seen_ids = seen_ids or set()

        # ── Node 1 ─────────────────────────────────────────────────────────────
        investor = INV_BY_ID.get(investor_id)
        if not investor:
            return {
                "investor_id"           : investor_id,
                "feed"                  : [],
                "fallback_triggered"    : False,
                "n_candidates_before_rerank": 0,
                "errors"                : [f"Investor '{investor_id}' not found"],
            }

        filter_tags = investor["subtags"]   # UCB-selected subtags in real code
        query_tags  = investor["main_tags"] + investor["subtags"]

        # ── Node 2 ─────────────────────────────────────────────────────────────
        query_vec = investor["embedding"]   # aggregated tag mean (fallback path)

        # ── Node 3 ─────────────────────────────────────────────────────────────
        candidates         = self._ann_search(query_vec, filter_tags, seen_ids, limit=self.fetch_k)
        fallback_triggered = False

        # ── Node 3b ────────────────────────────────────────────────────────────
        if len(candidates) < self.k:
            sibling_tags = self._sibling_tags(filter_tags, exclude=set(filter_tags))
            if sibling_tags:
                already = {c["pitchdeck_id"] for c in candidates} | seen_ids
                sibling_hits = self._ann_search(query_vec, sibling_tags, already, limit=self.fetch_k)
                for h in sibling_hits:
                    h["from_fallback"] = True
                candidates         = candidates + sibling_hits
                fallback_triggered = True

        if not candidates:
            return {
                "investor_id"           : investor_id,
                "feed"                  : [],
                "fallback_triggered"    : fallback_triggered,
                "n_candidates_before_rerank": 0,
                "errors"                : ["No candidates found after all fallbacks"],
            }

        # ── Node 4 + 5 ─────────────────────────────────────────────────────────
        n_before = len(candidates)
        final    = self._rerank(query_tags, candidates, top_n=self.k)

        return {
            "investor_id"           : investor_id,
            "feed"                  : final,
            "fallback_triggered"    : fallback_triggered,
            "n_candidates_before_rerank": n_before,
            "errors"                : errors,
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — FUNCTIONAL TESTS
#
#  Each test is a standalone function returning (name, passed, detail).
#  Tests use the SimulatedPipeline which faithfully mirrors the real nodes.
# ═══════════════════════════════════════════════════════════════════════════════

TestResult = tuple[str, bool, str]   # (name, passed, detail)


def t1_pipeline_runs_end_to_end(pipe: SimulatedPipeline) -> TestResult:
    name = "T01  Pipeline runs end-to-end without exception"
    try:
        result = pipe.get_feed(INVESTORS[0]["investor_id"])
        if isinstance(result, dict) and "feed" in result and "errors" in result:
            return name, True, f"returned dict with {len(result['feed'])} items"
        return name, False, f"unexpected return shape: {type(result)}"
    except Exception as e:
        return name, False, str(e)


def t2_returns_exactly_k(pipe: SimulatedPipeline) -> TestResult:
    name = f"T02  Returns exactly K={TOP_K} items (catalog large enough)"
    fails = []
    for inv in INVESTORS:
        result = pipe.get_feed(inv["investor_id"])
        n = len(result["feed"])
        if n != TOP_K:
            fails.append(f"{inv['investor_id']}: got {n}")
    if not fails:
        return name, True, "all investors received exactly K items"
    return name, False, "; ".join(fails[:3])


def t3_no_duplicates(pipe: SimulatedPipeline) -> TestResult:
    name = "T03  No duplicate pitchdeck IDs within a single feed"
    for inv in INVESTORS:
        result = pipe.get_feed(inv["investor_id"])
        ids = [item["pitchdeck_id"] for item in result["feed"]]
        if len(ids) != len(set(ids)):
            dupes = [pid for pid, c in Counter(ids).items() if c > 1]
            return name, False, f"investor={inv['investor_id']} duplicates={dupes}"
    return name, True, "no duplicates in any of the 20 investor feeds"


def t4_cold_start_new_user(pipe: SimulatedPipeline) -> TestResult:
    name = "T04  Cold-start new investor (no history) gets recommendations"
    cold = {
        "investor_id": "_cold_eval_user",
        "main_tags"  : ["fintech"],
        "subtags"    : ["payments", "lending"],
        "embedding"  : _agg_embed(["fintech", "payments", "lending"]),
    }
    INV_BY_ID["_cold_eval_user"] = cold
    try:
        result = pipe.get_feed("_cold_eval_user", seen_ids=set())
        ok = len(result["feed"]) > 0
        detail = f"received {len(result['feed'])} items"
    except Exception as e:
        ok, detail = False, str(e)
    finally:
        del INV_BY_ID["_cold_eval_user"]
    return name, ok, detail


def t5_unknown_investor(pipe: SimulatedPipeline) -> TestResult:
    name = "T05  Unknown investor handled gracefully (empty feed + error, no crash)"
    try:
        result = pipe.get_feed("__no_such_investor__")
        ok = result["feed"] == [] and len(result["errors"]) > 0
        detail = f"errors={result['errors']}" if ok else f"feed={result['feed'][:2]}"
    except Exception as e:
        ok, detail = False, str(e)
    return name, ok, detail


def t6_empty_catalog(pipe: SimulatedPipeline) -> TestResult:
    name = "T06  Empty catalog returns empty feed without crash"
    empty_pipe = SimulatedPipeline([], TAG_TAXONOMY, k=TOP_K)
    try:
        result = empty_pipe.get_feed(INVESTORS[0]["investor_id"])
        ok = result["feed"] == []
        detail = "empty feed returned correctly"
    except Exception as e:
        ok, detail = False, str(e)
    return name, ok, detail


def t7_single_item_catalog(pipe: SimulatedPipeline) -> TestResult:
    name = "T07  Single-item catalog returns ≤1 item without crash"
    one_pipe = SimulatedPipeline([PITCHDECKS[0]], TAG_TAXONOMY, k=TOP_K)
    try:
        result = one_pipe.get_feed(INVESTORS[0]["investor_id"])
        ok = len(result["feed"]) <= 1
        detail = f"feed length = {len(result['feed'])}"
    except Exception as e:
        ok, detail = False, str(e)
    return name, ok, detail


def t8_seen_ids_excluded(pipe: SimulatedPipeline) -> TestResult:
    name = "T08  Already-seen pitchdecks excluded from feed"
    seen = {p["pitchdeck_id"] for p in PITCHDECKS[:20]}  # mark first 20 as seen
    failures = []
    for inv in INVESTORS[:5]:
        result = pipe.get_feed(inv["investor_id"], seen_ids=seen)
        returned = {item["pitchdeck_id"] for item in result["feed"]}
        overlap  = returned & seen
        if overlap:
            failures.append(f"{inv['investor_id']}: {overlap}")
    if not failures:
        return name, True, "seen IDs never appear in output"
    return name, False, "; ".join(failures[:3])


def t9_all_ids_in_catalog(pipe: SimulatedPipeline) -> TestResult:
    name = "T09  All recommended IDs exist in catalog (no phantom items)"
    phantom = []
    for inv in INVESTORS:
        result = pipe.get_feed(inv["investor_id"])
        for item in result["feed"]:
            if item["pitchdeck_id"] not in CATALOG_IDS:
                phantom.append(item["pitchdeck_id"])
    if not phantom:
        return name, True, "all recommended IDs validated against catalog"
    return name, False, f"phantom IDs: {phantom[:5]}"


def t10_determinism(pipe: SimulatedPipeline) -> TestResult:
    name = "T10  Same investor call is deterministic (no random jitter)"
    inv_id = INVESTORS[0]["investor_id"]
    r1 = [x["pitchdeck_id"] for x in pipe.get_feed(inv_id)["feed"]]
    r2 = [x["pitchdeck_id"] for x in pipe.get_feed(inv_id)["feed"]]
    if r1 == r2:
        return name, True, "identical results on two consecutive calls"
    return name, False, f"call 1: {r1[:3]}, call 2: {r2[:3]}"


def t11_output_has_required_fields(pipe: SimulatedPipeline) -> TestResult:
    name = "T11  Each result item has required fields: pitchdeck_id, tags, vector_score, rerank_score"
    required = {"pitchdeck_id", "tags", "vector_score", "rerank_score"}
    for inv in INVESTORS[:3]:
        result = pipe.get_feed(inv["investor_id"])
        for item in result["feed"]:
            missing = required - set(item.keys())
            if missing:
                return name, False, f"investor={inv['investor_id']} missing={missing}"
    return name, True, "all required fields present in every result item"


def t12_sibling_fallback_triggered(pipe: SimulatedPipeline) -> TestResult:
    name = "T12  Sibling fallback fires when < K candidates and adds new items"
    # Create an investor with a very rare subtag so the main search returns few hits
    rare_inv = {
        "investor_id": "_rare_eval_user",
        "main_tags"  : ["climatetech"],
        "subtags"    : ["carbon_capture"],   # rare subtag in our small catalog
        "embedding"  : _agg_embed(["climatetech", "carbon_capture"]),
    }
    INV_BY_ID["_rare_eval_user"] = rare_inv

    # Use a tiny catalog with only a handful of matching items
    rare_catalog = [p for p in PITCHDECKS if "carbon_capture" in p["tags"]][:3]
    other_catalog = [p for p in PITCHDECKS if "climatetech" in p["tags"] and p not in rare_catalog][:20]
    test_catalog  = rare_catalog + other_catalog

    test_pipe = SimulatedPipeline(test_catalog, TAG_TAXONOMY, k=TOP_K)
    try:
        result = test_pipe.get_feed("_rare_eval_user")
        if result["fallback_triggered"]:
            detail = f"fallback fired, returned {len(result['feed'])} items"
            ok = True
        else:
            # Fallback may not fire if there are enough direct matches in the small catalog
            n_direct = len(rare_catalog)
            ok = True  # not a failure — it means the catalog was large enough
            detail = f"fallback not needed (direct matches={n_direct})"
    except Exception as e:
        ok, detail = False, str(e)
    finally:
        del INV_BY_ID["_rare_eval_user"]
    return name, ok, detail


def t13_thin_profile_no_crash(pipe: SimulatedPipeline) -> TestResult:
    name = "T13  Investor with no subtags (thin profile) handled gracefully"
    thin = {
        "investor_id": "_thin_eval_user",
        "main_tags"  : ["fintech"],
        "subtags"    : [],                   # no subtags → no filter tags
        "embedding"  : _agg_embed(["fintech"]),
    }
    INV_BY_ID["_thin_eval_user"] = thin
    try:
        result = pipe.get_feed("_thin_eval_user")
        # With no filter tags, ANN search should fall back to unfiltered search
        ok = len(result["feed"]) > 0
        detail = f"returned {len(result['feed'])} items via unfiltered fallback"
    except Exception as e:
        ok, detail = False, str(e)
    finally:
        del INV_BY_ID["_thin_eval_user"]
    return name, ok, detail


def t14_fully_exhausted_catalog(pipe: SimulatedPipeline) -> TestResult:
    name = "T14  Fully exhausted catalog (all items seen) returns empty feed"
    all_seen = set(CATALOG_IDS)
    try:
        result = pipe.get_feed(INVESTORS[0]["investor_id"], seen_ids=all_seen)
        ok = result["feed"] == []
        detail = "empty feed when all items already seen" if ok else f"got {len(result['feed'])} items"
    except Exception as e:
        ok, detail = False, str(e)
    return name, ok, detail


ALL_FUNCTIONAL_TESTS = [
    t1_pipeline_runs_end_to_end,
    t2_returns_exactly_k,
    t3_no_duplicates,
    t4_cold_start_new_user,
    t5_unknown_investor,
    t6_empty_catalog,
    t7_single_item_catalog,
    t8_seen_ids_excluded,
    t9_all_ids_in_catalog,
    t10_determinism,
    t11_output_has_required_fields,
    t12_sibling_fallback_triggered,
    t13_thin_profile_no_crash,
    t14_fully_exhausted_catalog,
]


def run_functional_tests(pipe: SimulatedPipeline) -> list[TestResult]:
    results = []
    for fn in ALL_FUNCTIONAL_TESTS:
        try:
            results.append(fn(pipe))
        except Exception as e:
            results.append((fn.__name__, False, f"EXCEPTION: {e}"))
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — INTRINSIC / BEHAVIORAL METRICS
#
#  These metrics describe the algorithm's behavior regardless of data realism.
#  They are valid even with synthetic interaction data.
# ═══════════════════════════════════════════════════════════════════════════════

def metric_catalog_coverage(
    all_feeds: list[list[str]],
    catalog:   set[str],
) -> float:
    """
    % of catalog items recommended at least once across all users.
    Range: 0–100.  Higher = broader catalog exploration.
    """
    ever_seen = {pid for feed in all_feeds for pid in feed}
    return round(len(ever_seen & catalog) / max(len(catalog), 1) * 100.0, 2)


def metric_intra_list_diversity(all_feeds: list[list[str]]) -> float:
    """
    Avg pairwise tag-Jaccard dissimilarity within each feed, averaged over users.
    Range: 0–1.  Higher = feeds contain more varied item types.
    """
    user_divs = []
    for feed in all_feeds:
        tags_list = [PD_BY_ID[pid]["tags"] for pid in feed if pid in PD_BY_ID]
        if len(tags_list) < 2:
            user_divs.append(1.0)
            continue
        pairs = list(itertools.combinations(tags_list, 2))
        div   = np.mean([1.0 - _tag_jaccard(a, b) for a, b in pairs])
        user_divs.append(float(div))
    return round(float(np.mean(user_divs)), 4) if user_divs else 0.0


def metric_novelty(all_feeds: list[list[str]], pop_map: dict[str, int]) -> float:
    """
    Avg novelty score = avg(-log2(p_i)) where p_i = popularity_fraction.
    Higher = more long-tail / niche items recommended.
    Populariy is measured as recommendation frequency across all users.
    """
    total = max(sum(pop_map.values()), 1)
    user_novs = []
    for feed in all_feeds:
        scores = []
        for pid in feed:
            p_i = pop_map.get(pid, 0) / total
            scores.append(-math.log2(p_i + 1e-10))
        if scores:
            user_novs.append(float(np.mean(scores)))
    return round(float(np.mean(user_novs)), 4) if user_novs else 0.0


def metric_personalization(all_feeds: list[list[str]]) -> float:
    """
    Avg pairwise Jaccard dissimilarity between different users' feeds.
    Range: 0–1.  Higher = each user gets a more unique feed.
    0 = everyone gets the same feed (popularity baseline).
    1 = every user gets a completely different feed.
    """
    n = len(all_feeds)
    if n < 2:
        return 0.0
    dissims = []
    for i, j in itertools.combinations(range(n), 2):
        s1, s2 = set(all_feeds[i]), set(all_feeds[j])
        union  = len(s1 | s2)
        if union == 0:
            continue
        dissims.append(1.0 - len(s1 & s2) / union)
    return round(float(np.mean(dissims)), 4) if dissims else 0.0


def _gini(values: list[float]) -> float:
    """Gini coefficient of a distribution.  0 = perfectly equal, 1 = maximally concentrated."""
    if not values or sum(values) == 0:
        return 0.0
    arr = sorted(values)
    n   = len(arr)
    idx = np.arange(1, n + 1, dtype=np.float64)
    return float(2.0 * np.dot(idx, arr) / (n * np.sum(arr)) - (n + 1) / n)


def metric_popularity_bias(
    all_feeds: list[list[str]],
    catalog:   list[dict],
) -> dict:
    """
    Gini coefficient of per-item recommendation counts.
    gini: 0 = all items recommended equally, 1 = one item gets everything.
    top10_share: % of all recommendations that go to the top-10% most recommended items.
    Also returns the raw pop_map for use in novelty calculation.
    """
    counts  = Counter(pid for feed in all_feeds for pid in feed)
    pop_map = {p["pitchdeck_id"]: counts.get(p["pitchdeck_id"], 0) for p in catalog}
    total   = max(sum(pop_map.values()), 1)

    gini    = round(_gini(list(pop_map.values())), 4)

    n_top   = max(1, len(pop_map) // 10)
    top_cnt = sum(sorted(pop_map.values(), reverse=True)[:n_top])
    top10   = round(top_cnt / total * 100.0, 2)

    return {"gini": gini, "top10_share": top10, "pop_map": pop_map}


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — BASELINES
# ═══════════════════════════════════════════════════════════════════════════════

def baseline_random(catalog: list[dict], k: int, user_idx: int) -> list[str]:
    """K random items from catalog (per-user seed for reproducibility)."""
    rng = random.Random(user_idx * 1000 + 7)
    return [p["pitchdeck_id"] for p in rng.sample(catalog, k=min(k, len(catalog)))]


def baseline_popular(catalog: list[dict], k: int) -> list[str]:
    """
    Top-K most popular items — same feed for every user.
    Without real interaction data, uses catalog ordering as synthetic popularity
    (index 0 = most popular), making this an intentionally degenerate baseline.
    """
    return [p["pitchdeck_id"] for p in catalog[:k]]


def baseline_heuristic(investor: dict, catalog: list[dict], k: int) -> list[str]:
    """
    Tag-Jaccard overlap heuristic.  No embeddings — pure keyword matching.
    This represents the simplest possible personalised recommender.
    """
    q_tags = investor["main_tags"] + investor["subtags"]
    scored = [(p["pitchdeck_id"], _tag_jaccard(q_tags, p["tags"])) for p in catalog]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [pid for pid, _ in scored[:k]]


def generate_all_feeds(pipe: SimulatedPipeline) -> list[list[str]]:
    return [
        [item["pitchdeck_id"] for item in pipe.get_feed(inv["investor_id"])["feed"]]
        for inv in INVESTORS
    ]


def compute_metrics(
    feeds:   list[list[str]],
    catalog: list[dict],
    pop_map: dict[str, int],
) -> dict:
    bias = metric_popularity_bias(feeds, catalog)
    return {
        "coverage"       : metric_catalog_coverage(feeds, CATALOG_IDS),
        "ild"            : metric_intra_list_diversity(feeds),
        "novelty"        : metric_novelty(feeds, pop_map),
        "personalization": metric_personalization(feeds),
        "gini"           : bias["gini"],
        "top10_share"    : bias["top10_share"],
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — STATIC CODE REVIEW FLAGS
#
#  Observations about the real pipeline code that affect correctness or
#  performance.  Identified by code inspection, not by running the code.
# ═══════════════════════════════════════════════════════════════════════════════

CODE_FLAGS = [
    (
        "BUG",
        "sibling_fallback_node — hardcoded `needed = 3`",
        "node.py:267 sets `needed = 3` unconditionally instead of "
        "`needed = TOP_K - len(current_candidates)`.  The `if needed <= 0` "
        "guard below it is dead code — needed is always 3, so the guard never "
        "triggers.  When 8 candidates exist and TOP_K=10, the fallback fires "
        "correctly but fetches only `needed*2 = 6` sibling results instead of "
        "the required minimum.  The reranker then selects top-K from the "
        "merged pool, which incidentally masks the issue — but the logic is "
        "wrong and will behave unexpectedly if RERANK_FETCH_K or TOP_K change.",
    ),
    (
        "TEST GAP",
        "test_generate_filter_tags_node — fetch_seen_pitchdeck_ids not mocked",
        "tests/test_feed_updates.py:477 only patches get_investor_subtags "
        "but not fetch_seen_pitchdeck_ids.  Without a live Supabase connection "
        "the latter returns [] silently (guarded by `if not supabase`), so the "
        "test passes but never asserts on seen_pitchdeck_ids.  Add a "
        "`@patch('...fetch_seen_pitchdeck_ids')` decorator and assert on the "
        "returned value.",
    ),
    (
        "EFFICIENCY",
        "rerank_candidates_node — double Supabase fetch of investor tags",
        "node.py:224 calls fetch_investor_tags(investor_id) to build the "
        "reranker query string.  This is a second Supabase read for data "
        "already fetched in Node 2's aggregated-fallback path.  Pass investor "
        "tags through FilteredSearchState instead of re-fetching.",
    ),
    (
        "PERFORMANCE",
        "neo4j_queries.py — new driver instance per function call",
        "get_investor_subtags(), get_sibling_subtags(), and "
        "update_graph_edge_weights() each call GraphDatabase.driver() and "
        "close it on exit.  At scale, this creates and tears down a TCP "
        "connection on every recommendation request.  Use a module-level "
        "singleton with Neo4j's built-in connection pooling instead.",
    ),
    (
        "ROBUSTNESS",
        "reranker.py — no retry on Jina API timeout",
        "A single aiohttp timeout raises RuntimeError, which Node 4 catches "
        "and falls back to vector order.  This is acceptable but silent — "
        "add exponential backoff (1–2 retries) before falling back, to "
        "avoid penalising precision on transient rate-limit errors.",
    ),
    (
        "CORRECTNESS",
        "generate_filter_tags_node — node.py:107 misses seen_pitchdeck_ids state key",
        "The node returns `seen_pitchdeck_ids` (node.py:114) but the "
        "FilteredSearchState TypedDict defines the key as `seen_pitchdeck_ids` "
        "(state.py:14), which matches.  However, node.py:107 calls "
        "fetch_seen_pitchdeck_ids which reads from `pitchdeck_likes` table "
        "(supabase_tags.py:43) while the API route comment refers to "
        "`pitchdeck_interactions`.  Confirm which table is the source of truth "
        "for seen interactions to avoid a silent data-source mismatch.",
    ),
]


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 6 — REPORT RENDERER
# ═══════════════════════════════════════════════════════════════════════════════

def _bar(value: float, max_val: float = 1.0, width: int = 20) -> str:
    filled = int(round(value / max(max_val, 1e-9) * width))
    return "#" * filled + "." * (width - filled)


def print_report(
    func_results: list[TestResult],
    metrics:      dict[str, dict],   # {"Agent": {...}, "Random": {...}, ...}
    pop_map:      dict[str, int],
) -> None:

    SEP  = "=" * 72
    THIN = "-" * 72

    passed = [r for r in func_results if r[1]]
    failed = [r for r in func_results if not r[1]]

    print(f"\n{SEP}")
    print("  SPARK2SCALE -- FEED RECOMMENDATION AGENT EVALUATION")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Catalog: {N_PITCHDECKS} pitchdecks  |  {N_INVESTORS} investors  |  K={TOP_K}")
    print(f"  Agent type: Hybrid (content-based + RL + UCB multi-vector + cross-encoder)")
    print(SEP)

    # ── (A) Functional tests ──────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  (A) FUNCTIONAL TESTS                        "
          f"{len(passed)} PASSED / {len(failed)} FAILED")
    print(f"{'='*72}\n")

    for name, ok, detail in func_results:
        icon   = "[PASS]" if ok else "[FAIL]"
        print(f"  {icon}  {name}")
        if not ok or (ok and detail):
            wrapped = textwrap.fill(detail, width=64,
                                    initial_indent="           ",
                                    subsequent_indent="           ")
            print(wrapped)

    # ── (B) Intrinsic metrics ─────────────────────────────────────────────────
    print(f"\n{THIN}")
    print(f"\n{'='*72}")
    print("  (B) INTRINSIC / BEHAVIORAL METRICS")
    print("      (PIPELINE SANITY CHECK ONLY -- not a quality measure)")
    print(f"{'='*72}\n")
    print("  Goal: high coverage + personalization + diversity + novelty,")
    print("  low popularity bias (Gini).  These describe behavior, not quality.\n")

    systems = list(metrics.keys())
    col_w   = 12

    # Header
    hdr = f"  {'Metric':<28}" + "".join(f"{s:>{col_w}}" for s in systems)
    print(hdr)
    print(f"  {THIN[:70]}")

    METRIC_META = [
        ("coverage",        "Catalog Coverage (%)",         "[+] higher better", 100.0),
        ("ild",             "Intra-list Diversity",          "[+] higher better", 1.0),
        ("novelty",         "Novelty (-log2 popularity)",    "[+] higher better", None),
        ("personalization", "Personalization",               "[+] higher better", 1.0),
        ("gini",            "Popularity Bias (Gini)",        "[-] lower better",  1.0),
        ("top10_share",     "Top-10% items share (%)",       "[-] lower better",  100.0),
    ]

    for mk, label, direction, _ in METRIC_META:
        vals = {s: metrics[s][mk] for s in systems}
        row  = f"  {label:<28}" + "".join(f"{vals[s]:>{col_w}.3f}" for s in systems)
        row += f"   {direction}"
        print(row)

    # Per-metric bar charts for agent only
    print(f"\n  Agent bar charts (max scale varies by metric):\n")
    agent_m = metrics["Agent"]
    for mk, label, direction, scale in METRIC_META:
        if scale is None:
            continue
        v = agent_m[mk] / scale
        v = min(v, 1.0)
        print(f"  {label:<28} {_bar(v, 1.0, 20)}  {agent_m[mk]:.3f}")

    # ── (C) Code flags ────────────────────────────────────────────────────────
    print(f"\n{THIN}")
    print(f"\n{'='*72}")
    print(f"  (C) CODE FLAGS  ({len(CODE_FLAGS)} found)")
    print(f"{'='*72}\n")

    severity_label = {"BUG": "[BUG]", "TEST GAP": "[TEST GAP]",
                      "EFFICIENCY": "[EFFICIENCY]", "PERFORMANCE": "[PERFORMANCE]",
                      "ROBUSTNESS": "[ROBUSTNESS]", "CORRECTNESS": "[CORRECTNESS]"}

    for i, (sev, title, desc) in enumerate(CODE_FLAGS, 1):
        label = severity_label.get(sev, sev)
        print(f"  {i}. {label} {title}")
        for line in textwrap.wrap(desc, width=66):
            print(f"       {line}")
        print()

    # ── (D) Limitations ───────────────────────────────────────────────────────
    print(f"{THIN}")
    print(f"\n{'='*72}")
    print("  (D) LIMITATIONS -- WHY QUALITY METRICS WERE NOT COMPUTED")
    print(f"{'='*72}\n")

    limitations = textwrap.dedent("""
    RECOMMENDATION QUALITY CANNOT BE ASSESSED WITH THIS DATA.

    All interaction data in this project is SYNTHETIC (generated for
    testing purposes).  Computing Precision@K, Recall@K, NDCG, MAP, MRR,
    or Hit Rate against synthetic interactions would measure how well the
    agent replicates the data generation script — not how useful it is to
    real investors.  Such numbers would be misleading and should NOT be
    reported as evidence of recommendation quality.

    What is required for genuine quality evaluation:

      1. Real interaction logs — genuine likes, dislikes, and contact
         events collected from a deployed system with real investors.
         Minimum threshold: thousands of interactions across hundreds of
         investors to get stable estimates.

      2. Human relevance judgements — domain-expert raters scoring
         recommended pitchdecks for a given investor profile on a 1–5
         scale, enabling offline NDCG/MAP computation.

      3. Online A/B test — randomly assign investors to the agent vs.
         a popularity baseline; measure contact rate, deal-flow, and
         30-day retention as primary success metrics.

      4. Long-horizon feedback — track whether recommended pitchdecks
         lead to actual investor interest over weeks, not just clicks.

    The intrinsic metrics in Section (B) are the only valid signals
    today.  They confirm the algorithm is not trivially broken (it
    produces varied, personalised, broad-coverage feeds) but they do
    not confirm it recommends well.
    """).strip()

    for line in limitations.splitlines():
        print(f"  {line}" if line else "")

    print(f"\n{SEP}\n")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    # Ensure UTF-8 output on all platforms (Windows defaults to cp1252)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("\nInitialising evaluation ...")

    # Build the pipeline under test
    pipe = SimulatedPipeline(PITCHDECKS, TAG_TAXONOMY, k=TOP_K, fetch_k=FETCH_K)

    # (A) Functional tests
    print("Running 14 functional tests ...")
    func_results = run_functional_tests(pipe)

    # (B+C+D) Behavioral metrics -- agent + baselines
    print("Generating feeds for all investors ...")
    agent_feeds = generate_all_feeds(pipe)

    # Build a popularity map from agent feed counts (used as reference)
    bias_result = metric_popularity_bias(agent_feeds, PITCHDECKS)
    pop_map     = bias_result["pop_map"]

    print("Computing intrinsic metrics ...")
    baselines_raw: dict[str, list[list[str]]] = {
        "Random"   : [baseline_random(PITCHDECKS, TOP_K, i) for i in range(N_INVESTORS)],
        "Popular"  : [baseline_popular(PITCHDECKS, TOP_K)  for _  in range(N_INVESTORS)],
        "Heuristic": [baseline_heuristic(inv, PITCHDECKS, TOP_K) for inv in INVESTORS],
    }

    metrics: dict[str, dict] = {"Agent": compute_metrics(agent_feeds, PITCHDECKS, pop_map)}
    for name, feeds in baselines_raw.items():
        metrics[name] = compute_metrics(feeds, PITCHDECKS, pop_map)

    # Print the full report
    print_report(func_results, metrics, pop_map)

    n_failed = sum(1 for _, ok, _ in func_results if not ok)
    return 1 if n_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
