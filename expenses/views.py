from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
import json
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
    # Tổng hợp tiền theo từng danh mục
    data = Transaction.objects.filter(user=request.user).values('category__name').annotate(sum=Sum('amount'))
    
    # Chuẩn bị dữ liệu cho JavaScript
    labels = [d['category__name'] or "Chưa phân loại" for d in data]
    values = [float(d['sum']) for d in data]
    
    return render(request, 'expenses/report_chart.html', {
        'labels': json.dumps(labels), 
        'values': json.dumps(values)
    })