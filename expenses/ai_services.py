import json
import os
import re
import time
import unicodedata
from io import BytesIO

from dotenv import load_dotenv

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - Pillow is in requirements, this is a safe fallback.
    Image = None
    ImageOps = None

load_dotenv()

CATEGORY_FOOD = "\u0102n u\u1ed1ng"
CATEGORY_TRANSPORT = "Di chuy\u1ec3n"
CATEGORY_EDUCATION = "H\u1ecdc t\u1eadp"
CATEGORY_LIVING = "Sinh ho\u1ea1t"
CATEGORY_SHOPPING = "Mua s\u1eafm"
CATEGORY_ENTERTAINMENT = "Gi\u1ea3i tr\u00ed"
CATEGORY_HEALTH = "S\u1ee9c kh\u1ecfe"
CATEGORY_BEAUTY = "L\u00e0m \u0111\u1eb9p"
CATEGORY_HOUSING = "Nh\u00e0 c\u1eeda"
CATEGORY_WORK = "C\u00f4ng vi\u1ec7c"
CATEGORY_TRAVEL = "Du l\u1ecbch"
CATEGORY_FAMILY = "Gia \u0111\u00ecnh"
CATEGORY_GIFTS = "Qu\u00e0 t\u1eb7ng"
CATEGORY_FINANCE = "T\u00e0i ch\u00ednh"
CATEGORY_INSURANCE = "B\u1ea3o hi\u1ec3m"
CATEGORY_INVESTMENT = "\u0110\u1ea7u t\u01b0"
CATEGORY_CHARITY = "T\u1eeb thi\u1ec7n"
CATEGORY_TAX_FEES = "Thu\u1ebf ph\u00ed"
CATEGORY_TECH = "C\u00f4ng ngh\u1ec7"
CATEGORY_SPORTS = "Th\u1ec3 thao"
CATEGORY_SUBSCRIPTION = "\u0110\u0103ng k\u00fd d\u1ecbch v\u1ee5"
CATEGORY_OTHER = "Kh\u00e1c"

CATEGORY_PATTERNS = [
    (
        CATEGORY_FOOD,
        [
            r"\b(an|an sang|an trua|an toi|com|com tam|com van phong|pho|bun|mi|my|chao|xoi|banh mi|banh|lau|nhau)\b",
            r"\b(cafe|coffee|ca phe|tra sua|tra dao|nuoc mia|sinh to|nuoc ep|nuoc ngot|do uong|do an|quan an|nha hang)\b",
            r"\b(coca|coke|pepsi|sprite|tonic|soda|sting|red bull|bo huc|7up)\b",
            r"\b(kfc|lotteria|mcdonald|pizza|tocotoco|highlands|phuc long|starbucks)\b",
        ],
    ),
    (
        CATEGORY_HEALTH,
        [
            r"\b(thuoc|nha thuoc|kham benh|bac si|benh vien|phong kham|vien phi|xet nghiem|noi soi)\b",
            r"\b(nha khoa|rang|mat kinh|kinh thuoc|tiem vaccine|vaccine|vitamin|thuc pham chuc nang)\b",
        ],
    ),
    (
        CATEGORY_BEAUTY,
        [
            r"\b(cat toc|lam toc|nhuom toc|salon|spa|massage|nail|lam mong|goi dau)\b",
            r"\b(my pham|skincare|kem chong nang|son moi|nuoc hoa|cham soc da|lam dep)\b",
        ],
    ),
    (
        CATEGORY_GIFTS,
        [
            r"\b(qua tang|mua qua|tang qua|sinh nhat|mung cuoi|mung sinh nhat|mung tuoi|li xi|thiep)\b",
        ],
    ),
    (
        CATEGORY_INSURANCE,
        [
            r"\b(bao hiem|bhyt|bhxh|bao hiem y te|bao hiem xe|bao hiem nhan tho|bao hiem nha)\b",
        ],
    ),
    (
        CATEGORY_TRAVEL,
        [
            r"\b(du lich|tour|khach san|resort|homestay|booking|airbnb|visa|ho chieu|passport)\b",
            r"\b(ve may bay|may bay|san bay|tau bay|di choi xa|nghi duong)\b",
        ],
    ),
    (
        CATEGORY_TRANSPORT,
        [
            r"\b(taxi|grab|gojek|be bike|be car|xanh sm|bus|xe buyt|metro|tau dien|tau hoa|ve xe|ve tau)\b",
            r"\b(xang|do xang|gui xe|giu xe|bai xe|sua xe|rua xe|bao duong xe|dang kiem|phi cau duong)\b",
            r"\b(di chuyen|van chuyen|ship|shipping|giao hang|cuoc xe|cuoc taxi)\b",
        ],
    ),
    (
        CATEGORY_EDUCATION,
        [
            r"\b(hoc phi|khoa hoc|lop hoc|dao tao|di thi|on thi|thi cu|le phi thi|trung tam|gia su|hoc online)\b",
            r"\b(sach|giao trinh|tai lieu|but|vo|dung cu hoc tap|van phong pham hoc sinh)\b",
        ],
    ),
    (
        CATEGORY_HOUSING,
        [
            r"\b(sua nha|son nha|noi that|do gia dung|tu lanh|may giat|dieu hoa|may lanh|bep|noi com)\b",
            r"\b(giuong|nem|chan ga|den|ban ghe|tu quan ao|rem cua|vat lieu xay dung)\b",
        ],
    ),
    (
        CATEGORY_LIVING,
        [
            r"\b(tien dien|tien nuoc|dien nuoc|internet|wifi|cap quang|truyen hinh cap)\b",
            r"\b(thue nha|tien nha|tien phong|tien tro|phong tro|chung cu|phi quan ly|gas|sinh hoat)\b",
            r"\b(cuoc dien thoai|nap dien thoai|the dien thoai|rac|giat ui|giat say)\b",
        ],
    ),
    (
        CATEGORY_ENTERTAINMENT,
        [
            r"\b(xem phim|rap phim|cinema|cgv|lotte cinema|galaxy|bhd|karaoke|bar|pub|concert|show)\b",
            r"\b(game|steam|playstation|net cafe|giai tri|di choi|ve show|ve xem phim|nhac hoi)\b",
        ],
    ),
    (
        CATEGORY_SPORTS,
        [
            r"\b(gym|yoga|fitness|boi|boi loi|the thao|bong da|cau long|tennis|pickleball|chay bo)\b",
            r"\b(ve san|thue san|giay the thao|do tap|pt|huan luyen vien)\b",
        ],
    ),
    (
        CATEGORY_SUBSCRIPTION,
        [
            r"\b(netflix|spotify|youtube premium|icloud|google one|office 365|microsoft 365|notion|canva)\b",
            r"\b(thue bao|subscription|dang ky dich vu|gia han|goi cuoc|membership|hoi vien)\b",
        ],
    ),
    (
        CATEGORY_TECH,
        [
            r"\b(dien thoai|laptop|may tinh|pc|tablet|ipad|tai nghe|chuot|ban phim|man hinh|sac du phong)\b",
            r"\b(phan mem|app|domain|hosting|server|vps|cloud|o cung|usb|camera|do cong nghe)\b",
        ],
    ),
    (
        CATEGORY_WORK,
        [
            r"\b(cong tac|gap khach|tiep khach|in an|photocopy|name card|van phong pham|dong phuc)\b",
            r"\b(chi phi cong viec|lam viec|coworking|gui ho so|chuyen phat nhanh)\b",
        ],
    ),
    (
        CATEGORY_FAMILY,
        [
            r"\b(cho con|cho be|sua cho be|ta bim|bim sua|do tre em|do choi tre em|giu tre)\b",
            r"\b(bo me|ong ba|gia dinh|nguoi than|cham soc gia dinh)\b",
        ],
    ),
    (
        CATEGORY_FINANCE,
        [
            r"\b(tra no|lai vay|tien lai|vay ngan hang|the tin dung|tin dung|ngan hang|rut tien)\b",
            r"\b(chuyen khoan|phi ngan hang|phi duy tri|sao ke|tat toan|vay)\b",
        ],
    ),
    (
        CATEGORY_INVESTMENT,
        [
            r"\b(dau tu|co phieu|chung khoan|trai phieu|quy mo|crypto|bitcoin|vang|mua vang|tiet kiem)\b",
        ],
    ),
    (
        CATEGORY_CHARITY,
        [
            r"\b(tu thien|ung ho|quyen gop|cuu tro|dong gop|giup do|donate)\b",
        ],
    ),
    (
        CATEGORY_TAX_FEES,
        [
            r"\b(thue thu nhap|thue tncn|vat|le phi|phi hanh chinh|phi dich vu|phi phat|nop phat|tien phat)\b",
        ],
    ),
    (
        CATEGORY_SHOPPING,
        [
            r"\b(shopee|lazada|tiki|sendo|amazon|order|dat hang|mua sam|shopping|hang online)\b",
            r"\b(sieu thi|bach hoa xanh|winmart|coopmart|big c|go!|lottemart|aeon|tap hoa)\b",
            r"\b(ao|quan|giay|dep|tui xach|balo|dong ho|phu kien|quan ao|thoi trang)\b",
            r"\b(mua|sam)\b",
        ],
    ),
]

CATEGORY_NAMES = [category for category, _patterns in CATEGORY_PATTERNS] + [CATEGORY_OTHER]

CATEGORY_ALIASES = {
    "food": CATEGORY_FOOD,
    "eat": CATEGORY_FOOD,
    "restaurant": CATEGORY_FOOD,
    "transport": CATEGORY_TRANSPORT,
    "transportation": CATEGORY_TRANSPORT,
    "commute": CATEGORY_TRANSPORT,
    "education": CATEGORY_EDUCATION,
    "study": CATEGORY_EDUCATION,
    "living": CATEGORY_LIVING,
    "utilities": CATEGORY_LIVING,
    "home utilities": CATEGORY_LIVING,
    "shopping": CATEGORY_SHOPPING,
    "entertainment": CATEGORY_ENTERTAINMENT,
    "health": CATEGORY_HEALTH,
    "healthcare": CATEGORY_HEALTH,
    "beauty": CATEGORY_BEAUTY,
    "housing": CATEGORY_HOUSING,
    "home": CATEGORY_HOUSING,
    "work": CATEGORY_WORK,
    "business": CATEGORY_WORK,
    "travel": CATEGORY_TRAVEL,
    "family": CATEGORY_FAMILY,
    "gift": CATEGORY_GIFTS,
    "gifts": CATEGORY_GIFTS,
    "finance": CATEGORY_FINANCE,
    "financial": CATEGORY_FINANCE,
    "insurance": CATEGORY_INSURANCE,
    "investment": CATEGORY_INVESTMENT,
    "charity": CATEGORY_CHARITY,
    "donation": CATEGORY_CHARITY,
    "tax": CATEGORY_TAX_FEES,
    "fees": CATEGORY_TAX_FEES,
    "technology": CATEGORY_TECH,
    "tech": CATEGORY_TECH,
    "sports": CATEGORY_SPORTS,
    "sport": CATEGORY_SPORTS,
    "subscription": CATEGORY_SUBSCRIPTION,
}

MONEY_RE = re.compile(
    r"(?<!\w)(?P<number>\d+(?:[.,]\d+)*)(?:\s*(?P<unit>k|nghin|ngan|tr|trieu|m|vnd|d|dong))?\b",
    re.IGNORECASE,
)

MONEY_VALUE_RE = r"(?P<number>\d+(?:[.,]\d+)*)(?:\s*(?P<unit>k|nghin|ngan|tr|trieu|m|vnd|d|dong))?"
COUNT_UNITS_RE = r"(?:nguoi|ve|ly|cai|mon|phan|suat|goi|thang|ngay|lan|chiec|bo)"

DIGIT_WORDS = {
    "khong": 0,
    "mot": 1,
    "moi": 1,
    "hai": 2,
    "ba": 3,
    "bon": 4,
    "tu": 4,
    "nam": 5,
    "lam": 5,
    "sau": 6,
    "bay": 7,
    "tam": 8,
    "chin": 9,
}
NUMBER_CONNECTORS = {"le", "linh", "hon", "khoang", "gan", "dau", "do"}
NUMBER_SCALES = {"muoi", "tram", "nghin", "ngan", "trieu", "ty", "dong", "ruoi"}
NUMBER_PHRASE_TOKENS = set(DIGIT_WORDS) | NUMBER_CONNECTORS | NUMBER_SCALES
MONEY_CONTEXT_RE = re.compile(
    r"\b(tien|het|mat|ton|chi|tra|mua|dong|hoa don|bill|gia|phi|ve|an|u?ong|di|thue)\b"
)


def _normalize_text(value):
    value = (value or "").lower().replace("\u0111", "d")
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", value).strip()


def _env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name, default):
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _split_env_list(name, default):
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class ExpenseAI:
    _text_cache = {}

    def __init__(self):
        self.model_id = os.getenv("GEMINI_MODEL_ID", "gemini-flash-lite-latest")
        self.image_model_ids = self._build_image_model_list()
        self.text_ai_mode = os.getenv("EXPENSE_TEXT_AI_MODE", "fallback").strip().lower()
        self.text_max_retries = _env_int("GEMINI_TEXT_MAX_RETRIES", 1)
        self.image_max_retries = _env_int("GEMINI_IMAGE_MAX_RETRIES", 2)
        self.retry_delay_seconds = _env_float("GEMINI_RETRY_DELAY_SECONDS", 2)
        self._client = None

    def _build_image_model_list(self):
        configured_models = _split_env_list(
            "GEMINI_IMAGE_MODEL_IDS",
            "gemini-flash-lite-latest,gemini-2.0-flash-lite,gemini-2.5-flash",
        )
        model_ids = [self.model_id] + configured_models
        return list(dict.fromkeys(model_ids))

    @property
    def client(self):
        if self._client is None:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError(
                    "GEMINI_API_KEY not found in .env file. "
                    "Add GEMINI_API_KEY=your_key_here or use EXPENSE_TEXT_AI_MODE=local."
                )
            if not api_key.startswith("AIzaSy"):
                raise ValueError("Invalid GEMINI_API_KEY format. It should start with 'AIzaSy'.")

            from google import genai

            self._client = genai.Client(api_key=api_key)
        return self._client

    def clean_json_output(self, text):
        try:
            text = re.sub(r"```json\s?|\s?```", "", str(text or "")).strip()
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return None

            data = json.loads(match.group())
            data["amount"] = self._parse_amount_value(data.get("amount"))
            data["category"] = self._normalize_category(data.get("category"))
            data["note"] = str(data.get("note") or "").strip()
            return data
        except Exception as exc:
            print(f"DEBUG - JSON parse error: {exc}")
            return None

    def clean_item_json_output(self, text, item_name):
        try:
            text = re.sub(r"```json\s?|\s?```", "", str(text or "")).strip()
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return None

            data = json.loads(match.group())
            quantity = self._parse_quantity_value(data.get("quantity", 0))
            unit_price = self._parse_amount_value(
                data.get("unit_price") or data.get("unitPrice") or data.get("price") or data.get("don_gia")
            )
            line_total = self._parse_amount_value(
                data.get("line_total") or data.get("lineTotal") or data.get("total") or data.get("thanh_tien")
            )
            if line_total <= 0 and unit_price > 0 and quantity > 0:
                line_total = unit_price * quantity

            matched = self._parse_bool(data.get("matched", line_total > 0))
            matched_item = str(data.get("item") or data.get("matched_item") or item_name).strip()
            category = data.get("category") or self._match_category(f"{item_name} {matched_item}")

            return {
                "matched": matched,
                "item": matched_item,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": round(line_total, 2),
                "category": self._normalize_category(category),
                "note": str(data.get("note") or "").strip(),
            }
        except Exception as exc:
            print(f"DEBUG - Item JSON parse error: {exc}")
            return None

    def analyze_text(self, text):
        text = (text or "").strip()
        local_result = self._fallback_parse_text(text)
        cache_key = _normalize_text(text)

        if not text:
            return local_result

        if self.text_ai_mode in {"local", "fast", "off"}:
            return local_result

        local_is_complete = local_result["amount"] > 0 and local_result["category"] != CATEGORY_OTHER
        if self.text_ai_mode != "always" and local_is_complete:
            return local_result

        cached = self._text_cache.get(cache_key)
        if cached:
            return dict(cached)

        ai_result = self._analyze_text_with_gemini(text)
        if not ai_result:
            return local_result

        result = {
            "amount": ai_result.get("amount") or local_result["amount"],
            "category": ai_result.get("category") or local_result["category"],
            "note": ai_result.get("note") or text,
        }
        self._text_cache[cache_key] = dict(result)
        return result

    def analyze_image(self, image_path):
        if not os.path.exists(image_path):
            return {"amount": 0, "category": CATEGORY_OTHER, "note": "Khong the doc anh"}

        categories = ", ".join(CATEGORY_NAMES)
        prompt = f"""
        Analyze this Vietnamese receipt image and return only compact JSON:
        {{"amount": number, "category": string, "note": string}}
        category must be one of: {categories}.
        amount must be the final total paid in VND, without currency symbols.
        Prefer labels like T.Cong, Tong cong, Thanh tien, Tong tien, Tien mat, Total, Grand total.
        Do not return unit prices or line item subtotals when a final total is visible.
        """

        contents = [prompt, self._build_image_part(image_path)]
        config = self._generation_config(max_tokens=160)

        partial_result = None
        last_error_note = "Khong the phan tich anh"
        for model_id in self.image_model_ids:
            for attempt in range(max(1, self.image_max_retries)):
                try:
                    response = self.client.models.generate_content(
                        model=model_id,
                        contents=contents,
                        config=config,
                    )
                    result = self.clean_json_output(response.text)
                    if result and result.get("amount", 0) > 0:
                        return result
                    if result and partial_result is None:
                        partial_result = result
                    break
                except Exception as exc:
                    message = str(exc)
                    if "429" in message:
                        last_error_note = "Gemini het quota hoac dang bi rate limit. Hay doi mot lat, doi model, hoac kiem tra API key."
                        print(f"Image AI quota/rate error on {model_id}; trying fallback model.")
                        break
                    if attempt + 1 < self.image_max_retries:
                        time.sleep(self.retry_delay_seconds)
                        continue
                    last_error_note = f"Loi Gemini khi phan tich anh: {exc}"
                    print(f"Image AI error on {model_id}: {exc}")
                    break

        if partial_result:
            return partial_result

        return {"amount": 0, "category": CATEGORY_OTHER, "note": last_error_note}

    def analyze_image_item(self, image_path, item_name):
        item_name = (item_name or "").strip()
        if not item_name:
            return self.analyze_image(image_path)

        if not os.path.exists(image_path):
            return {"amount": 0, "category": CATEGORY_OTHER, "note": "Khong the doc anh"}

        categories = ", ".join(CATEGORY_NAMES)
        prompt = f"""
        Analyze this Vietnamese receipt image and find the requested line item: "{item_name}".
        Return only compact JSON:
        {{
          "matched": boolean,
          "item": string,
          "quantity": number,
          "unit_price": number,
          "line_total": number,
          "category": string,
          "note": string
        }}
        category must be one of: {categories}.
        Match item names fuzzily, ignoring case, accents, spaces, and minor OCR errors.
        If the requested item appears in multiple rows, sum quantity and line_total across all matching rows.
        unit_price is the per-item price; line_total is quantity * unit_price or the row total.
        If the item is not visible, return matched=false and numeric fields as 0.
        """

        contents = [prompt, self._build_image_part(image_path)]
        config = self._generation_config(max_tokens=220)

        partial_result = None
        last_error_note = "Khong tim thay mon trong hoa don"
        for model_id in self.image_model_ids:
            for attempt in range(max(1, self.image_max_retries)):
                try:
                    response = self.client.models.generate_content(
                        model=model_id,
                        contents=contents,
                        config=config,
                    )
                    item_result = self.clean_item_json_output(response.text, item_name)
                    if item_result and item_result.get("matched") and item_result.get("line_total", 0) > 0:
                        return self._item_result_to_expense_result(item_result, item_name)
                    if item_result and partial_result is None:
                        partial_result = item_result
                    break
                except Exception as exc:
                    message = str(exc)
                    if "429" in message:
                        last_error_note = "Gemini het quota hoac dang bi rate limit. Hay doi mot lat, doi model, hoac kiem tra API key."
                        print(f"Image item AI quota/rate error on {model_id}; trying fallback model.")
                        break
                    if attempt + 1 < self.image_max_retries:
                        time.sleep(self.retry_delay_seconds)
                        continue
                    last_error_note = f"Loi Gemini khi boc gia mon: {exc}"
                    print(f"Image item AI error on {model_id}: {exc}")
                    break

        if partial_result:
            return self._item_result_to_expense_result(partial_result, item_name)

        return {"amount": 0, "category": CATEGORY_OTHER, "note": last_error_note}

    def _item_result_to_expense_result(self, item_result, requested_item):
        if not item_result.get("matched"):
            return {
                "amount": 0,
                "category": CATEGORY_OTHER,
                "note": f"Khong tim thay mon '{requested_item}' trong hoa don",
            }

        item = item_result.get("item") or requested_item
        quantity = item_result.get("quantity") or 0
        unit_price = item_result.get("unit_price") or 0
        line_total = item_result.get("line_total") or 0
        note_parts = [f"{item} trong hoa don"]
        if quantity:
            note_parts.append(f"SL {quantity:g}")
        if unit_price:
            note_parts.append(f"don gia {unit_price:g}")

        return {
            "amount": round(line_total, 2),
            "category": item_result.get("category") or CATEGORY_OTHER,
            "note": " - ".join(note_parts),
            "item": item,
            "quantity": quantity,
            "unit_price": unit_price,
            "line_total": line_total,
        }

    def _fallback_parse_text(self, text):
        amount = self._extract_amount(text)
        category = self._match_category(text)
        return {"amount": round(amount, 2), "category": category, "note": text}

    def _analyze_text_with_gemini(self, text):
        categories = ", ".join(CATEGORY_NAMES)
        prompt = f"""
        Analyze this Vietnamese expense sentence and return only compact JSON:
        "{text}"
        Schema: {{"amount": number, "category": string, "note": string}}
        category must be one of: {categories}.
        Convert Vietnamese number words to VND amounts.
        Convert k/nghin/ngan to thousands and tr/trieu to millions.
        If quantity and unit price are present, multiply them.
        If the sentence says one half / split bill / chia N nguoi, return the user's share.
        """
        config = self._generation_config(max_tokens=128)

        for attempt in range(max(1, self.text_max_retries)):
            try:
                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=prompt,
                    config=config,
                )
                return self.clean_json_output(response.text)
            except Exception as exc:
                if "429" in str(exc):
                    print("Text AI rate limited; using local parser result.")
                    break
                if attempt + 1 < self.text_max_retries:
                    time.sleep(self.retry_delay_seconds)
                    continue
                print(f"Text AI error: {exc}")
                break

        return None

    def _generation_config(self, max_tokens):
        from google.genai import types

        return types.GenerateContentConfig(
            temperature=0,
            maxOutputTokens=max_tokens,
            responseMimeType="application/json",
        )

    def _build_image_part(self, image_path):
        from google.genai import types

        image_bytes, mime_type = self._read_optimized_image(image_path)
        return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    def _read_optimized_image(self, image_path):
        if Image is not None:
            try:
                with Image.open(image_path) as img:
                    img = ImageOps.exif_transpose(img)
                    img.thumbnail((1280, 1280))
                    if img.mode not in {"RGB", "L"}:
                        img = img.convert("RGB")

                    output = BytesIO()
                    img.save(output, format="JPEG", quality=85, optimize=True)
                    return output.getvalue(), "image/jpeg"
            except Exception as exc:
                print(f"Image optimize error, sending original file: {exc}")

        with open(image_path, "rb") as file:
            image_bytes = file.read()

        ext = os.path.splitext(image_path)[1].lower()
        mime_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(ext, "image/jpeg")
        return image_bytes, mime_type

    def _extract_amount(self, text):
        normalized = _normalize_text(text)
        numeric_amount = self._extract_numeric_amount(normalized)
        written_amount = self._extract_written_amount(normalized)
        amount = max(numeric_amount, written_amount)

        quantity_total = self._extract_quantity_total(normalized)
        if quantity_total > 0:
            amount = quantity_total

        split_amount = self._extract_split_amount(normalized, amount)
        if split_amount > 0:
            amount = split_amount

        return amount

    def _extract_numeric_amount(self, normalized):
        best_amount = 0
        best_score = 0

        for match in MONEY_RE.finditer(normalized):
            amount = self._parse_amount_value(match.group("number"), match.group("unit"))
            if amount <= 0:
                continue

            number = match.group("number")
            unit = (match.group("unit") or "").lower()
            has_unit = bool(unit)
            has_separator = "." in number or "," in number

            if has_unit:
                score = 3
            elif has_separator or amount >= 1000:
                score = 2
            else:
                score = 1

            if score > best_score or (score == best_score and amount > best_amount):
                best_score = score
                best_amount = amount

        return best_amount

    def _extract_written_amount(self, normalized):
        normalized = self._mark_approximate_tam(normalized)
        tokens = normalized.split()
        best_amount = 0

        index = 0
        while index < len(tokens):
            if tokens[index] not in NUMBER_PHRASE_TOKENS:
                index += 1
                continue

            end = index
            while end < len(tokens) and tokens[end] in NUMBER_PHRASE_TOKENS:
                end += 1

            phrase_tokens = tokens[index:end]
            parsed = self._parse_vietnamese_number_phrase(phrase_tokens)
            if parsed:
                value, has_explicit_money_unit, has_hundred_scale = parsed
                if has_explicit_money_unit:
                    best_amount = max(best_amount, value)
                elif has_hundred_scale and MONEY_CONTEXT_RE.search(normalized):
                    best_amount = max(best_amount, value * 1_000)

            index = end

        return best_amount

    def _mark_approximate_tam(self, normalized):
        digit_words = "|".join(word for word in DIGIT_WORDS if word != "tam")
        return re.sub(rf"\btam\s+(?=({digit_words}|tam)\b)", "khoang ", normalized)

    def _parse_vietnamese_number_phrase(self, tokens):
        tokens = [token for token in tokens if token not in {"hon", "khoang", "gan", "dau", "do"}]
        if not tokens:
            return None

        total = 0
        group = []
        has_explicit_money_unit = False
        has_hundred_scale = "tram" in tokens
        last_large_scale = None
        index = 0

        while index < len(tokens):
            token = tokens[index]

            if token in {"ty", "trieu", "nghin", "ngan", "dong"}:
                scale = {
                    "ty": 1_000_000_000,
                    "trieu": 1_000_000,
                    "nghin": 1_000,
                    "ngan": 1_000,
                    "dong": 1,
                }[token]
                group_value = self._parse_under_thousand(group)
                if group_value == 0:
                    group_value = 1
                total += group_value * scale
                group = []
                has_explicit_money_unit = True
                last_large_scale = scale
                index += 1
                continue

            if token == "ruoi":
                if last_large_scale:
                    total += last_large_scale / 2
                else:
                    group.append(token)
                index += 1
                continue

            group.append(token)
            index += 1

        if group:
            total += self._parse_under_thousand(group)

        if total <= 0:
            return None

        return total, has_explicit_money_unit, has_hundred_scale

    def _parse_under_thousand(self, tokens):
        tokens = [token for token in tokens if token not in {"le", "linh"}]
        if not tokens:
            return 0

        if "tram" in tokens:
            index = tokens.index("tram")
            hundreds = self._parse_digit_word(tokens[index - 1]) if index > 0 else 1
            remainder = tokens[index + 1 :]
            value = hundreds * 100
            if remainder == ["ruoi"]:
                return value + 50
            return value + self._parse_tens(remainder)

        return self._parse_tens(tokens)

    def _parse_tens(self, tokens):
        if not tokens:
            return 0

        if tokens[0] == "muoi":
            return 10 + self._parse_digit_word(tokens[1]) if len(tokens) > 1 else 10

        if len(tokens) >= 2 and tokens[1] == "muoi":
            value = self._parse_digit_word(tokens[0]) * 10
            if len(tokens) > 2:
                value += self._parse_digit_word(tokens[2])
            return value

        if tokens == ["ruoi"]:
            return 0.5

        return self._parse_digit_word(tokens[0])

    def _parse_digit_word(self, token):
        return DIGIT_WORDS.get(token, 0)

    def _extract_quantity_total(self, normalized):
        unit_price = self._extract_unit_price(normalized)
        if unit_price <= 0:
            return 0

        quantity = self._extract_quantity(normalized)
        if quantity <= 1:
            return 0

        return unit_price * quantity

    def _extract_unit_price(self, normalized):
        patterns = [
            rf"\bmoi\s+\w+\s+{MONEY_VALUE_RE}\b",
            rf"\b{MONEY_VALUE_RE}\s*(?:/|mot|1)\s*{COUNT_UNITS_RE}\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match:
                amount = self._parse_amount_value(match.group("number"), match.group("unit"))
                if amount > 0:
                    return amount

        return 0

    def _extract_quantity(self, normalized):
        quantities = []
        pattern = rf"\b(?P<qty>\d+|mot|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi)\s*{COUNT_UNITS_RE}\b"
        for match in re.finditer(pattern, normalized):
            qty = match.group("qty")
            if qty.isdigit():
                value = int(qty)
            else:
                value = 10 if qty == "muoi" else self._parse_digit_word(qty)
            if value > 0:
                quantities.append(value)

        return max(quantities) if quantities else 0

    def _extract_split_amount(self, normalized, amount):
        if amount <= 0:
            return 0

        if re.search(r"\b(mot nua|nua hoa don|chia doi|chia 2|phan minh mot nua)\b", normalized):
            return amount / 2

        match = re.search(rf"\bchia\s+(?P<qty>\d+|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi)\s*{COUNT_UNITS_RE}\b", normalized)
        if not match:
            return 0

        qty = match.group("qty")
        divisor = int(qty) if qty.isdigit() else (10 if qty == "muoi" else self._parse_digit_word(qty))
        if divisor > 1:
            return amount / divisor

        return 0

    def _parse_bool(self, value):
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        normalized = _normalize_text(str(value))
        return normalized in {"true", "1", "yes", "y", "co", "dung", "matched"}

    def _parse_quantity_value(self, value):
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            return float(value)

        normalized = _normalize_text(str(value))
        number_match = re.search(r"\d+(?:[.,]\d+)?", normalized)
        if number_match:
            return float(number_match.group().replace(",", "."))

        parsed = self._parse_vietnamese_number_phrase(normalized.split())
        if parsed:
            quantity, _has_explicit_money_unit, _has_hundred_scale = parsed
            return float(quantity)

        return 0

    def _parse_amount_value(self, value, unit=None):
        if value is None:
            return 0

        raw = _normalize_text(str(value)).replace(" ", "")
        unit = _normalize_text(unit or "")

        inline_unit = re.search(r"(k|nghin|ngan|tr|trieu|m|vnd|d|dong)$", raw)
        if inline_unit:
            unit = inline_unit.group(1)
            raw = raw[: inline_unit.start()]

        number = re.sub(r"[^\d.,]", "", raw)
        if not number:
            return 0

        if "," in number and "." in number:
            if number.rfind(",") > number.rfind("."):
                number = number.replace(".", "").replace(",", ".")
            else:
                number = number.replace(",", "")
        elif "," in number:
            parts = number.split(",")
            if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
                number = "".join(parts)
            else:
                number = number.replace(",", ".")
        elif "." in number:
            parts = number.split(".")
            if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
                number = "".join(parts)

        try:
            amount = float(number)
        except ValueError:
            return 0

        if unit in {"k", "nghin", "ngan"}:
            amount *= 1_000
        elif unit in {"tr", "trieu", "m"}:
            amount *= 1_000_000

        return round(amount, 2)

    def _match_category(self, text):
        normalized = _normalize_text(text)
        best_category = CATEGORY_OTHER
        best_score = 0

        for category, patterns in CATEGORY_PATTERNS:
            score = sum(1 for pattern in patterns if re.search(pattern, normalized))
            if score > best_score:
                best_score = score
                best_category = category

        return best_category

    def _normalize_category(self, value):
        normalized = _normalize_text(str(value or ""))
        if not normalized:
            return CATEGORY_OTHER

        for category, patterns in CATEGORY_PATTERNS:
            category_name = _normalize_text(category)
            if normalized == category_name:
                return category

        alias = CATEGORY_ALIASES.get(normalized)
        if alias:
            return alias

        for category, patterns in CATEGORY_PATTERNS:
            if any(re.search(pattern, normalized) for pattern in patterns):
                return category

        return CATEGORY_OTHER
