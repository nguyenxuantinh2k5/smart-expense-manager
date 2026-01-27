import os
import json
import re
import time
from google import genai
from dotenv import load_dotenv

load_dotenv()

class ExpenseAI:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key)
        # Sử dụng model đã xác nhận chạy được trên tài khoản của bạn
        self.model_id = "gemini-2.0-flash" 

    def clean_json_output(self, text):
        """Trích xuất JSON từ chuỗi văn bản bất kỳ, kể cả khi AI trả về rác"""
        try:
            # Tìm nội dung nằm giữa dấu ngoặc nhọn đầu tiên và cuối cùng
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                json_str = match.group()
                # Xóa các dấu chấm/phẩy trong chuỗi số (VD: "30.000" -> "30000")
                # Đây là nguyên nhân chính khiến int() bị lỗi và trả về 0đ
                data = json.loads(json_str)
                
                # Chuẩn hóa amount: ép về kiểu int, xóa mọi ký tự không phải số
                if 'amount' in data:
                    amount_raw = str(data['amount'])
                    amount_clean = re.sub(r'[^\d]', '', amount_raw)
                    data['amount'] = int(amount_clean) if amount_clean else 0
                return data
            return None
        except Exception as e:
            print(f"DEBUG - Lỗi parse JSON: {e}")
            return None

    def analyze_text(self, text):
        """Hàm chính để phân tích văn bản chi tiêu"""
        prompt = f"""
        Phân tích câu chi tiêu: "{text}"
        Trả về JSON thô: {{"amount": int, "category": str, "note": str}}
        Lưu ý: 
        - amount: nhân 'k', 'ngàn' với 1000.
        - category: chọn (Ăn uống, Di chuyển, Học tập, Sinh hoạt, Khác).
        Chỉ trả về JSON, không giải thích.
        """
        
        # Thử lại tối đa 3 lần nếu gặp lỗi 429 (Retry Logic)
        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=self.model_id, 
                    contents=prompt
                )
                result = self.clean_json_output(response.text)
                if result:
                    return result
                break 
            except Exception as e:
                if "429" in str(e):
                    print(f"⚠️ Đang nghẽn mạng (429), đợi 10 giây để thử lại lần {attempt+1}...")
                    time.sleep(10) # Nghỉ để né giới hạn Google
                else:
                    print(f"❌ Lỗi hệ thống: {e}")
                    break
                    
        return {"amount": 0, "category": "Khác", "note": text}