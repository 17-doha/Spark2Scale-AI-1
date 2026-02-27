from supabase import create_client, Client
from app.core.config import config
from app.core.logger import get_logger

logger = get_logger(__name__)

supabase: Client | None = None

try:
    if config.SUPABASE_URL and config.SUPABASE_KEY:
        supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
        logger.info("Supabase client initialized successfully")
    else:
        logger.warning("Supabase URL or Key not found in config, Supabase client not initialized")
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {e}")
