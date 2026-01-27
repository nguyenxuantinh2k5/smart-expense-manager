from django.urls import path
from .views import TransactionListAPI

urlpatterns = [
    path('transactions/', TransactionListAPI.as_view(), name='api_transactions'),
]