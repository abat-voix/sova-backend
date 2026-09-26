from rest_framework.routers import DefaultRouter

from sova.messaging.api import views

app_name = "messaging"

router = DefaultRouter()
router.register("attachments", views.MessageAttachmentViewSet, basename="message-attachment")
router.register("conversations", views.ConversationViewSet, basename="conversation")

urlpatterns = router.urls
