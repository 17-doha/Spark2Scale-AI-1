import modal
import time
import os
import json
from typing import Dict, Any

# ── Image: upgraded vLLM + transformers that know Gemma 3n ───────────────────
inference_image = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install(
        "vllm>=0.8.5",           # Gemma 3n support added here
        "transformers>=4.53.0",  # Gemma3nForConditionalGeneration added here
        "fastapi",
        "huggingface_hub",
        "accelerate",
        "timm",
    )
)

app = modal.App("spark2scale-gemma3n-inference")


@app.cls(
    gpu              = "A100-40GB",
    image            = inference_image,
    secrets          = [modal.Secret.from_name("huggingface-secret")],
    scaledown_window = 300,
    timeout          = 600,   # give enough time for model download on cold start
)
@modal.concurrent(max_inputs=32)  # forward up to 32 HTTP requests to the same container so vLLM can batch them
class LLMEngine:

    @modal.enter()
    def load_model(self):
        from huggingface_hub import snapshot_download
        from vllm.engine.async_llm_engine import AsyncLLMEngine
        from vllm.engine.arg_utils import AsyncEngineArgs

        # V1 engine currently has a bug with Gemma 3 dummy profiling (inputs_embeds=None).
        # We force V0 engine to avoid this crash.
        os.environ["VLLM_USE_V1"] = "0"

        model_id = "Spark2scale/gemma_3n_spark2scale-4500-5-merged"
        hf_token = os.environ.get("HF_TOKEN")

        print(f"Downloading {model_id} ...")
        local_dir = snapshot_download(repo_id=model_id, token=hf_token)
        print(f"Downloaded to {local_dir}")

        # ── Patch config.json ────────────────────────────────────────────────
        config_path = os.path.join(local_dir, "config.json")
        with open(config_path) as f:
            config = json.load(f)

        def patch_config(obj):
            if not isinstance(obj, dict):
                return
            if "gradient_clipping" in obj:
                val = obj["gradient_clipping"]
                if isinstance(val, (int, float)) and abs(val) > 60000:
                    print(f"  Patched gradient_clipping: {val} -> 1.0")
                    obj["gradient_clipping"] = 1.0
            if "torch_dtype" in obj and obj["torch_dtype"] == "float16":
                print("  Patched torch_dtype: float16 -> bfloat16")
                obj["torch_dtype"] = "bfloat16"
            if "quantization_config" in obj:
                print("  Removed quantization_config")
                del obj["quantization_config"]
            for v in list(obj.values()):
                if isinstance(v, dict):
                    patch_config(v)

        patch_config(config)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        print("config.json patched.")

        # ── Init vLLM engine ─────────────────────────────────────────────────
        print("Initialising vLLM AsyncLLMEngine ...")
        engine_args = AsyncEngineArgs(
            model                  = local_dir,
            dtype                  = "bfloat16",
            max_model_len          = 8192,   # raised from 4096; A100 KV cache handles this easily
            gpu_memory_utilization = 0.90,
            max_num_seqs           = 32,
            tensor_parallel_size   = 1,
            enforce_eager          = True,   # skip CUDA-graph profiling that crashes on Gemma3n mm forward
            trust_remote_code      = True,
        )
        self.engine = AsyncLLMEngine.from_engine_args(engine_args)

        # Store tokenizer for server-side token counting / truncation
        from transformers import AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(local_dir, trust_remote_code=True)
        self.max_model_len = 8192   # keep in sync with engine_args above
        print("Engine ready!")

    # ── Token-aware two-stage truncation ─────────────────────────────────────
    def _smart_truncate(
        self,
        context: str,
        question: str,
        json_suffix: str,
        max_new_tokens: int,
    ) -> str:
        """
        Ensure the full prompt fits within the model's token window.

        Stage 1 — trim CONTEXT (keep tail)
            Handles evaluation_agent calls where the context block is large
            but the question/instruction is short.

        Stage 2 — trim QUESTION (keep tail)
            Handles chat.py calls where the question contains the full
            startup-data JSON (can be 10k+ tokens).  We keep the TAIL of
            the question so the actual user message (always at the end) is
            never dropped.

        Hard-cap fallback
            Slice raw token IDs so vLLM never crashes with an oversized input,
            no matter what.
        """
        SAFETY_MARGIN = 64
        token_budget = self.max_model_len - max_new_tokens - SAFETY_MARGIN

        # ── helpers ──────────────────────────────────────────────────────────
        def _encode(text: str) -> list:
            return self.tokenizer.encode(text, add_special_tokens=False)

        def _decode(ids: list) -> str:
            return self.tokenizer.decode(ids, skip_special_tokens=True)

        def _build_prompt(ctx: str, q: str) -> str:
            user_content = f"Context: {ctx}\n\nQuestion: {q}{json_suffix}"
            return (
                "<start_of_turn>user\n"
                + user_content
                + "<end_of_turn>\n"
                + "<start_of_turn>model\n"
            )

        def _trim_tail(ids: list, max_toks: int, label: str) -> str:
            """Return decoded text, keeping the last max_toks tokens."""
            if len(ids) <= max_toks:
                return _decode(ids)
            return f"[... {label} trimmed to fit model window ...]\n" + _decode(ids[-max_toks:])

        # ── Quick exit: already fits ─────────────────────────────────────────
        full_prompt = _build_prompt(context, question)
        original_tokens = len(_encode(full_prompt))
        if original_tokens <= token_budget:
            return full_prompt

        ctx_ids = _encode(context)
        q_ids   = _encode(question)

        # ── Stage 1: trim context ────────────────────────────────────────────
        # How much room is left for context once the question+template is fixed?
        skeleton_tokens = len(_encode(_build_prompt("", question)))
        available_for_ctx = token_budget - skeleton_tokens

        if available_for_ctx > 0:
            trimmed_ctx = _trim_tail(ctx_ids, available_for_ctx, "context")
            stage1_prompt = _build_prompt(trimmed_ctx, question)
            stage1_tokens = len(_encode(stage1_prompt))
            print(
                f"[INFO] Stage-1 (context trim): {original_tokens} → {stage1_tokens} tokens "
                f"(budget {token_budget})"
            )
            if stage1_tokens <= token_budget:
                return stage1_prompt
        else:
            print(
                f"[INFO] Stage-1 skipped: question alone ({skeleton_tokens} tokens) "
                f"already exceeds budget ({token_budget}). Moving to Stage 2."
            )

        # ── Stage 2: trim question (keep tail = user message) ───────────────
        # Measure the bare template overhead (empty ctx + empty question).
        bare_overhead = len(_encode(_build_prompt("", "")))
        available_for_q = token_budget - bare_overhead

        if available_for_q > 0:
            trimmed_q = _trim_tail(q_ids, available_for_q, "question/data")
            stage2_prompt = _build_prompt("", trimmed_q)
            stage2_tokens = len(_encode(stage2_prompt))
            print(
                f"[INFO] Stage-2 (question trim): → {stage2_tokens} tokens "
                f"(budget {token_budget}, kept tail of question)"
            )
            if stage2_tokens <= token_budget:
                return stage2_prompt
        else:
            print(
                f"[WARN] Bare template overhead ({bare_overhead} tokens) already "
                f"exceeds budget ({token_budget}). Applying hard-cap fallback."
            )
            stage2_prompt = _build_prompt("", f"[payload too large — {original_tokens} tokens]")

        # ── Hard-cap fallback: raw token-ID slice ────────────────────────────
        # Should never be reached, but guarantees vLLM never crashes.
        all_ids = _encode(stage2_prompt)
        sliced  = _decode(all_ids[-token_budget:])
        print(f"[WARN] Hard-cap fallback: sliced to {token_budget} tokens")
        return sliced

    # ── Inference endpoint ────────────────────────────────────────────────────
    @modal.fastapi_endpoint(method="POST")
    async def infer(self, payload: Dict[str, Any]):
        import uuid
        from vllm import SamplingParams

        context        = payload.get("context", "")
        question       = payload.get("question", "")
        json_mode      = payload.get("json_mode", False)
        temperature    = payload.get("temperature", 0.7)
        max_new_tokens = payload.get("max_new_tokens", 512)
        top_p          = payload.get("top_p", 0.95)
        top_k          = payload.get("top_k", 64)

        # Build the JSON instruction suffix (only in json_mode)
        json_suffix = (
            "\n\nOutput only valid JSON. "
            "Do not include any preamble, explanation, or markdown code blocks."
            if json_mode else ""
        )

        # Build + smart-truncate the prompt so it always fits the model window
        prompt = self._smart_truncate(
            context        = context,
            question       = question,
            json_suffix    = json_suffix,
            max_new_tokens = max_new_tokens,
        )

        sampling_params = SamplingParams(
            temperature = temperature,
            top_p       = top_p,
            top_k       = top_k,
            max_tokens  = max_new_tokens,
        )

        request_id   = str(uuid.uuid4())
        t0           = time.perf_counter()
        final_output = None

        async for out in self.engine.generate(prompt, sampling_params, request_id):
            final_output = out

        answer  = final_output.outputs[0].text.strip()
        elapsed = round(time.perf_counter() - t0, 3)

        result = {
            "answer":         answer,
            "inference_time": elapsed,
        }

        if json_mode:
            try:
                clean = answer.replace("```json", "").replace("```", "").strip()
                result["json_data"]  = json.loads(clean)
                result["json_valid"] = True
            except json.JSONDecodeError as e:
                result["json_data"]  = None
                result["json_valid"] = False
                result["json_error"] = str(e)

        return result

    # ── Health check ──────────────────────────────────────────────────────────
    @modal.fastapi_endpoint(method="GET")
    async def health(self):
        return {"status": "healthy", "engine": "vLLM AsyncLLMEngine"}


# ── Local test entrypoint ─────────────────────────────────────────────────────
@app.local_entrypoint()
def main():
    import time
    import requests

    # During `modal run` the URLs carry a -dev suffix.
    # Cold start = model download (~60s) + engine init (~30s) → allow up to 10 min.
    INFER_URL  = os.getenv(
        "MODAL_INFER_URL_DEV",
        "https://doha-hemdan7--spark2scale-gemma3n-inference-llmengine-infer-dev.modal.run",
    )
    HEALTH_URL = os.getenv(
        "MODAL_HEALTH_URL_DEV",
        "https://doha-hemdan7--spark2scale-gemma3n-inference-llmengine-health-dev.modal.run",
    )

    TEST_PAYLOAD = {
        "context":       "Simple AI builds AI phone agents for sales automation.",
        "question":      "What are the top 3 strengths of this startup?",
        "max_new_tokens": 200,
        "temperature":   0.7,
    }

    TOTAL_WAIT   = 600   # seconds before giving up
    RETRY_EVERY  = 15    # seconds between attempts
    deadline     = time.time() + TOTAL_WAIT
    attempt      = 0

    print("Waiting for container to finish cold start (model download + engine init)...")
    print("This can take up to 2 minutes on first run.\n")

    while time.time() < deadline:
        attempt += 1
        try:
            # ── Try health first (fast, no GPU work) ─────────────────────────
            h = requests.get(HEALTH_URL, timeout=20)
            if h.status_code == 200:
                print(f"[attempt {attempt}] Health OK: {h.json()}")
                break
        except requests.exceptions.RequestException as e:
            remaining = int(deadline - time.time())
            print(f"[attempt {attempt}] Container not ready yet ({e.__class__.__name__}). "
                  f"Retrying in {RETRY_EVERY}s ... ({remaining}s left)")
            time.sleep(RETRY_EVERY)
    else:
        print("Container did not become healthy within the timeout. Check Modal dashboard.")
        return

    # ── Container is up — run the real inference test ─────────────────────────
    print("\nRunning test inference ...")
    try:
        resp = requests.post(INFER_URL, json=TEST_PAYLOAD, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        print(f"Answer:         {data['answer'][:300]}")
        print(f"Inference time: {data['inference_time']}s")
    except requests.exceptions.RequestException as e:
        print(f"Inference failed: {e}")