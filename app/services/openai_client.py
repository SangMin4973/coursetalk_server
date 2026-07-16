from openai import OpenAI
from app.core.config import get_settings

settings = get_settings()

client = OpenAI(
    api_key=settings.openai_api_key,
    timeout=90.0,
)