import os
import requests
import uuid
import urllib.parse
from typing import Optional

from app.core.config import config
from app.core.logger import get_logger

logger = get_logger(__name__)


def _generate_image_pollinations(prompt: str, output_dir: str) -> Optional[str]:
    """Generate image via Pollinations AI. Model is configurable (e.g. gptimage-large for better icon quality)."""
    icon_suffix = ", premium 3D isometric render, modern professional illustration, high resolution, soft studio lighting, clean background, high quality"
    full_prompt = (prompt.strip().rstrip(".,") + " " + icon_suffix).strip()
    model = getattr(config, "IMAGE_MODEL", "gptimage-large") or "gptimage-large"
    logger.info(f"Generating image via Pollinations (model={model}) for prompt: {full_prompt}")
    encoded_prompt = urllib.parse.quote(full_prompt)
    seed = uuid.uuid4().int % 1000000
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?model={urllib.parse.quote(model)}&width=1024&height=1024&seed={seed}&nologo=true"
    headers = {}
    if config.POLLINATIONS_API_KEY:
        headers["Authorization"] = f"Bearer {config.POLLINATIONS_API_KEY}"
    response = requests.get(url, headers=headers, timeout=90)
    if response.status_code != 200:
        logger.error(f"Pollinations AI failed ({response.status_code}): {response.text}")
        return None
    filename = f"{uuid.uuid4()}.png"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "wb") as f:
        f.write(response.content)
    logger.info(f"Image saved to {filepath}")
    return filepath


def _generate_image_google(prompt: str, output_dir: str) -> Optional[str]:
    """Generate image via Google GenAI SDK (gemini-2.5-flash-image)."""
    try:
        from google import genai
        from PIL import Image
    except ImportError:
        logger.warning("google-genai or PIL package not installed.")
        return None

    if not config.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set; falling back to Pollinations.")
        return None

    icon_suffix = ", premium 3D isometric illustration, modern professional render, high quality, soft lighting, clean background"
    full_prompt = (prompt.strip().rstrip(".,") + " " + icon_suffix).strip()
    model_name = getattr(config, "IMAGE_MODEL", "gemini-2.5-flash-lite") or "gemini-2.5-flash-lite"
    
    # If the user has a Pollinations model configured but is using Google provider, 
    # we MUST use a valid Google model name (e.g. gemini-2.5-flash-lite)
    if "gpt" in model_name or "flux" in model_name or "imagen" not in model_name.lower() and "gemini" not in model_name.lower():
        model_name = "gemini-2.5-flash-lite" # Default safe choice for GenAI SDK image gen
    
    logger.info(f"Generating image via Google GenAI (model={model_name}) for prompt: {full_prompt}")
    
    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=model_name,
            contents=[full_prompt],
        )

        image_path = os.path.join(output_dir, f"{uuid.uuid4()}.png")
        
        for part in response.parts:
            if part.inline_data is not None:
                image = part.as_image()
                image.save(image_path)
                logger.info(f"Image saved to {image_path}")
                return image_path
                
        logger.error("No image data found in Google GenAI response.")
        return None
    except Exception as e:
        logger.error(f"Google GenAI failed: {e}")
        return None


def generate_image(prompt: str, output_dir: str) -> Optional[str]:
    """
    Generates an image for the slide. Uses Google GenAI (Gemini image) when
    IMAGE_PROVIDER=google; otherwise uses Pollinations.
    """
    try:
        provider = getattr(config, "IMAGE_PROVIDER", "pollinations") or "pollinations"
        
        if provider.lower() == "google":
            out = _generate_image_google(prompt, output_dir)
            if out: return out
            logger.info("Google GenAI failed; falling back to Pollinations.")

        return _generate_image_pollinations(prompt, output_dir)
    except Exception as e:
        logger.error(f"Error generating image: {e}")
        return None
