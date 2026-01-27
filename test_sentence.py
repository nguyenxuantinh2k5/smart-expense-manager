import os
import json
import re
from google import genai
from dotenv import load_dotenv
import time

# 1. Khởi tạo môi trường
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_ID = "gemini-2.0-flash" # Model ổn định nhất trong danh sách của bạn

# 2. Danh sách các câu chi tiêu để "cọ xát"
test_cases = [
    "Ăn sáng phở bò 35k",                # Tiếng lóng 'k'
    "Nạp card điện thoại 50.000đ",       # Có dấu chấm và đơn vị đ
    "Mua giáo trình hết 120 ngàn",       # Đơn vị chữ 'ngàn'
    "Đi grab ra trường 22000",           # Số thuần túy
    "Tiền phòng tháng này 2 triệu",      # Đơn vị 'triệu'
    "Cafe trà đá vỉa hè 15.000 VNĐ",     # Định dạng tiền tệ chuẩn
    "Mua sắm quần áo ở chợ đêm 350000",  # Câu dài, số tiền lớn
]

def clean_and_parse(raw_text):
    """Hàm xử lý thô dữ liệu JSON từ AI"""
    try:
        # Lọc bỏ Markdown rác ```json ... ```
        clean_json = re.sub(r'```json\s?|\s?```', '', raw_text).strip()
        return json.loads(clean_json)
    except:
        return None

def run_suite():
    print(f"--- 📊 BẮT ĐẦU KIỂM THỬ LOGIC AI (Model: {MODEL_ID}) ---")
    
    for i, sentence in enumerate(test_cases, 1):
        print(f"\n[Test {i}]: '{sentence}'")
        
        prompt = f"""
        Phân tích chi tiêu: "{sentence}"
        Trả về JSON thô: {{"amount": int, "category": str, "note": str}}
        Lưu ý: 
        - amount phải là số nguyên (VD: 30k -> 30000, 2 triệu -> 2000000).
        - category chọn: Ăn uống, Di chuyển, Học tập, Sinh hoạt, Khác.
        """

        try:
            response = client.models.generate_content(model=MODEL_ID, contents=prompt)
            data = clean_and_parse(response.text)
            
            if data:
                amount = data.get('amount', 0)
                category = data.get('category', 'Chưa rõ')
                print(f"  💰 Số tiền: {amount:,} VNĐ")
                print(f"  🏷️ Danh mục: {category}")
                
                # Cảnh báo nếu logic bóc tách ra 0
                if amount == 0:
                    print("  ❌ LỖI LOGIC: AI không bóc tách được số tiền!")
            else:
                print("  ❌ LỖI: AI trả về định dạng không phải JSON!")
                
        except Exception as e:
            print(f"  ❌ LỖI HỆ THỐNG: {e}")
            time.sleep(13)
    print("\n--- ✅ HOÀN THÀNH KIỂM THỬ ---")

if __name__ == "__main__":
    run_suite()