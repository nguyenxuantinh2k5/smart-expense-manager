from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('expenses/', include('expenses.urls')), # App chính
    path('api/', include('api.urls')),           # App API cho Data
    path('', lambda r: redirect('expenses/add/')), # Tự động vào trang nhập liệu
]