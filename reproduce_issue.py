
import os
import sys
import django
import io

# Set UTF-8 for stdout/stderr explicitly
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from expenses.ai_services import ExpenseAI

def test_ai():
    ai = ExpenseAI()
    test_cases = [
        "Ăn trưa 30k"
    ]

    print("--- STARTING AI ANALYSIS TEST ---", flush=True)
    for text in test_cases:
        print(f"\nTesting: '{text}'", flush=True)
        try:
            # We want to intercept the internal print in analyze_text or just trust the detailed exception
            # But analyze_text prints to stdout.
            result = ai.analyze_text(text)
            print(f"Final Result: {result}", flush=True)
        except Exception as e:
            print(f"Error: {e}", flush=True)
    print("\n--- END TEST ---", flush=True)

if __name__ == "__main__":
    test_ai()
