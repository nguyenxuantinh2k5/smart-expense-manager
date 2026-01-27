from rest_framework.views import APIView
from rest_framework.response import Response
from expenses.models import Transaction
from .serializers import TransactionSerializer
from rest_framework.permissions import IsAuthenticated

class TransactionListAPI(APIView):
    permission_classes = [IsAuthenticated] # Chỉ người dùng đã đăng nhập mới lấy được data

    def get(self, request):
        # Chỉ lấy chi tiêu của người đang đăng nhập
        transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
        serializer = TransactionSerializer(transactions, many=True)
        return Response(serializer.data)