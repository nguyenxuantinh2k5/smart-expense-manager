from django.db import models
from django.contrib.auth.models import User
from datetime import datetime
from decimal import Decimal

def current_year():
    return datetime.now().year

def current_month():
    return datetime.now().month

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.name

class Transaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    note = models.TextField(blank=True)
    # Thêm trường lưu ảnh hóa đơn
    image = models.ImageField(upload_to='static/uploads/', null=True, blank=True)
    raw_text = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"{self.note} - {self.amount}đ"
    class Meta:
        ordering = ['-created_at']

class Budget(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    year = models.IntegerField(default=current_year)
    month = models.IntegerField(default=current_month)  # 1-12
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-year', '-month']
        unique_together = ('user', 'year', 'month')
    
    def __str__(self):
        return f"{self.user.username} - {self.year}/{self.month:02d}: {self.amount}đ"
    
    def get_month_name(self):
        months = ['', 'Tháng 1', 'Tháng 2', 'Tháng 3', 'Tháng 4', 'Tháng 5', 'Tháng 6',
                  'Tháng 7', 'Tháng 8', 'Tháng 9', 'Tháng 10', 'Tháng 11', 'Tháng 12']
        return f"{months[self.month]} {self.year}" 

class CategoryRule(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    keyword = models.CharField(max_length=120)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    usage_count = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-usage_count', '-updated_at']
        unique_together = ('user', 'keyword')

    def __str__(self):
        return f"{self.keyword} -> {self.category.name}"

class SplitBill(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=150, default='Chia bill')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    people_count = models.PositiveIntegerField(default=2)
    payer_name = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def share_amount(self):
        if self.people_count <= 0:
            return Decimal('0')
        return self.total_amount / Decimal(self.people_count)

    def __str__(self):
        return f"{self.title} - {self.total_amount}"

class SplitParticipant(models.Model):
    bill = models.ForeignKey(SplitBill, on_delete=models.CASCADE, related_name='participants')
    name = models.CharField(max_length=100)
    share_amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid = models.BooleanField(default=False)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.name}: {self.share_amount}"

class RecurringExpense(models.Model):
    FREQUENCY_WEEKLY = 'weekly'
    FREQUENCY_MONTHLY = 'monthly'
    FREQUENCY_YEARLY = 'yearly'
    FREQUENCY_CHOICES = [
        (FREQUENCY_WEEKLY, 'Hang tuan'),
        (FREQUENCY_MONTHLY, 'Hang thang'),
        (FREQUENCY_YEARLY, 'Hang nam'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.TextField(blank=True)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default=FREQUENCY_MONTHLY)
    next_due_date = models.DateField()
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['next_due_date', 'title']

    def __str__(self):
        return f"{self.title} - {self.amount}"
