from django.shortcuts import render, redirect
from django.db.models import Sum
from .models import Transaction, Category
from .ai_services import ExpenseAI

def add_expense(request):
    if request.method == "POST":
        raw_text = request.POST.get('raw_text')
        ai = ExpenseAI()
        res = ai.analyze(raw_text)
        
        cat_obj, _ = Category.objects.get_or_create(name=res['category'])
        Transaction.objects.create(
            amount=res['amount'],
            category=cat_obj,
            note=res['note'],
            raw_text=raw_text
        )
        return redirect('dashboard')
    return render(request, 'expenses/add_expense.html')

from django.shortcuts import render
from django.db.models import Sum
from .models import Transaction

def dashboard(request):
    # 1. Tính tổng tiền (Sử dụng hàm Sum của Django)
    total_spent = Transaction.objects.aggregate(Sum('amount'))['amount__sum'] or 0
    
    # 2. Lấy 5 giao dịch gần đây nhất
    recent_transactions = Transaction.objects.all().order_by('-created_at')[:5]
    
    # 3. Đếm tổng số lần chi tiêu
    transaction_count = Transaction.objects.count()

    context = {
        'total_spent': total_spent,
        'recent_transactions': recent_transactions,
        'count': transaction_count,
    }
    return render(request, 'expenses/dashboard.html', context)

def report_chart(request):
    data = Transaction.objects.values('category__name').annotate(sum=Sum('amount'))
    labels = [d['category__name'] for d in data]
    values = [float(d['sum']) for d in data]
    return render(request, 'expenses/report_chart.html', {'labels': labels, 'values': values})