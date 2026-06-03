from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q, Sum
from django.http import HttpResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
import json
import calendar
import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile
from .models import (
    Budget,
    Category,
    CategoryRule,
    RecurringExpense,
    SplitBill,
    SplitParticipant,
    Transaction,
)
from .ai_services import CATEGORY_NAMES, CATEGORY_PATTERNS, ExpenseAI
from .forms import RegisterForm

RULE_STOP_WORDS = {
    'an', 'uong', 'mua', 'het', 'tien', 'chi', 'tra', 'voi', 'trong', 'hoa', 'don',
    'bill', 'sl', 'so', 'luong', 'gia', 'don', 'ngay', 'hom', 'nay', 'di', 'cho',
    'minh', 'ban', 'mot', 'hai', 'ba', 'bon', 'nam', 'sau', 'bay', 'tam', 'chin',
    'k', 'nghin', 'ngan', 'trieu', 'dong', 'vnd',
}

CATEGORY_QUERY_ALIASES = [
    ('Ăn uống', ['an uong', 'an', 'com', 'cafe', 'tra sua', 'nha hang']),
    ('Di chuyển', ['di chuyen', 'grab', 'taxi', 'xang', 'xe', 'bus']),
    ('Học tập', ['hoc tap', 'hoc phi', 'sach', 'khoa hoc']),
    ('Sinh hoạt', ['sinh hoat', 'tien dien', 'tien nuoc', 'internet', 'nha tro']),
    ('Mua sắm', ['mua sam', 'shopee', 'lazada', 'sieu thi']),
    ('Giải trí', ['giai tri', 'xem phim', 'game', 'karaoke']),
    ('Sức khỏe', ['suc khoe', 'thuoc', 'kham benh', 'benh vien']),
    ('Công nghệ', ['cong nghe', 'laptop', 'dien thoai', 'phan mem']),
]

CATEGORY_BREAKDOWN_TERMS = ('tung loai', 'tung danh muc', 'theo loai', 'theo danh muc', 'cac danh muc')
CATEGORY_DETAIL_TERMS = ('chi tiet', 'liet ke', 'giao dich', 'nhung khoan', 'cac khoan')
CATEGORY_BIGGEST_TERMS = ('lon nhat', 'cao nhat', 'dat nhat', 'nhieu nhat', 'ton nhieu', 'bat thuong')
CATEGORY_AVERAGE_TERMS = ('trung binh', 'binh quan')
CATEGORY_COUNT_TERMS = ('bao nhieu lan', 'so lan', 'may lan', 'bao nhieu giao dich')
CATEGORY_PERCENT_TERMS = ('ti le', 'ty le', 'phan tram', '%', 'chiem')


def _normalize_text_value(value):
    value = (value or '').lower().replace('đ', 'd')
    value = unicodedata.normalize('NFD', value)
    value = ''.join(ch for ch in value if unicodedata.category(ch) != 'Mn')
    return re.sub(r'\s+', ' ', value).strip()


def _parse_decimal(value):
    try:
        cleaned = str(value or '').replace(',', '').strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _format_money(value):
    value = Decimal(value or 0)
    return f"{value:,.0f}".replace(',', '.') + 'đ'


def _category_choices():
    db_names = Category.objects.values_list('name', flat=True).order_by('name')
    return list(dict.fromkeys([*CATEGORY_NAMES, *db_names]))


def _contains_any(normalized_query, terms):
    return any(term in normalized_query for term in terms)


def _extract_rule_keyword(text):
    normalized = _normalize_text_value(text)
    normalized = re.sub(r'\d+(?:[.,]\d+)?\s*(k|nghin|ngan|trieu|vnd|dong)?', ' ', normalized)
    tokens = [
        token for token in re.findall(r'[a-z0-9]+', normalized)
        if len(token) >= 2 and token not in RULE_STOP_WORDS
    ]
    return ' '.join(tokens[:3])[:120]


def _find_category_rule(user, text):
    normalized = _normalize_text_value(text)
    if not normalized:
        return None
    rules = CategoryRule.objects.filter(user=user).select_related('category')
    for rule in rules:
        if rule.keyword and rule.keyword in normalized:
            return rule.category
    return None


def _apply_learned_category(user, text, category_name):
    learned_category = _find_category_rule(user, text)
    return learned_category.name if learned_category else category_name


def _remember_category_rule(user, text, category):
    keyword = _extract_rule_keyword(text)
    if not keyword or not category:
        return None

    rule, created = CategoryRule.objects.get_or_create(
        user=user,
        keyword=keyword,
        defaults={'category': category},
    )
    if not created:
        rule.category = category
        rule.usage_count += 1
        rule.save(update_fields=['category', 'usage_count', 'updated_at'])
    return rule


def _month_bounds(year, month):
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return timezone.make_aware(start), timezone.make_aware(end)


def _parse_filter_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _start_of_day(value):
    return timezone.make_aware(datetime.combine(value, datetime.min.time()))


def _parse_search_amount(value):
    digits = re.sub(r'\D', '', value or '')
    return Decimal(digits) if digits else None


def _filter_transaction_queryset(transactions, params):
    category_filter = (params.get('category') or '').strip()
    date_from_raw = (params.get('date_from') or '').strip()
    date_to_raw = (params.get('date_to') or '').strip()
    search_query = (params.get('search') or '').strip()

    if category_filter:
        transactions = transactions.filter(category__name=category_filter)

    date_from = _parse_filter_date(date_from_raw)
    if date_from:
        transactions = transactions.filter(created_at__gte=_start_of_day(date_from))

    date_to = _parse_filter_date(date_to_raw)
    if date_to:
        transactions = transactions.filter(created_at__lt=_start_of_day(date_to + timedelta(days=1)))

    if search_query:
        search_filter = (
            Q(note__icontains=search_query) |
            Q(raw_text__icontains=search_query) |
            Q(category__name__icontains=search_query)
        )
        search_amount = _parse_search_amount(search_query)
        if search_amount is not None:
            search_filter |= Q(amount=search_amount)
        transactions = transactions.filter(search_filter)

    return transactions, {
        'category': category_filter,
        'date_from': date_from_raw,
        'date_to': date_to_raw,
        'search': search_query,
    }


def _query_period(user, normalized_query):
    now = timezone.localtime(timezone.now())
    if 'tuan' in normalized_query:
        start = now - timedelta(days=now.weekday())
        start = timezone.make_aware(datetime(start.year, start.month, start.day))
        return Transaction.objects.filter(user=user, created_at__gte=start), 'tuần này'
    if 'thang truoc' in normalized_query:
        year = now.year if now.month > 1 else now.year - 1
        month = now.month - 1 if now.month > 1 else 12
        start, end = _month_bounds(year, month)
        return Transaction.objects.filter(user=user, created_at__gte=start, created_at__lt=end), 'tháng trước'
    if 'hom nay' in normalized_query:
        start = timezone.make_aware(datetime(now.year, now.month, now.day))
        return Transaction.objects.filter(user=user, created_at__gte=start), 'hôm nay'
    start, end = _month_bounds(now.year, now.month)
    return Transaction.objects.filter(user=user, created_at__gte=start, created_at__lt=end), 'tháng này'


def _category_from_query(normalized_query):
    for category_name in _category_choices():
        normalized_name = _normalize_text_value(category_name)
        if normalized_name and re.search(rf'\b{re.escape(normalized_name)}\b', normalized_query):
            return category_name

    for category_name, aliases in CATEGORY_QUERY_ALIASES:
        if any(alias in normalized_query for alias in aliases):
            return category_name

    for category_name, patterns in CATEGORY_PATTERNS:
        if any(re.search(pattern, normalized_query) for pattern in patterns):
            return category_name
    return None


def _format_percent(amount, total):
    if not total:
        return '0.0%'
    percent = (Decimal(amount or 0) / Decimal(total)) * Decimal('100')
    return f'{percent:.1f}%'


def _category_breakdown_rows(transactions, total):
    grouped = transactions.values('category__name').annotate(
        total=Sum('amount'),
        count=Count('id'),
    ).order_by('-total')
    return [
        {
            'label': row['category__name'] or 'Chưa phân loại',
            'value': _format_money(row['total']),
            'detail': f'{row["count"]} giao dịch - {_format_percent(row["total"], total)} tổng chi',
        }
        for row in grouped
    ]


def _transaction_rows(transactions, limit=8):
    rows = []
    for item in transactions[:limit]:
        category_name = item.category.name if item.category else 'Chưa phân loại'
        created_date = timezone.localtime(item.created_at).strftime('%d/%m/%Y')
        rows.append({
            'label': item.note or 'Không ghi chú',
            'value': _format_money(item.amount),
            'detail': f'{category_name} - {created_date}',
        })
    return rows


def _answer_category_report(category_name, transactions, total, period_label, normalized_query):
    category_transactions = transactions.filter(category__name=category_name)
    category_total = category_transactions.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    category_count = category_transactions.count()

    if category_count == 0:
        return {
            'answer': f'Chưa có giao dịch thuộc {category_name} trong {period_label}.',
            'rows': [{'label': category_name, 'value': _format_money(0)}],
        }

    percent = _format_percent(category_total, total)
    avg_amount = category_transactions.aggregate(avg=Avg('amount'))['avg'] or Decimal('0')
    biggest = category_transactions.order_by('-amount').first()

    if _contains_any(normalized_query, CATEGORY_PERCENT_TERMS):
        return {
            'answer': f'{category_name} chiếm {percent} tổng chi trong {period_label}.',
            'rows': [{
                'label': category_name,
                'value': _format_money(category_total),
                'detail': f'{category_count} giao dịch trên tổng {_format_money(total)}',
            }],
        }

    if _contains_any(normalized_query, CATEGORY_AVERAGE_TERMS):
        return {
            'answer': f'Mức chi trung bình cho {category_name} trong {period_label} là {_format_money(avg_amount)}.',
            'rows': [{
                'label': category_name,
                'value': _format_money(avg_amount),
                'detail': f'{category_count} giao dịch, tổng {_format_money(category_total)}',
            }],
        }

    if _contains_any(normalized_query, CATEGORY_COUNT_TERMS):
        return {
            'answer': f'{category_name} trong {period_label} có {category_count} giao dịch.',
            'rows': [{
                'label': category_name,
                'value': f'{category_count} giao dịch',
                'detail': f'Tổng {_format_money(category_total)} - {percent} tổng chi',
            }],
        }

    if _contains_any(normalized_query, CATEGORY_BIGGEST_TERMS):
        return {
            'answer': f'Các khoản {category_name} lớn nhất trong {period_label}.',
            'rows': _transaction_rows(category_transactions.order_by('-amount'), limit=5),
        }

    if _contains_any(normalized_query, CATEGORY_DETAIL_TERMS):
        return {
            'answer': f'Chi tiết {category_name} trong {period_label}: {_format_money(category_total)} với {category_count} giao dịch.',
            'rows': _transaction_rows(category_transactions.order_by('-created_at'), limit=10),
        }

    biggest_text = f' Khoản lớn nhất là {biggest.note or "Không ghi chú"}: {_format_money(biggest.amount)}.' if biggest else ''
    return {
        'answer': (
            f'{category_name} trong {period_label}: {_format_money(category_total)} '
            f'với {category_count} giao dịch, chiếm {percent} tổng chi.{biggest_text}'
        ),
        'rows': [{
            'label': category_name,
            'value': _format_money(category_total),
            'detail': f'Trung bình {_format_money(avg_amount)} / giao dịch',
        }],
    }


def _answer_report_question(user, question):
    normalized = _normalize_text_value(question)
    transactions, period_label = _query_period(user, normalized)
    total = transactions.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    count = transactions.count()

    if count == 0:
        return {
            'answer': f'Chưa có giao dịch nào trong {period_label}.',
            'rows': [],
        }

    if 'so voi' in normalized and 'thang truoc' in normalized:
        now = timezone.localtime(timezone.now())
        current_start, current_end = _month_bounds(now.year, now.month)
        prev_year = now.year if now.month > 1 else now.year - 1
        prev_month = now.month - 1 if now.month > 1 else 12
        prev_start, prev_end = _month_bounds(prev_year, prev_month)
        current_total = Transaction.objects.filter(
            user=user, created_at__gte=current_start, created_at__lt=current_end
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        previous_total = Transaction.objects.filter(
            user=user, created_at__gte=prev_start, created_at__lt=prev_end
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        diff = current_total - previous_total
        direction = 'nhiều hơn' if diff > 0 else 'ít hơn'
        return {
            'answer': f'Tháng này bạn chi {_format_money(current_total)}, {direction} {_format_money(abs(diff))} so với tháng trước.',
            'rows': [
                {'label': 'Tháng này', 'value': _format_money(current_total)},
                {'label': 'Tháng trước', 'value': _format_money(previous_total)},
            ],
        }

    if _contains_any(normalized, CATEGORY_BREAKDOWN_TERMS):
        return {
            'answer': f'Chi theo từng danh mục trong {period_label}: {_format_money(total)} với {count} giao dịch.',
            'rows': _category_breakdown_rows(transactions, total),
        }

    category_name = _category_from_query(normalized)
    if category_name:
        return _answer_category_report(category_name, transactions, total, period_label, normalized)

    if 'bat thuong' in normalized or 'cao bat thuong' in normalized:
        avg_amount = transactions.aggregate(avg=Avg('amount'))['avg'] or Decimal('0')
        unusual = transactions.filter(amount__gte=avg_amount * Decimal('2')).order_by('-amount')[:5]
        if not unusual:
            unusual = transactions.order_by('-amount')[:5]
        return {
            'answer': f'Mức chi trung bình trong {period_label} là {_format_money(avg_amount)}. Đây là các khoản lớn nhất cần xem lại.',
            'rows': _transaction_rows(unusual, limit=5),
        }

    if 'nhieu nhat' in normalized or 'ton nhieu' in normalized or 'tốn nhiều' in question:
        top = _category_breakdown_rows(transactions, total)[:5]
        first = top[0] if top else None
        answer = (
            f'Bạn tốn nhiều nhất cho {first["label"]}: {first["value"]}.'
            if first else f'Tổng chi trong {period_label}: {_format_money(total)}.'
        )
        return {
            'answer': answer,
            'rows': top,
        }

    return {
        'answer': f'Tổng chi {period_label}: {_format_money(total)} với {count} giao dịch.',
        'rows': _category_breakdown_rows(transactions, total)[:5],
    }


def _advance_due_date(due_date, frequency):
    if frequency == RecurringExpense.FREQUENCY_WEEKLY:
        return due_date + timedelta(days=7)
    if frequency == RecurringExpense.FREQUENCY_YEARLY:
        try:
            return due_date.replace(year=due_date.year + 1)
        except ValueError:
            return due_date.replace(year=due_date.year + 1, day=28)

    next_month = due_date.month + 1
    next_year = due_date.year
    if next_month > 12:
        next_month = 1
        next_year += 1
    last_day = calendar.monthrange(next_year, next_month)[1]
    return due_date.replace(year=next_year, month=next_month, day=min(due_date.day, last_day))


def _generate_due_recurring_expenses(user):
    today = date.today()
    generated = 0
    recurring_items = RecurringExpense.objects.filter(user=user, active=True, next_due_date__lte=today)
    for item in recurring_items:
        generated += _generate_transactions_for_recurring_item(item, today)
    return generated


def _generate_transactions_for_recurring_item(item, today=None):
    today = today or date.today()
    generated = 0
    guard = 0
    while item.next_due_date <= today and guard < 24:
        Transaction.objects.create(
            user=item.user,
            amount=item.amount,
            category=item.category,
            note=item.note or item.title,
            raw_text=f"recurring:{item.id}:{item.next_due_date.isoformat()}",
        )
        item.next_due_date = _advance_due_date(item.next_due_date, item.frequency)
        generated += 1
        guard += 1
    if generated:
        item.save(update_fields=['next_due_date', 'updated_at'])
    return generated

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
        image_item_name = request.POST.get('image_item_name', '').strip()
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
                        if image_item_name:
                            res = ai.analyze_image_item(temp_trans.image.path, image_item_name)
                        else:
                            res = ai.analyze_image(temp_trans.image.path)
                        
                        if not res or float(res.get('amount') or 0) <= 0:
                            error_message = res.get('note', "Không thể phân tích ảnh") if res else "Không thể phân tích ảnh"
                            temp_trans.delete()
                        else:
                            # ✅ Update transaction
                            category_name = _apply_learned_category(
                                request.user,
                                f"{image_item_name} {res.get('note', '')}",
                                res.get('category', 'Khác'),
                            )
                            cat_obj, _ = Category.objects.get_or_create(
                                name=category_name
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
                        category_name = _apply_learned_category(request.user, raw_text or note_val, category_name)

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
    old_category_id = transaction.category_id
    
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
            if old_category_id != cat_obj.id:
                _remember_category_rule(request.user, transaction.raw_text or note, cat_obj)
            
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
    transactions = Transaction.objects.filter(user=request.user).select_related('category').order_by('-created_at')
    transactions, filter_state = _filter_transaction_queryset(transactions, request.GET)
    
    # 💰 Calculate totals
    total = transactions.aggregate(Sum('amount'))['amount__sum'] or 0
    count = transactions.count()
    average = (total / count) if count else 0
    
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
        month_start, next_month = _month_bounds(current_year, current_month)
        
        month_spent = Transaction.objects.filter(
            user=request.user,
            created_at__gte=month_start,
            created_at__lt=next_month
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        percentage = (month_spent / current_budget.amount * 100) if current_budget.amount > 0 else 0
        budget_info = {
            'budget': current_budget,
            'spent': month_spent,
            'remaining': current_budget.amount - month_spent,
            'percentage': percentage,
            'percentage_width': f'{min(float(percentage), 100):.2f}',
            'is_exceeded': month_spent > current_budget.amount
        }
    except Budget.DoesNotExist:
        budget_info = None
    
    return render(request, 'expenses/dashboard.html', {
        'transactions': transactions_page, 
        'total': total,
        'count': count,
        'average': average,
        'categories': categories,
        'selected_category': filter_state['category'],
        'search_query': filter_state['search'],
        'date_from': filter_state['date_from'],
        'date_to': filter_state['date_to'],
        'paginator': paginator,
        'page_obj': transactions_page,
        'budget_info': budget_info,
        'export_query': request.GET.urlencode(),
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
def smart_report(request):
    question = request.POST.get('question', '').strip() if request.method == "POST" else ''
    result = _answer_report_question(request.user, question) if question else None
    examples = [
        'Tháng này tôi tốn nhiều nhất vào đâu?',
        'Chi tiết ăn uống tháng này gồm những khoản nào?',
        'Từng loại chi tiêu tháng này chi bao nhiêu?',
        'Công nghệ chiếm bao nhiêu phần trăm tháng này?',
        'Đăng ký dịch vụ tháng này khoản nào lớn nhất?',
        'So với tháng trước tôi chi nhiều hơn hay ít hơn?',
        'Khoản nào bất thường tháng này?',
    ]
    return render(request, 'expenses/smart_report.html', {
        'question': question,
        'result': result,
        'examples': examples,
    })

@login_required(login_url='login')
def split_bill(request):
    error = None
    result_bill = None

    if request.method == "POST":
        total_amount = _parse_decimal(request.POST.get('total_amount'))
        title = request.POST.get('title', 'Chia bill').strip() or 'Chia bill'
        payer_name = request.POST.get('payer_name', '').strip()
        note = request.POST.get('note', '').strip()
        names_raw = request.POST.get('participant_names', '').strip()
        category_name = request.POST.get('category', '').strip() or 'Khác'
        save_as_expense = request.POST.get('save_as_expense') == 'on'

        try:
            people_count = int(request.POST.get('people_count', 2))
        except ValueError:
            people_count = 0

        if not total_amount or total_amount <= 0:
            error = 'Vui lòng nhập tổng tiền hợp lệ.'
        elif people_count <= 0:
            error = 'Số người chia bill phải lớn hơn 0.'
        else:
            names = [
                name.strip()
                for name in re.split(r'[\n,]+', names_raw)
                if name.strip()
            ]
            if not names:
                names = [f'Người {index}' for index in range(1, people_count + 1)]
            if len(names) != people_count:
                people_count = len(names)

            result_bill = SplitBill.objects.create(
                user=request.user,
                title=title,
                total_amount=total_amount,
                people_count=people_count,
                payer_name=payer_name,
                note=note,
            )
            share = (total_amount / Decimal(people_count)).quantize(Decimal('0.01'))
            for name in names:
                SplitParticipant.objects.create(
                    bill=result_bill,
                    name=name,
                    share_amount=share,
                )
            if save_as_expense:
                category, _ = Category.objects.get_or_create(name=category_name)
                Transaction.objects.create(
                    user=request.user,
                    amount=share,
                    category=category,
                    note=f"{title} - phần của tôi ({people_count} người)",
                    raw_text=f"split_bill:{result_bill.id}",
                )

    recent_bills = SplitBill.objects.filter(user=request.user).prefetch_related('participants')[:10]
    category_choices = _category_choices()
    return render(request, 'expenses/split_bill.html', {
        'error': error,
        'result_bill': result_bill,
        'recent_bills': recent_bills,
        'category_choices': category_choices,
    })

@login_required(login_url='login')
def recurring_expenses(request):
    error = None
    success = None

    if request.method == "POST":
        action = request.POST.get('action')
        if action == 'generate_due':
            generated = _generate_due_recurring_expenses(request.user)
            success = f'Đã tạo {generated} giao dịch định kỳ đến hạn.'
        else:
            title = request.POST.get('title', '').strip()
            amount = _parse_decimal(request.POST.get('amount'))
            category_name = request.POST.get('category', '').strip()
            note = request.POST.get('note', '').strip()
            frequency = request.POST.get('frequency', RecurringExpense.FREQUENCY_MONTHLY)
            next_due_raw = request.POST.get('next_due_date', '').strip()

            if not title:
                error = 'Vui lòng nhập tên khoản định kỳ.'
            elif not amount or amount <= 0:
                error = 'Vui lòng nhập số tiền hợp lệ.'
            elif frequency not in dict(RecurringExpense.FREQUENCY_CHOICES):
                error = 'Chu kỳ không hợp lệ.'
            else:
                try:
                    next_due_date = datetime.strptime(next_due_raw, '%Y-%m-%d').date()
                except ValueError:
                    next_due_date = date.today()

                category = None
                if category_name:
                    category, _ = Category.objects.get_or_create(name=category_name)

                recurring_item = RecurringExpense.objects.create(
                    user=request.user,
                    title=title,
                    amount=amount,
                    category=category,
                    note=note,
                    frequency=frequency,
                    next_due_date=next_due_date,
                )
                generated = _generate_transactions_for_recurring_item(recurring_item)
                if generated:
                    success = f'Đã thêm khoản chi định kỳ và tạo {generated} giao dịch đến hạn.'
                else:
                    success = 'Đã thêm khoản chi định kỳ. Giao dịch sẽ được tạo khi đến hạn.'

    recurring_items = RecurringExpense.objects.filter(user=request.user).select_related('category')
    category_choices = _category_choices()
    return render(request, 'expenses/recurring_expenses.html', {
        'error': error,
        'success': success,
        'recurring_items': recurring_items,
        'category_choices': category_choices,
        'today': date.today().isoformat(),
        'frequency_choices': RecurringExpense.FREQUENCY_CHOICES,
    })

EXCEL_MIME_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _excel_column_name(index):
    name = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _clean_excel_text(value):
    text = str(value or '')
    return ''.join(
        char for char in text
        if char in {'\t', '\n', '\r'} or ord(char) >= 32
    )


def _xlsx_inline_cell(row_index, column_index, value, style_id=None):
    cell_ref = f'{_excel_column_name(column_index)}{row_index}'
    style_attr = f' s="{style_id}"' if style_id is not None else ''
    value = escape(_clean_excel_text(value))
    return f'<c r="{cell_ref}" t="inlineStr"{style_attr}><is><t xml:space="preserve">{value}</t></is></c>'


def _xlsx_number_cell(row_index, column_index, value, style_id=None):
    cell_ref = f'{_excel_column_name(column_index)}{row_index}'
    style_attr = f' s="{style_id}"' if style_id is not None else ''
    number = Decimal(value or 0)
    return f'<c r="{cell_ref}" t="n"{style_attr}><v>{number:f}</v></c>'


def _build_expense_sheet_xml(rows):
    xml_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            if row_index > 1 and column_index == 4:
                cells.append(_xlsx_number_cell(row_index, column_index, value, style_id=2))
            else:
                cells.append(_xlsx_inline_cell(row_index, column_index, value, style_id=1 if row_index == 1 else None))
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
    <cols>
        <col min="1" max="1" width="20" customWidth="1"/>
        <col min="2" max="2" width="18" customWidth="1"/>
        <col min="3" max="3" width="45" customWidth="1"/>
        <col min="4" max="4" width="18" customWidth="1"/>
    </cols>
    <sheetData>
        {''.join(xml_rows)}
    </sheetData>
</worksheet>'''


def _build_expenses_xlsx(rows):
    workbook_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
    <sheets>
        <sheet name="Chi tiêu" sheetId="1" r:id="rId1"/>
    </sheets>
</workbook>'''
    workbook_rels_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''
    root_rels_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''
    content_types_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
    <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
    <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''
    styles_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
    <numFmts count="1">
        <numFmt numFmtId="164" formatCode="#,##0"/>
    </numFmts>
    <fonts count="2">
        <font><sz val="11"/><name val="Calibri"/></font>
        <font><b/><sz val="11"/><name val="Calibri"/></font>
    </fonts>
    <fills count="2">
        <fill><patternFill patternType="none"/></fill>
        <fill><patternFill patternType="gray125"/></fill>
    </fills>
    <borders count="1"><border/></borders>
    <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
    <cellXfs count="3">
        <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
        <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
        <xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
    </cellXfs>
    <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''

    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', content_types_xml)
        archive.writestr('_rels/.rels', root_rels_xml)
        archive.writestr('xl/workbook.xml', workbook_xml)
        archive.writestr('xl/_rels/workbook.xml.rels', workbook_rels_xml)
        archive.writestr('xl/styles.xml', styles_xml)
        archive.writestr('xl/worksheets/sheet1.xml', _build_expense_sheet_xml(rows))
    return output.getvalue()


def _filtered_export_transactions(request):
    transactions = Transaction.objects.filter(user=request.user).select_related('category').order_by('-created_at')
    transactions, _filter_state = _filter_transaction_queryset(transactions, request.GET)
    return transactions


@login_required(login_url='login')
def export_expenses_xlsx(request):
    """Export chi tiêu của user thành file Excel XLSX."""
    rows = [['Ngày tạo', 'Danh mục', 'Ghi chú', 'Số tiền (VNĐ)']]

    for transaction in _filtered_export_transactions(request):
        rows.append([
            timezone.localtime(transaction.created_at).strftime('%d/%m/%Y %H:%M'),
            transaction.category.name if transaction.category else 'Khác',
            transaction.note,
            transaction.amount,
        ])

    timestamp = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')
    response = HttpResponse(
        _build_expenses_xlsx(rows),
        content_type=EXCEL_MIME_TYPE,
    )
    response['Content-Disposition'] = f'attachment; filename="chi_tieu_{timestamp}.xlsx"'
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
    current_month_start, next_month_start = _month_bounds(current_year, current_month)
    
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
        month_start, next_month = _month_bounds(budget.year, budget.month)
        
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
            'percentage_width': f'{min(float(percentage), 100):.2f}',
            'is_exceeded': is_exceeded
        })
    
    return render(request, 'expenses/budget_history.html', {
        'budget_data': budget_data
    })
