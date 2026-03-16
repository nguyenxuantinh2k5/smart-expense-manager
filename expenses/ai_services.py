import os
import json
import re
import time
import base64
from google import genai
from dotenv import load_dotenv

load_dotenv()

class ExpenseAI:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "❌ GEMINI_API_KEY not found in .env file!\n"
                "Please add: GEMINI_API_KEY=your_key_here\n"
                "Get your key from: https://aistudio.google.com/apikey"
            )
        
        if api_key.startswith("AIzaSy") == False:
            raise ValueError(
                "❌ Invalid API key format!\n"
                "Make sure it starts with 'AIzaSy...'"
            )
        self.client = genai.Client(api_key=api_key)
        # Sử dụng model đã xác nhận chạy được trên tài khoản của bạn
        self.model_id = "gemini-2.0-flash" 

    def clean_json_output(self, text):
        """Trích xuất JSON từ chuỗi văn bản bất kỳ, kể cả khi AI trả về rác"""
        try:
            text = re.sub(r'```json\s?|\s?```', '', text).strip()
            # Tìm nội dung nằm giữa dấu ngoặc nhọn đầu tiên và cuối cùng
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                json_str = match.group()
                # Xóa các dấu chấm/phẩy trong chuỗi số (VD: "30.000" -> "30000")
                # Đây là nguyên nhân chính khiến int() bị lỗi và trả về 0đ
                data = json.loads(json_str)
                
                # Chuẩn hóa amount: xử lý nhiều dạng đầu vào (30k, 30.000, 30,000, 30.000,50, 30kđ...)
                if 'amount' in data:
                    amount_raw = str(data['amount']).strip()

                    # Nhận biết ký hiệu 'k' / 'ngàn' và nhân với 1000
                    multiplier = 1
                    if re.search(r"\b\d+\s*(k|kđ|k₫|ngàn|ngan)\b", amount_raw, re.IGNORECASE):
                        multiplier = 1000

                    # Loại bỏ ký tự không phải số/., (ví dụ: "30.000" "30,000" "30k")
                    amount_clean = re.sub(r"[^\d\.,]", "", amount_raw)

                    # Nếu có nhiều dấu '.' (thường là phân cách hàng ngàn), xóa hết
                    if amount_clean.count('.') > 1:
                        amount_clean = amount_clean.replace('.', '')
                    # Nếu có cả ',' và '.', giả định ',' là phần nghìn và '.' là thập phân? Giữ '.'
                    if ',' in amount_clean and '.' in amount_clean:
                        amount_clean = amount_clean.replace(',', '')
                    # Nếu chỉ có ',', đổi thành '.' để parse float
                    elif ',' in amount_clean:
                        amount_clean = amount_clean.replace(',', '.')

                    try:
                        amount_float = float(amount_clean) if amount_clean else 0
                        data['amount'] = round(amount_float * multiplier, 2)
                    except ValueError:
                        data['amount'] = 0
                return data
            return None
        except Exception as e:
            print(f"DEBUG - Lỗi parse JSON: {e}")
            return None

    def _fallback_parse_text(self, text: str) -> dict:
        """Fallback khi AI không trả về JSON hợp lệ (hoặc mất kết nối).

        Mục tiêu: vẫn tạo được amount + category dựa trên quy tắc đơn giản.
        """
        text_lower = text.lower()

        # amount: tìm số đầu tiên, hỗ trợ 'k' / 'ngàn'
        amount = 0
        match = re.search(r"(\d+[\.,]?\d*)(\s*(k|kđ|k₫|ngàn|ngan))?", text_lower)
        if match:
            raw_num = match.group(1)
            has_k = bool(match.group(3))
            num = raw_num.replace(',', '.')
            if num.count('.') > 1:
                num = num.replace('.', '')
            try:
                amount = float(num) * (1000 if has_k else 1)
            except ValueError:
                amount = 0

        # category heuristic
        if any(w in text_lower for w in ['ăn', 'cafe', 'coffee', 'nhậu', 'lẩu', 'phở', 'bún', 'chợ']):
            category = 'Ăn uống'
        elif any(w in text_lower for w in ['taxi', 'grab', 'bus', 'xăng', 'xe', 'tàu', 'vé', 'dịch vụ vận chuyển']):
            category = 'Di chuyển'
        elif any(w in text_lower for w in ['sách', 'học', 'lớp', 'khóa học', 'đào tạo', 'thi']):
            category = 'Học tập'
        elif any(w in text_lower for w in ['điện', 'nước', 'internet', 'thuê', 'nhà', 'phòng', 'tiền nhà']):
            category = 'Sinh hoạt'
        else:
            category = 'Khác'

        return {'amount': round(amount, 2), 'category': category, 'note': text}

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
                    
        return self._fallback_parse_text(text)
    def analyze_image(self, image_path):
        """✅ IMPLEMENT MISSING: Phân tích ảnh hóa đơn"""
        """
        Sử dụng Gemini Vision để phân tích ảnh hóa đơn
        - Trích xuất số tiền
        - Xác định danh mục chi tiêu
        - Mô tả chi tiêu
        """
        try:
            # Kiểm tra file tồn tại
            if not os.path.exists(image_path):
                print(f"❌ Ảnh không tồn tại: {image_path}")
                return {"amount": 0, "category": "Khác", "note": "Không thể đọc ảnh"}

            # Đọc file ảnh
            with open(image_path, 'rb') as f:
                image_data = base64.standard_b64encode(f.read()).decode('utf-8')

            # Determine MIME type based on file extension
            ext = os.path.splitext(image_path)[1].lower()
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }
            mime_type = mime_types.get(ext, 'image/jpeg')

            # Prompt phân tích ảnh
            prompt = """
            Phân tích ảnh hóa đơn/biên lai này:
            Trích xuất thông tin và trả về JSON: {
                "amount": số tiền (chỉ số, không ký tự đặc biệt),
                "category": loại chi tiêu (Ăn uống, Di chuyển, Học tập, Sinh hoạt, Khác),
                "note": mô tả ngắn gọn về chi tiêu (tiếng Việt)
            }
            
            Lưu ý:
            - Nếu không tìm thấy số tiền, trả về 0
            - Chỉ trả về JSON, không giải thích
            - amount phải là số nguyên (ví dụ: 50000, 25500)
            """

            # Gọi Gemini Vision API
            for attempt in range(3):
                try:
                    response = self.client.models.generate_content(
                        model=self.model_id,
                        contents=[
                            prompt,
                            {
                                "type": "image",
                                "source": {
                                    "bytes": image_data,
                                    "mime_type": mime_type
                                }
                            }
                        ]
                    )
                    
                    result = self.clean_json_output(response.text)
                    if result:
                        print(f"✅ Phân tích ảnh thành công: {result}")
                        return result
                    break
                    
                except Exception as e:
                    if "429" in str(e):
                        print(f"⚠️ API rate limit, đợi 10 giây (lần {attempt+1})...")
                        time.sleep(10)
                    else:
                        print(f"❌ Lỗi phân tích ảnh: {e}")
                        break

            return {"amount": 0, "category": "Khác", "note": "Không thể phân tích ảnh"}

        except Exception as e:
            print(f"❌ Lỗi đọc file ảnh: {e}")
            return {"amount": 0, "category": "Khác", "note": f"Lỗi: {str(e)}"}