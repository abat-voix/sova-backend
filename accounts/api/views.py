from django.db.models import QuerySet

from accounts.api.permissions import CanListUsers
from accounts.api.serializers import UserSerializer
from accounts.services import visible_users
from sova.core.api.views import SovaReadOnlyViewSet


class UserViewSet(SovaReadOnlyViewSet):
    """
    Пользователи системы — только чтение.

    Состав списка зависит от роли запрашивающего: руководитель видит КАМов,
    администратор платформы — всех пользователей, кроме администраторов
    платформы. Остальным ролям эндпоинт недоступен.
    """

    read_serializer_class = UserSerializer
    serializer_class = UserSerializer
    permission_classes = (CanListUsers,)
    ordering_fields = ("last_name", "first_name", "email")
    search_fields = ("first_name", "last_name", "email", "username")

    def get_queryset(self) -> QuerySet:
        """Пользователи, видимые текущему пользователю согласно его роли."""
        return (
            visible_users(self.request.user)
            .select_related("system_role")
            .order_by("last_name", "first_name", "pk")
        )
