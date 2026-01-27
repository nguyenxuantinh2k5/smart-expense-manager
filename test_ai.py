import os
from xmlrpc import client
from google import genai
from dotenv import load_dotenv

load_dotenv()

def test_gemini():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ LỖI: Không tìm thấy API Key trong file .env")
        return

    client = genai.Client(api_key=api_key)
    
    print("--- ĐANG KIỂM TRA DANH SÁCH MODEL KHẢ DỤNG ---")
    try:
        print("--- DANH SÁCH MODEL KEY CỦA BẠN ĐƯỢC DÙNG ---")
        models = client.models.list()
        for m in models:
            # Chú ý: Hãy nhìn kỹ xem nó in ra 'gemini-1.5-flash' hay 'models/gemini-1.5-flash'
            print(f"👉 {m.name}") 
    except Exception as e:
        print(f"Lỗi khi liệt kê: {e}")

if __name__ == "__main__":
    test_gemini()