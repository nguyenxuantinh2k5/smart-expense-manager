from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import json
import csv
from datetime import datetime, timedelta
from .models import Transaction, Category, Budget
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
        ai = ExpenseAI()
        image_file = request.FILES.get('image_file')
        raw_text = request.POST.get('raw_text')
        error_message = None

        try:
            if not image_file and not raw_text:
                error_message = "⚠️ Vui lòng nhập text hoặc chọn ảnh"
            
            elif image_file:
                # ✅ Validate image file
                max_size = 5 * 1024 * 1024  # 5MB
                if image_file.size > max_size:
                    error_message = f"❌ Ảnh quá lớn (max {max_size // (1024*1024)}MB)"
                elif not image_file.content_type.startswith('image/'):
                    error_message = "❌ File không phải ảnh"
                else:
                    # ✅ Process image
                    try:
                        temp_trans = Transaction.objects.create(
                            user=request.user, 
                            amount=0, 
                            image=image_file
                        )
                        
                        # ✅ Call AI service with error handling
                        res = ai.analyze_image(temp_trans.image.path)
                        
                        if not res:
                            error_message = "❌ Không thể phân tích ảnh"
                            temp_trans.delete()
                        else:
                            # ✅ Update transaction
                            cat_obj, _ = Category.objects.get_or_create(
                                name=res.get('category', 'Khác')
                            )
                            temp_trans.amount = res.get('amount', 0)
                            temp_trans.category = cat_obj
                            temp_trans.note = res.get('note', 'Chi tiêu từ ảnh')
                            temp_trans.save()
                            return redirect('dashboard')
                    
                    except Exception as ai_error:
                        error_message = f"❌ Lỗi xử lý ảnh: {str(ai_error)}"
                        if 'temp_trans' in locals():
                            temp_trans.delete()
            
            elif raw_text:
                # ✅ Process text
                try:
                    res = ai.analyze_text(raw_text)
                    
                    if not res:
                        error_message = "❌ Không thể phân tích text"
                    else:
                        amount_val = res.get('amount', 0)
                        category_name = res.get('category', 'Khác')
                        note_val = res.get('note', raw_text)

                        cat_obj, _ = Category.objects.get_or_create(name=category_name)
                        
                        Transaction.objects.create(
                            user=request.user,
                            amount=amount_val, 
                            category=cat_obj,
                            note=note_val,
                            raw_text=raw_text
                        )
                        return redirect('dashboard')
                
                except Exception as ai_error:
                    error_message = f"❌ Lỗi xử lý text: {str(ai_error)}"
        
        except Exception as e:
            error_message = f"❌ Lỗi hệ thống: {str(e)}"
        
        # ✅ If error, show it to user
        if error_message:
            return render(request, 'expenses/add_expense.html', {
                'error': error_message
            })
    
    return render(request, 'expenses/add_expense.html')

@login_required(login_url='login')
def edit_expense(request, transaction_id):
    try:
        transaction = Transaction.objects.get(id=transaction_id, user=request.user)
    except Transaction.DoesNotExist:
        return redirect('dashboard')
    
    if request.method == "POST":
        try:
            amount = float(request.POST.get('amount', transaction.amount))
            category_name = request.POST.get('category', transaction.category.name if transaction.category else 'Khác')
            note = request.POST.get('note', transaction.note)
            
            if amount < 0:
                return render(request, 'expenses/edit_expense.html', {
                    'transaction': transaction,
                    'categories': Category.objects.all(),
                    'error': '❌ Số tiền không được âm'
                })
            
            cat_obj, _ = Category.objects.get_or_create(name=category_name)
            transaction.amount = amount
            transaction.category = cat_obj
            transaction.note = note
            transaction.save()
            
            return redirect('dashboard')
        except ValueError:
            return render(request, 'expenses/edit_expense.html', {
                'transaction': transaction,
                'categories': Category.objects.all(),
                'error': '❌ Số tiền không hợp lệ'
            })
    
    return render(request, 'expenses/edit_expense.html', {
        'transaction': transaction,
        'categories': Category.objects.all()
    })

@login_required(login_url='login')
def delete_expense(request, transaction_id):
    try:
        transaction = Transaction.objects.get(id=transaction_id, user=request.user)
    except Transaction.DoesNotExist:
        return redirect('dashboard')
    
    if request.method == "POST":
        transaction.delete()
        return redirect('dashboard')
    
    return render(request, 'expenses/delete_expense.html', {
        'transaction': transaction
    })

@login_required(login_url='login')
def dashboard(request):
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
    
    # 🔍 Filter by category
    category_filter = request.GET.get('category')
    if category_filter and category_filter != '':
        transactions = transactions.filter(category__name=category_filter)
    
    # 🔍 Filter by date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        transactions = transactions.filter(created_at__gte=date_from)
    if date_to:
        transactions = transactions.filter(created_at__lte=date_to + ' 23:59:59')
    
    # 🔍 Search by note
    search_query = request.GET.get('search')
    if search_query:
        transactions = transactions.filter(note__icontains=search_query)
    
    # 💰 Calculate totals
    total = transactions.aggregate(Sum('amount'))['amount__sum'] or 0
    count = transactions.count()
    
    # 📂 Get categories for filter dropdown
    categories = Category.objects.all()
    
    # 📄 Pagination - 10 items per page
    paginator = Paginator(transactions, 10)
    page = request.GET.get('page', 1)
    
    try:
        transactions_page = paginator.page(page)
    except PageNotAnInteger:
        transactions_page = paginator.page(1)
    except EmptyPage:
        transactions_page = paginator.page(paginator.num_pages)
    
    # 💰 Get current month budget info
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    
    budget_info = {}
    try:
        current_budget = Budget.objects.get(user=request.user, year=current_year, month=current_month)
        month_start = datetime(current_year, current_month, 1)
        if current_month == 12:
            next_month = datetime(current_year + 1, 1, 1)
        else:
            next_month = datetime(current_year, current_month + 1, 1)
        
        month_spent = Transaction.objects.filter(
            user=request.user,
            created_at__gte=month_start,
            created_at__lt=next_month
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        budget_info = {
            'budget': current_budget,
            'spent': month_spent,
            'remaining': current_budget.amount - month_spent,
            'percentage': (month_spent / current_budget.amount * 100) if current_budget.amount > 0 else 0,
            'is_exceeded': month_spent > current_budget.amount
        }
    except Budget.DoesNotExist:
        budget_info = None
    
    return render(request, 'expenses/dashboard.html', {
        'transactions': transactions_page, 
        'total': total,
        'count': count,
        'categories': categories,
        'selected_category': category_filter,
        'search_query': search_query,
        'date_from': date_from,
        'date_to': date_to,
        'paginator': paginator,
        'page_obj': transactions_page,
        'budget_info': budget_info
    })

@login_required(login_url='login')
def report_chart(request):
    # Tổng hợp tiền theo từng danh mục
    data = Transaction.objects.filter(user=request.user).values('category__name').annotate(sum=Sum('amount'))
    
    # Chuẩn bị dữ liệu cho JavaScript
    labels = [d['category__name'] or "Chưa phân loại" for d in data]
    values = [float(d['sum']) for d in data]
    
    return render(request, 'expenses/report_chart.html', {
        'labels': json.dumps(labels), 
        'values': json.dumps(values)
    })

@login_required(login_url='login')
def export_expenses_csv(request):
    """✅ Export tất cả chi tiêu của user thành file CSV"""
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
    
    # Áp dụng filter nếu có
    category_filter = request.GET.get('category')
    if category_filter and category_filter != '':
        transactions = transactions.filter(category__name=category_filter)
    
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        transactions = transactions.filter(created_at__gte=date_from)
    if date_to:
        transactions = transactions.filter(created_at__lte=date_to + ' 23:59:59')
    
    search_query = request.GET.get('search')
    if search_query:
        transactions = transactions.filter(note__icontains=search_query)
    
    # Tạo CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="chi_tieu_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    writer = csv.writer(response, encoding='utf-8-sig')
    writer.writerow(['Ngày tạo', 'Danh mục', 'Ghi chú', 'Số tiền (VNĐ)'])
    
    for trans in transactions:
        writer.writerow([
            trans.created_at.strftime('%d/%m/%Y %H:%M'),
            trans.category.name if trans.category else 'Khác',
            trans.note,
            f'{trans.amount:.0f}'
        ])
    
    return response

@login_required(login_url='login')
def user_profile(request):
    """✅ Xem thông tin user profile"""
    return render(request, 'expenses/user_profile.html', {
        'user': request.user
    })

@login_required(login_url='login')
def edit_profile(request):
    """✅ Sửa thông tin user (username, email, first_name, last_name)"""
    if request.method == "POST":
        try:
            user = request.user
            new_email = request.POST.get('email', user.email)
            new_first_name = request.POST.get('first_name', user.first_name)
            new_last_name = request.POST.get('last_name', user.last_name)
            
            # Kiểm tra email đã tồn tại chưa (ngoại trừ user hiện tại)
            if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
                return render(request, 'expenses/edit_profile.html', {
                    'user': user,
                    'error': '❌ Email này đã được sử dụng'
                })
            
            user.email = new_email
            user.first_name = new_first_name
            user.last_name = new_last_name
            user.save()
            
            return render(request, 'expenses/edit_profile.html', {
                'user': user,
                'success': '✅ Cập nhật thông tin thành công'
            })
        except Exception as e:
            return render(request, 'expenses/edit_profile.html', {
                'user': request.user,
                'error': f'❌ Lỗi: {str(e)}'
            })
    
    return render(request, 'expenses/edit_profile.html', {
        'user': request.user
    })

@login_required(login_url='login')
def change_password(request):
    """✅ Đổi mật khẩu"""
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            return render(request, 'expenses/change_password.html', {
                'form': form,
                'success': '✅ Đổi mật khẩu thành công'
            })
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'expenses/change_password.html', {
        'form': form
    })

@login_required(login_url='login')
def set_budget(request):
    """✅ Đặt hoặc cập nhật budget cho tháng hiện tại"""
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    
    try:
        budget = Budget.objects.get(user=request.user, year=current_year, month=current_month)
    except Budget.DoesNotExist:
        budget = None
    
    if request.method == "POST":
        try:
            amount = float(request.POST.get('amount', 0))
            
            if amount < 0:
                return render(request, 'expenses/set_budget.html', {
                    'budget': budget,
                    'current_month': f"{current_month:02d}/{current_year}",
                    'error': '❌ Budget không được âm'
                })
            
            if budget:
                budget.amount = amount
                budget.save()
                message = '✅ Cập nhật budget thành công'
            else:
                Budget.objects.create(
                    user=request.user,
                    year=current_year,
                    month=current_month,
                    amount=amount
                )
                message = '✅ Đặt budget thành công'
            
            return render(request, 'expenses/set_budget.html', {
                'budget': Budget.objects.get(user=request.user, year=current_year, month=current_month),
                'current_month': f"{current_month:02d}/{current_year}",
                'success': message
            })
        except ValueError:
            return render(request, 'expenses/set_budget.html', {
                'budget': budget,
                'current_month': f"{current_month:02d}/{current_year}",
                'error': '❌ Số tiền không hợp lệ'
            })
    
    # Tính chi tiêu tháng này
    current_month_start = datetime(current_year, current_month, 1)
    if current_month == 12:
        next_month_start = datetime(current_year + 1, 1, 1)
    else:
        next_month_start = datetime(current_year, current_month + 1, 1)
    
    current_month_total = Transaction.objects.filter(
        user=request.user,
        created_at__gte=current_month_start,
        created_at__lt=next_month_start
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    return render(request, 'expenses/set_budget.html', {
        'budget': budget,
        'current_month': f"{current_month:02d}/{current_year}",
        'current_month_total': current_month_total,
        'remaining': (budget.amount - current_month_total) if budget else None
    })

@login_required(login_url='login')
def budget_history(request):
    """✅ Xem lịch sử budget tất cả tháng"""
    budgets = Budget.objects.filter(user=request.user).order_by('-year', '-month')
    
    # Tính chi tiêu cho mỗi budget
    budget_data = []
    for budget in budgets:
        month_start = datetime(budget.year, budget.month, 1)
        if budget.month == 12:
            next_month = datetime(budget.year + 1, 1, 1)
        else:
            next_month = datetime(budget.year, budget.month + 1, 1)
        
        spent = Transaction.objects.filter(
            user=request.user,
            created_at__gte=month_start,
            created_at__lt=next_month
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        remaining = budget.amount - spent
        percentage = (spent / budget.amount * 100) if budget.amount > 0 else 0
        is_exceeded = spent > budget.amount
        
        budget_data.append({
            'budget': budget,
            'spent': spent,
            'remaining': remaining,
            'percentage': min(percentage, 100),  # Cap at 100 for display
            'is_exceeded': is_exceeded
        })
    
    return render(request, 'expenses/budget_history.html', {
        'budget_data': budget_data
    })