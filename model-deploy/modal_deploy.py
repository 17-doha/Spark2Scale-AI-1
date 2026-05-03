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

        model_id = "Dohahemdann/gemma_3n_spark2scale-4500-5-merged"
        hf_token = os.environ.get("HF_TOKEN")

        print(f"Downloading {model_id} ...")
        local_dir = snapshot_download(repo_id=model_id, token=hf_token)
        print(f"Downloaded to {local_dir}")

        # ── Patch config.json ────────────────────────────────────────────────
        # gradient_clipping fix is still needed; rope_type error no longer
        # occurs on vllm>=0.8.5 with correct transformers version.
        config_path = os.path.join(local_dir, "config.json")
        with open(config_path) as f:
            config = json.load(f)

        def patch_config(obj):
            if not isinstance(obj, dict):
                return
            # gradient_clipping overflows float16 range if > 65504
            if "gradient_clipping" in obj:
                val = obj["gradient_clipping"]
                if isinstance(val, (int, float)) and abs(val) > 60000:
                    print(f"  Patched gradient_clipping: {val} -> 1.0")
                    obj["gradient_clipping"] = 1.0
            # Force torch_dtype to bfloat16 to avoid float16 vs bfloat16 mixed precision crash in vLLM vision profiler
            if "torch_dtype" in obj and obj["torch_dtype"] == "float16":
                print("  Patched torch_dtype: float16 -> bfloat16")
                obj["torch_dtype"] = "bfloat16"
            # Remove quantization_config so vLLM loads in bfloat16
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
            dtype                  = "bfloat16",  # A100 supports bfloat16 natively
            max_model_len          = 4096,         # A100 has headroom for longer ctx
            gpu_memory_utilization = 0.90,
            max_num_seqs           = 32,           # match allow_concurrent_inputs so all requests batch together
            tensor_parallel_size   = 1,
            enforce_eager          = True,         # skip CUDA-graph profiling that crashes on Gemma3n mm forward
            trust_remote_code      = True,
        )
        self.engine = AsyncLLMEngine.from_engine_args(engine_args)
        print("Engine ready!")

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

        # Build prompt in the Gemma chat format used during fine-tuning
        user_content = f"Context: {context}\n\nQuestion: {question}"
        if json_mode:
            user_content += (
                "\n\nOutput only valid JSON. "
                "Do not include any preamble, explanation, or markdown code blocks."
            )
        prompt = (
            "<start_of_turn>user\n"
            + user_content
            + "<end_of_turn>\n"
            + "<start_of_turn>model\n"
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
    INFER_URL  = "https://doha-hemdan7--spark2scale-gemma3n-inference-llmengine-infer-dev.modal.run"
    HEALTH_URL = "https://doha-hemdan7--spark2scale-gemma3n-inference-llmengine-health-dev.modal.run"

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