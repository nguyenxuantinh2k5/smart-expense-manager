from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from .models import Transaction, Category
from .ai_services import ExpenseAI
from .forms import RegisterForm

def register_view(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = RegisterForm()
    return render(request, 'expenses/register.html', {'form': form})

def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'expenses/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required(login_url='login')
def add_expense(request):
    if request.method == "POST":
        raw_text = request.POST.get('raw_text')
        ai = ExpenseAI()
        res = ai.analyze(raw_text)
        
        cat_obj, _ = Category.objects.get_or_create(name=res['category'])
        Transaction.objects.create(
            user=request.user,
            amount=res['amount'],
            category=cat_obj,
            note=res['note'],
            raw_text=raw_text
        )
        return redirect('dashboard')
    return render(request, 'expenses/add_expense.html')

@login_required(login_url='login')
def dashboard(request):
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
    total = transactions.aggregate(Sum('amount'))['amount__sum'] or 0
    count = transactions.count()
    return render(request, 'expenses/dashboard.html', {
        'transactions': transactions, 
        'total': total,
        'count': count
    })

@login_required(login_url='login')
def report_chart(request):
    data = Transaction.objects.filter(user=request.user).values('category__name').annotate(sum=Sum('amount'))
    labels = [d['category__name'] for d in data]
    values = [float(d['sum']) for d in data]
    return render(request, 'expenses/report_chart.html', {'labels': labels, 'values': values})