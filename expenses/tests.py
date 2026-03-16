from django.test import TestCase, Client
from django.contrib.auth.models import User
from .models import Category, Transaction
from .ai_services import ExpenseAI
import json

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