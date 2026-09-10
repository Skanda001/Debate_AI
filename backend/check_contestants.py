import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parent / ".env")

from core.services.providers import build_contestants, ProviderError, _instantiate

raw = os.getenv("CONTESTANTS", "")
print("CONTESTANTS raw:", raw)
print()

for spec in [s.strip() for s in raw.split(",") if s.strip()]:
    try:
        p = _instantiate(spec)
        print(f"✅ {spec}  →  {p.id}  ({p.display_name})")
    except ProviderError as e:
        print(f"❌ {spec}  →  SKIPPED: {e}")
    except Exception as e:
        print(f"❌ {spec}  →  ERROR: {type(e).__name__}: {e}")

print("\n=== build_contestants() actual output ===")
contestants = build_contestants()
print(f"Count: {len(contestants)}")
for c in contestants:
    print(f"  • {c.id}")