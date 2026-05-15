import modal
import time
import os
import json
from typing import Dict, Any

# ── Image ─────────────────────────────────────────────────────────────────────
inference_image = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install(
        "vllm>=0.8.5",
        "transformers>=4.53.0",
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
    timeout          = 600,
)
@modal.concurrent(max_inputs=32)
class LLMEngine:

    @modal.enter()
    def load_model(self):
        # MUST be set before any vLLM import. V1 is now the default in vLLM>=0.8
        # and can only be configured at process startup. We embrace V1 and use
        # its TokensPrompt API (prompt_token_ids) to avoid the deprecated
        # raw-string InputProcessor path that caused the 500 error.
        os.environ["VLLM_USE_V1"] = "1"

        from huggingface_hub import snapshot_download
        from vllm import LLM

        model_id = "Dohahemdann/gemma_3n_spark2scale-4500-5-merged"
        hf_token = os.environ.get("HF_TOKEN")

        print(f"Downloading {model_id} ...")
        local_dir = snapshot_download(repo_id=model_id, token=hf_token)
        print(f"Downloaded to {local_dir}")

        # ── Patch config.json ─────────────────────────────────────────────────
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

        # ── Init vLLM V1 (synchronous LLM) ───────────────────────────────────
        # We use the sync vllm.LLM and call it via asyncio.to_thread() in infer().
        # AsyncLLMEngine's generate() now requires Renderer.render_cmpl() input,
        # not raw strings — sync LLM.generate({"prompt_token_ids": [...]}) is
        # the cleanest V1-compatible path.
        print("Initialising vLLM LLM (V1, sync) ...")
        self.llm = LLM(
            model                  = local_dir,
            dtype                  = "bfloat16",
            max_model_len          = 8192,
            gpu_memory_utilization = 0.90,
            max_num_seqs           = 32,
            tensor_parallel_size   = 1,
            enforce_eager          = True,   # skip CUDA-graph profiling (Gemma3n crash guard)
            trust_remote_code      = True,
        )

        from transformers import AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            local_dir, trust_remote_code=True
        )
        self.max_model_len = 8192
        print("Engine ready!")

    # ── Helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _wrap_chat(user_text: str) -> str:
        return (
            "<start_of_turn>user\n"
            + user_text
            + "<end_of_turn>\n"
            + "<start_of_turn>model\n"
        )

    def _to_token_ids(self, text: str, max_new_tokens: int) -> list:
        """
        Tokenize text and truncate to fit the model window.
        Returns a list of token IDs — passed as {"prompt_token_ids": ids}
        to vLLM so we never touch the deprecated raw-string path.
        HEAD is preserved (schema/instructions stay intact);
        only the tail of the document text is dropped if needed.
        """
        SAFETY_MARGIN = 64
        budget = self.max_model_len - max_new_tokens - SAFETY_MARGIN
        ids = self.tokenizer.encode(text, add_special_tokens=False)
        if len(ids) > budget:
            print(
                f"[INFO] Truncated: {len(ids)} → {budget} tokens "
                f"(dropped {len(ids) - budget} tokens from tail)"
            )
            ids = ids[:budget]
        return ids

    def _smart_truncate_ids(self, context, question, json_suffix, max_new_tokens) -> list:
        """Legacy context+question path — keeps question TAIL (user message)."""
        SAFETY_MARGIN = 64
        budget = self.max_model_len - max_new_tokens - SAFETY_MARGIN

        def enc(t):
            return self.tokenizer.encode(t, add_special_tokens=False)

        def dec(ids):
            return self.tokenizer.decode(ids, skip_special_tokens=True)

        def build(ctx, q):
            return self._wrap_chat(f"Context: {ctx}\n\nQuestion: {q}{json_suffix}")

        ids = enc(build(context, question))
        if len(ids) <= budget:
            return ids

        # Stage 1: trim context tail
        avail = budget - len(enc(build("", question)))
        if avail > 0:
            s1_ids = enc(build(dec(enc(context)[:avail]), question))
            if len(s1_ids) <= budget:
                return s1_ids

        # Stage 2: trim question head, keep tail
        avail = budget - len(enc(build("", "")))
        if avail > 0:
            q_ids = enc(question)
            s2_ids = enc(build("", dec(q_ids[-avail:])))
            if len(s2_ids) <= budget:
                return s2_ids

        return enc(build("", "[payload too large]"))[:budget]

    # ── Inference endpoint ─────────────────────────────────────────────────────
    @modal.fastapi_endpoint(method="POST")
    async def infer(self, payload: Dict[str, Any]):
        import asyncio
        from vllm import SamplingParams

        raw_prompt     = payload.get("prompt",         None)
        context        = payload.get("context",        "")
        question       = payload.get("question",       "")
        json_mode      = payload.get("json_mode",      False)
        temperature    = payload.get("temperature",    0.7)
        max_new_tokens = payload.get("max_new_tokens", 512)
        top_p          = payload.get("top_p",          0.95)
        top_k          = payload.get("top_k",          64)

        if raw_prompt is not None:
            # PDF extractor: pre-built prompt → wrap in chat template → tokenize
            token_ids = self._to_token_ids(
                self._wrap_chat(raw_prompt), max_new_tokens
            )
        else:
            # Legacy evaluation_agent / chat.py
            json_suffix = (
                "\n\nOutput only valid JSON. "
                "Do not include any preamble, explanation, or markdown code blocks."
                if json_mode else ""
            )
            token_ids = self._smart_truncate_ids(
                context, question, json_suffix, max_new_tokens
            )

        sampling_params = SamplingParams(
            temperature = temperature,
            top_p       = top_p,
            top_k       = top_k,
            max_tokens  = max_new_tokens,
        )

        # Run sync LLM in a thread — keeps the async event loop free
        # {"prompt_token_ids": [...]} is the V1-safe way to pass pre-tokenized input
        def _generate():
            outputs = self.llm.generate(
                {"prompt_token_ids": token_ids},
                sampling_params,
            )
            return outputs[0].outputs[0].text.strip()

        t0      = time.perf_counter()
        answer  = await asyncio.to_thread(_generate)
        elapsed = round(time.perf_counter() - t0, 3)

        result = {"answer": answer, "inference_time": elapsed}

        if json_mode or raw_prompt is not None:
            try:
                clean = answer.replace("```json", "").replace("```", "").strip()
                result["json_data"]  = json.loads(clean)
                result["json_valid"] = True
            except json.JSONDecodeError as e:
                result["json_data"]  = None
                result["json_valid"] = False
                result["json_error"] = str(e)

        return result

    # ── Health check ───────────────────────────────────────────────────────────
    @modal.fastapi_endpoint(method="GET")
    async def health(self):
        return {"status": "healthy", "engine": "vLLM V1 sync LLM + asyncio.to_thread"}


# ── Local test entrypoint ──────────────────────────────────────────────────────
@app.local_entrypoint()
def main():
    import requests

    INFER_URL  = os.getenv(
        "MODAL_INFER_URL_DEV",
        "https://doha-hemdan7--spark2scale-gemma3n-inference-llmengine-infer-dev.modal.run",
    )
    HEALTH_URL = os.getenv(
        "MODAL_HEALTH_URL_DEV",
        "https://doha-hemdan7--spark2scale-gemma3n-inference-llmengine-health-dev.modal.run",
    )

    TEST_PAYLOAD = {
        "context":        "Simple AI builds AI phone agents for sales automation.",
        "question":       "What are the top 3 strengths of this startup?",
        "max_new_tokens": 200,
        "temperature":    0.7,
    }

    TOTAL_WAIT  = 600
    RETRY_EVERY = 15
    deadline    = time.time() + TOTAL_WAIT
    attempt     = 0

    print("Waiting for container to finish cold start...")
    while time.time() < deadline:
        attempt += 1
        try:
            h = requests.get(HEALTH_URL, timeout=20)
            if h.status_code == 200:
                print(f"[attempt {attempt}] Health OK: {h.json()}")
                break
        except requests.exceptions.RequestException as e:
            remaining = int(deadline - time.time())
            print(
                f"[attempt {attempt}] Not ready ({e.__class__.__name__}). "
                f"Retrying in {RETRY_EVERY}s ... ({remaining}s left)"
            )
            time.sleep(RETRY_EVERY)
    else:
        print("Container did not become healthy within timeout.")
        return

    print("\nRunning test inference ...")
    try:
        resp = requests.post(INFER_URL, json=TEST_PAYLOAD, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        print(f"Answer:         {data['answer'][:300]}")
        print(f"Inference time: {data['inference_time']}s")
    except requests.exceptions.RequestException as e:
        print(f"Inference failed: {e}")