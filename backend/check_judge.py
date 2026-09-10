import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from dotenv import load_dotenv
load_dotenv()

print("\n=== ENV CHECK ===")
print("JUDGE_MODEL =", os.getenv("JUDGE_MODEL"))
print("OPENAI_BASE_URL =", os.getenv("OPENAI_BASE_URL"))
print("OPENAI_API_KEY =", (os.getenv("OPENAI_API_KEY") or "")[:12], "...")
print("MISTRAL_API_KEY =", (os.getenv("MISTRAL_API_KEY") or "")[:12], "...")

print("\n=== BUILD JUDGE ===")
from core.services.providers import build_judge, _instantiate, ProviderError

try:
    judge = _instantiate(os.getenv("JUDGE_MODEL", ""))
    print("✅ Judge built:", judge.id, "|", judge.display_name)
    print("\n=== TEST JUDGE CALL ===")
    out = judge.generate("Reply with exactly: OK")
    print("✅ Judge response:", out[:200])
except Exception as e:
    print("❌ FAILED:", type(e).__name__, "-", e)