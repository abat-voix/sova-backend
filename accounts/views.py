from django.middleware.csrf import get_token
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.models import UserRole


@extend_schema(
    responses={200: OpenApiResponse(description="Current authentication session")}
)
@api_view(["GET"])
@permission_classes([AllowAny])
def session(request):
    csrf_token = get_token(request)

    if not request.user.is_authenticated:
        return Response({"authenticated": False, "csrfToken": csrf_token})

    display_name = request.user.get_full_name() or request.user.email or "Пользователь"
    role_assignment = UserRole.objects.filter(user=request.user).first()
    role = role_assignment.role if role_assignment else None
    role_display = role_assignment.get_role_display() if role_assignment else None
    return Response(
        {
            "authenticated": True,
            "csrfToken": csrf_token,
            "user": {
                "id": request.user.pk,
                "email": request.user.email,
                "firstName": request.user.first_name,
                "lastName": request.user.last_name,
                "displayName": display_name,
                "isStaff": request.user.is_staff,
                "role": role,
                "roleDisplay": role_display,
                "roles": [role] if role else [],
            },
        }
    )
