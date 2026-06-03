from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile
from .models import Budget, Category, CategoryRule, RecurringExpense, SplitBill, Transaction
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

    def test_dashboard_has_feature_links(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/smart-report/')
        self.assertContains(response, '/split-bill/')
        self.assertContains(response, '/recurring/')
        self.assertContains(response, 'Xuất XLSX')

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

class FeatureWorkflowTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='featureuser',
            email='feature@example.com',
            password='testpass123'
        )
        self.client.login(username='featureuser', password='testpass123')
        self.food = Category.objects.create(name="\u0102n u\u1ed1ng")
        self.other = Category.objects.create(name="Kh\u00e1c")

    def test_smart_report_answers_top_category(self):
        Transaction.objects.create(user=self.user, amount=100000, category=self.food, note='Cơm')
        Transaction.objects.create(user=self.user, amount=30000, category=self.other, note='Khác')

        response = self.client.post('/smart-report/', {
            'question': 'Tháng này tôi tốn nhiều nhất vào đâu?'
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn("\u0102n u\u1ed1ng", response.context['result']['answer'])

    def test_dashboard_formats_money_with_vietnamese_grouping(self):
        Budget.objects.create(user=self.user, amount=5000000)
        Transaction.objects.create(user=self.user, amount=1000000, category=self.food, note='Tiền ăn')
        Transaction.objects.create(user=self.user, amount=973000, category=self.other, note='Khác')

        response = self.client.get('/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1.973.000đ')
        self.assertContains(response, '986.500đ')
        self.assertContains(response, '5.000.000đ')
        self.assertContains(response, '3.027.000đ')
        self.assertNotContains(response, 'value="None"')

    def test_dashboard_filters_by_single_fields_and_combines_them(self):
        transport = Category.objects.create(name='Di chuyển')
        food_current = Transaction.objects.create(
            user=self.user,
            amount=100000,
            category=self.food,
            note='Cơm văn phòng',
            raw_text='an trua 100k',
        )
        transport_current = Transaction.objects.create(
            user=self.user,
            amount=50000,
            category=transport,
            note='Taxi sân bay',
            raw_text='grab 50k',
        )
        food_old = Transaction.objects.create(
            user=self.user,
            amount=70000,
            category=self.food,
            note='Cơm tháng trước',
            raw_text='com cu 70k',
        )

        Transaction.objects.filter(id=food_current.id).update(
            created_at=timezone.make_aware(datetime(2026, 6, 10, 12, 0))
        )
        Transaction.objects.filter(id=transport_current.id).update(
            created_at=timezone.make_aware(datetime(2026, 6, 11, 12, 0))
        )
        Transaction.objects.filter(id=food_old.id).update(
            created_at=timezone.make_aware(datetime(2026, 5, 20, 12, 0))
        )

        response = self.client.get('/dashboard/', {'search': 'Cơm'})
        self.assertContains(response, 'Cơm văn phòng')
        self.assertContains(response, 'Cơm tháng trước')
        self.assertNotContains(response, 'Taxi sân bay')

        response = self.client.get('/dashboard/', {'search': '100.000'})
        self.assertContains(response, 'Cơm văn phòng')
        self.assertNotContains(response, 'Taxi sân bay')
        self.assertNotContains(response, 'Cơm tháng trước')

        response = self.client.get('/dashboard/', {'category': "\u0102n u\u1ed1ng"})
        self.assertContains(response, 'Cơm văn phòng')
        self.assertContains(response, 'Cơm tháng trước')
        self.assertNotContains(response, 'Taxi sân bay')

        response = self.client.get('/dashboard/', {
            'date_from': '2026-06-01',
            'date_to': '2026-06-30',
        })
        self.assertContains(response, 'Cơm văn phòng')
        self.assertContains(response, 'Taxi sân bay')
        self.assertNotContains(response, 'Cơm tháng trước')

        response = self.client.get('/dashboard/', {
            'category': "\u0102n u\u1ed1ng",
            'search': 'văn phòng',
            'date_from': '2026-06-01',
            'date_to': '2026-06-30',
        })
        self.assertContains(response, 'Cơm văn phòng')
        self.assertNotContains(response, 'Taxi sân bay')
        self.assertNotContains(response, 'Cơm tháng trước')

    def test_smart_report_answers_detailed_category_question(self):
        Transaction.objects.create(user=self.user, amount=100000, category=self.food, note='Cơm văn phòng')
        Transaction.objects.create(user=self.user, amount=50000, category=self.food, note='Cafe')
        Transaction.objects.create(user=self.user, amount=30000, category=self.other, note='Khác')

        response = self.client.post('/smart-report/', {
            'question': 'Chi tiết ăn uống tháng này gồm những khoản nào?'
        })

        self.assertEqual(response.status_code, 200)
        result = response.context['result']
        self.assertIn("\u0102n u\u1ed1ng", result['answer'])
        labels = [row['label'] for row in result['rows']]
        self.assertIn('Cơm văn phòng', labels)
        self.assertIn('Cafe', labels)

    def test_smart_report_recognizes_all_ai_category_names(self):
        tech = Category.objects.create(name='Công nghệ')
        Transaction.objects.create(user=self.user, amount=15000000, category=tech, note='Laptop')
        Transaction.objects.create(user=self.user, amount=100000, category=self.food, note='Cơm')

        response = self.client.post('/smart-report/', {
            'question': 'Công nghệ chiếm bao nhiêu phần trăm tháng này?'
        })

        self.assertEqual(response.status_code, 200)
        result = response.context['result']
        self.assertIn('Công nghệ', result['answer'])
        self.assertIn('%', result['answer'])
        self.assertEqual(result['rows'][0]['label'], 'Công nghệ')

    def test_smart_report_answers_category_breakdown(self):
        Transaction.objects.create(user=self.user, amount=100000, category=self.food, note='Cơm')
        Transaction.objects.create(user=self.user, amount=30000, category=self.other, note='Khác')

        response = self.client.post('/smart-report/', {
            'question': 'Từng loại chi tiêu tháng này chi bao nhiêu?'
        })

        self.assertEqual(response.status_code, 200)
        labels = [row['label'] for row in response.context['result']['rows']]
        self.assertIn("\u0102n u\u1ed1ng", labels)
        self.assertIn('Khác', labels)

    def test_bill_and_recurring_forms_show_full_ai_category_choices(self):
        split_response = self.client.get('/split-bill/')
        recurring_response = self.client.get('/recurring/')

        self.assertEqual(split_response.status_code, 200)
        self.assertEqual(recurring_response.status_code, 200)
        for response in (split_response, recurring_response):
            self.assertContains(response, 'Công nghệ')
            self.assertContains(response, 'Đăng ký dịch vụ')
            self.assertContains(response, 'Bảo hiểm')

    def test_export_expenses_returns_valid_xlsx_file(self):
        Transaction.objects.create(user=self.user, amount=100000, category=self.food, note='Cơm văn phòng')

        response = self.client.get('/export/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('.xlsx', response['Content-Disposition'])

        with ZipFile(BytesIO(response.content)) as workbook:
            self.assertIn('[Content_Types].xml', workbook.namelist())
            self.assertIn('xl/worksheets/sheet1.xml', workbook.namelist())
            sheet_xml = workbook.read('xl/worksheets/sheet1.xml').decode('utf-8')

        self.assertIn('Ngày tạo', sheet_xml)
        self.assertIn("\u0102n u\u1ed1ng", sheet_xml)
        self.assertIn('Cơm văn phòng', sheet_xml)
        self.assertIn('100000', sheet_xml)

    def test_export_expenses_xlsx_uses_filters(self):
        transport = Category.objects.create(name='Di chuyển')
        Transaction.objects.create(user=self.user, amount=100000, category=self.food, note='Cơm văn phòng')
        Transaction.objects.create(user=self.user, amount=50000, category=transport, note='Taxi')

        response = self.client.get('/export/', {
            'category': "\u0102n u\u1ed1ng",
            'search': 'Cơm',
        })

        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(response.content)) as workbook:
            sheet_xml = workbook.read('xl/worksheets/sheet1.xml').decode('utf-8')

        self.assertIn('Cơm văn phòng', sheet_xml)
        self.assertNotIn('Taxi', sheet_xml)

    def test_edit_transaction_creates_learning_rule(self):
        transaction = Transaction.objects.create(
            user=self.user,
            amount=55000,
            category=self.other,
            note='Highlands',
            raw_text='Highlands 55k',
        )

        response = self.client.post(f'/edit/{transaction.id}/', {
            'amount': '55000',
            'category': "\u0102n u\u1ed1ng",
            'note': 'Highlands',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(CategoryRule.objects.filter(
            user=self.user,
            keyword='highlands',
            category=self.food,
        ).exists())

    def test_learned_rule_overrides_ai_category_for_text(self):
        CategoryRule.objects.create(user=self.user, keyword='highlands', category=self.food)

        with patch('expenses.views.ExpenseAI.analyze_text', return_value={
            'amount': 55000,
            'category': 'Kh\u00e1c',
            'note': 'Highlands',
        }):
            response = self.client.post('/add/', {
                'raw_text': 'Highlands 55k',
            })

        self.assertEqual(response.status_code, 302)
        transaction = Transaction.objects.get(user=self.user, note='Highlands')
        self.assertEqual(transaction.category, self.food)

    def test_split_bill_creates_participants(self):
        response = self.client.post('/split-bill/', {
            'title': 'Ăn tối',
            'total_amount': '300000',
            'people_count': '3',
            'participant_names': 'A, B, C',
            'payer_name': 'A',
            'category': "\u0102n u\u1ed1ng",
            'save_as_expense': 'on',
        })

        self.assertEqual(response.status_code, 200)
        bill = SplitBill.objects.get(user=self.user, title='Ăn tối')
        self.assertEqual(bill.participants.count(), 3)
        self.assertEqual(bill.participants.first().share_amount, Decimal('100000.00'))
        transaction = Transaction.objects.get(user=self.user, raw_text=f'split_bill:{bill.id}')
        self.assertEqual(transaction.amount, Decimal('100000.00'))
        self.assertEqual(transaction.category, self.food)

    def test_recurring_expense_generates_due_transaction(self):
        RecurringExpense.objects.create(
            user=self.user,
            title='Netflix',
            amount=260000,
            category=self.food,
            frequency=RecurringExpense.FREQUENCY_MONTHLY,
            next_due_date=date.today() - timedelta(days=1),
        )

        response = self.client.post('/recurring/', {
            'action': 'generate_due',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Transaction.objects.filter(user=self.user, note='Netflix').exists())
        recurring = RecurringExpense.objects.get(user=self.user, title='Netflix')
        self.assertGreater(recurring.next_due_date, date.today())

    def test_adding_due_recurring_expense_creates_transaction_immediately(self):
        response = self.client.post('/recurring/', {
            'title': 'Internet',
            'amount': '180000',
            'category': 'Sinh hoạt',
            'frequency': RecurringExpense.FREQUENCY_MONTHLY,
            'next_due_date': date.today().isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Transaction.objects.filter(user=self.user, note='Internet').exists())
        recurring = RecurringExpense.objects.get(user=self.user, title='Internet')
        self.assertGreater(recurring.next_due_date, date.today())
