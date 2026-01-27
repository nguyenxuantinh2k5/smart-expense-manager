import sys
import os

print(f"Python Executable: {sys.executable}")
print(f"CWD: {os.getcwd()}")
print("Sys Path:")
for p in sys.path:
    print(f"  - {p}")

try:
    import google
    print(f"Google module: {google}")
    print(f"Google path: {getattr(google, '__path__', 'No Path')}")
    print(f"Google file: {getattr(google, '__file__', 'No File')}")
except ImportError as e:
    print(f"Failed to import google: {e}")

try:
    from google import genai
    print(f"Successfully imported genai: {genai}")
except ImportError as e:
    print(f"Failed to import google.genai: {e}")

try:
    import google.generativeai
    print("Found legacy google.generativeai package")
except ImportError:
    print("Legacy google.generativeai not found")
