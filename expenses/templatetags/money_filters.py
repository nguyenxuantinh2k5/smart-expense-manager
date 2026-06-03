from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template


register = template.Library()


def _to_decimal(value):
    if value in (None, ''):
        return Decimal('0')
    if isinstance(value, str):
        value = value.replace('.', '').replace(',', '').strip()
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None


def _format_grouped(value):
    amount = _to_decimal(value)
    if amount is None:
        return value

    rounded = amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    sign = '-' if rounded < 0 else ''
    return f'{sign}{abs(int(rounded)):,}'.replace(',', '.')


@register.filter
def group_number(value):
    return _format_grouped(value)


@register.filter
def vnd(value):
    return f'{_format_grouped(value)}đ'


@register.filter
def vnd_abs(value):
    amount = _to_decimal(value)
    if amount is None:
        return value
    return f'{_format_grouped(abs(amount))}đ'
