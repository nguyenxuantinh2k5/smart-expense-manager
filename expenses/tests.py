from django.test import TestCase, Client
from django.contrib.auth.models import User
from .models import Category, Transaction
from .ai_services import ExpenseAI
import json
from unittest.mock import patch
from types import SimpleNamespace

class CategoryModelTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Ăn uống")
    
    def test_category_creation(self):
        self.assertEqual(self.category.name, "Ăn uống")
        self.assertEqual(str(self.category), "Ăn uống")

class TransactionModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.category = Category.objects.create(name="Di chuyển")
        self.transaction = Transaction.objects.create(
            user=self.user,
            amount=50000.00,
            category=self.category,
            note="Taxi đi làm"
        )
    
    def test_transaction_creation(self):
        self.assertEqual(self.transaction.amount, 50000.00)
        self.assertEqual(self.transaction.category.name, "Di chuyển")
        self.assertEqual(self.transaction.user.username, "testuser")

class AuthenticationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_login_page(self):
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 200)
    
    def test_login_successful(self):
        response = self.client.post('/login/', {
            'username': 'testuser',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, 302)  # Redirect
    
    def test_dashboard_requires_login(self):
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 302)  # Redirect to login

class AIServicesTest(TestCase):
    def setUp(self):
        self.ai = ExpenseAI()
    
    def test_clean_json_output_valid(self):
        text = '{"amount": 50000, "category": "Ăn uống", "note": "Cơm"}'
        result = self.ai.clean_json_output(text)
        self.assertEqual(result['amount'], 50000)
        self.assertEqual(result['category'], "Ăn uống")
    
    def test_clean_json_output_with_noise(self):
        text = 'Some text before {"amount": "30.000", "category": "Ăn", "note": "Cà phê"} and after'
        result = self.ai.clean_json_output(text)
        self.assertEqual(result['amount'], 30000)

    def test_analyze_text_local_food(self):
        result = self.ai.analyze_text("an trua 30k")
        self.assertEqual(result["amount"], 30000)
        self.assertEqual(result["category"], "\u0102n u\u1ed1ng")

    def test_analyze_text_local_transport(self):
        result = self.ai.analyze_text("grab di lam 50k")
        self.assertEqual(result["amount"], 50000)
        self.assertEqual(result["category"], "Di chuy\u1ec3n")

    def test_analyze_text_local_living_expense(self):
        result = self.ai.analyze_text("tien dien 300.000")
        self.assertEqual(result["amount"], 300000)
        self.assertEqual(result["category"], "Sinh ho\u1ea1t")

    def test_analyze_text_more_local_categories(self):
        cases = [
            ("mua ao shopee 250k", 250000, "Mua s\u1eafm"),
            ("kham benh o phong kham 200k", 200000, "S\u1ee9c kh\u1ecfe"),
            ("cat toc salon 80k", 80000, "L\u00e0m \u0111\u1eb9p"),
            ("xem phim cgv 120k", 120000, "Gi\u1ea3i tr\u00ed"),
            ("sua nha 2tr", 2000000, "Nh\u00e0 c\u1eeda"),
            ("khach san da nang 1.200.000", 1200000, "Du l\u1ecbch"),
            ("bao hiem xe 1tr", 1000000, "B\u1ea3o hi\u1ec3m"),
            ("netflix 260k", 260000, "\u0110\u0103ng k\u00fd d\u1ecbch v\u1ee5"),
            ("mua laptop 15tr", 15000000, "C\u00f4ng ngh\u1ec7"),
            ("ung ho tu thien 100k", 100000, "T\u1eeb thi\u1ec7n"),
        ]

        for text, amount, category in cases:
            with self.subTest(text=text):
                result = self.ai.analyze_text(text)
                self.assertEqual(result["amount"], amount)
                self.assertEqual(result["category"], category)

    def test_analyze_text_vietnamese_words_and_simple_math(self):
        cases = [
            ("an trua het ba muoi nghin", 30000, "\u0102n u\u1ed1ng"),
            ("hom nay di sieu thi het dau do hon hai tram", 200000, "Mua s\u1eafm"),
            ("chia tien an voi ban, phan minh mot nua hoa don 420k", 210000, "\u0102n u\u1ed1ng"),
            ("ve xem phim cho 3 nguoi, moi ve 95k", 285000, "Gi\u1ea3i tr\u00ed"),
            ("mua 2 ly tra sua 45k mot ly", 90000, "\u0102n u\u1ed1ng"),
        ]

        for text, amount, category in cases:
            with self.subTest(text=text):
                result = self.ai.analyze_text(text)
                self.assertEqual(result["amount"], amount)
                self.assertEqual(result["category"], category)

    def test_analyze_text_uses_gemini_when_local_is_incomplete(self):
        with patch.object(
            self.ai,
            "_analyze_text_with_gemini",
            return_value={"amount": 135000, "category": "Mua s\u1eafm", "note": "AI parsed"},
        ) as gemini:
            result = self.ai.analyze_text("mua do trong bill nay")

        gemini.assert_called_once()
        self.assertEqual(result["amount"], 135000)
        self.assertEqual(result["category"], "Mua s\u1eafm")

    def test_analyze_image_tries_fallback_model_after_quota_error(self):
        class FakeModels:
            def __init__(self):
                self.calls = []

            def generate_content(self, *, model, contents, config):
                self.calls.append(model)
                if model == "quota-model":
                    raise Exception("429 RESOURCE_EXHAUSTED")
                return SimpleNamespace(
                    text='{"amount": "225,000", "category": "Restaurant", "note": "Vinh Nguyen Res"}'
                )

        fake_models = FakeModels()
        self.ai._client = SimpleNamespace(models=fake_models)
        self.ai.image_model_ids = ["quota-model", "fallback-model"]

        with patch("os.path.exists", return_value=True), \
             patch.object(self.ai, "_build_image_part", return_value="image-part"), \
             patch.object(self.ai, "_generation_config", return_value=None):
            result = self.ai.analyze_image("bill1.jpg")

        self.assertEqual(fake_models.calls, ["quota-model", "fallback-model"])
        self.assertEqual(result["amount"], 225000)
        self.assertEqual(result["category"], "\u0102n u\u1ed1ng")

    def test_clean_item_json_output(self):
        text = """
        {"matched": true, "item": "Sprite", "quantity": 2, "unit_price": "25,000", "line_total": "50,000", "category": "Restaurant"}
        """
        result = self.ai.clean_item_json_output(text, "Sprite")

        self.assertTrue(result["matched"])
        self.assertEqual(result["item"], "Sprite")
        self.assertEqual(result["quantity"], 2)
        self.assertEqual(result["unit_price"], 25000)
        self.assertEqual(result["line_total"], 50000)
        self.assertEqual(result["category"], "\u0102n u\u1ed1ng")

    def test_analyze_image_item_sums_matching_rows(self):
        class FakeModels:
            def generate_content(self, *, model, contents, config):
                return SimpleNamespace(
                    text='{"matched": true, "item": "Coca", "quantity": 4, "unit_price": "25,000", "line_total": "100,000", "category": "Restaurant"}'
                )

        self.ai._client = SimpleNamespace(models=FakeModels())
        self.ai.image_model_ids = ["fallback-model"]

        with patch("os.path.exists", return_value=True), \
             patch.object(self.ai, "_build_image_part", return_value="image-part"), \
             patch.object(self.ai, "_generation_config", return_value=None):
            result = self.ai.analyze_image_item("bill1.jpg", "Coca")

        self.assertEqual(result["amount"], 100000)
        self.assertEqual(result["category"], "\u0102n u\u1ed1ng")
        self.assertEqual(result["item"], "Coca")
        self.assertEqual(result["quantity"], 4)
        self.assertEqual(result["unit_price"], 25000)
