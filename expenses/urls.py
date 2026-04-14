from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('add/', views.add_expense, name='add_expense'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('edit/<int:transaction_id>/', views.edit_expense, name='edit_expense'),
    path('delete/<int:transaction_id>/', views.delete_expense, name='delete_expense'),
    path('report/', views.report_chart, name='report_chart'),
    path('export/', views.export_expenses_csv, name='export_expenses'),
    path('profile/', views.user_profile, name='user_profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/change-password/', views.change_password, name='change_password'),
    path('budget/set/', views.set_budget, name='set_budget'),
    path('budget/history/', views.budget_history, name='budget_history'),
]