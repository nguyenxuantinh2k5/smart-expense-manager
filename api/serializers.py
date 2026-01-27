from rest_framework import serializers
from expenses.models import Transaction, Category

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name']

class TransactionSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source='category.name')

    class Meta:
        model = Transaction
        fields = ['id', 'amount', 'category', 'category_name', 'note', 'image', 'created_at']