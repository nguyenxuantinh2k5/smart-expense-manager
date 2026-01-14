import re

class ExpenseAI:
    def __init__(self):
        self.categories = {
            'Ăn uống': ['ăn', 'uống', 'bún', 'cơm', 'phở', 'cafe', 'mì', 'snack'],
            'Di chuyển': ['xăng', 'grab', 'bus', 'xe', 'taxi'],
            'Học tập': ['sách', 'vở', 'học phí', 'khóa học'],
            'Sinh hoạt': ['điện', 'nước', 'trọ', 'siêu thị']
        }

    def analyze(self, text):
        text_lower = text.lower()
        amount = 0
        # Regex tìm số tiền (ví dụ: 50k, 100 ngàn, 1.2tr)
        match = re.search(r'(\d+(?:\.\d+)?)\s*(k|vnđ|ngàn|n|tr|triệu|đ)', text_lower)
        if match:
            val = float(match.group(1))
            unit = match.group(2)
            if unit in ['k', 'n', 'ngàn']: amount = val * 1000
            elif unit in ['tr', 'triệu']: amount = val * 1000000
            else: amount = val

        category = "Khác"
        for cat, keys in self.categories.items():
            if any(k in text_lower for k in keys):
                category = cat
                break
        return {'amount': amount, 'category': category, 'note': text}