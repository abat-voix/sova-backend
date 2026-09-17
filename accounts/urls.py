from django.urls import path

from accounts.views import session


app_name = "accounts"

urlpatterns = [
    path("me/", session, name="session"),
]
