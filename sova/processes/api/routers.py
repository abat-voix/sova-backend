from rest_framework.routers import DefaultRouter

from sova.processes.api import views

app_name = "processes"

router = DefaultRouter()
router.register(
    "workflow-instances",
    views.WorkflowInstanceViewSet,
    basename="workflow-instance",
)
router.register("stage-instances", views.StageInstanceViewSet, basename="stage-instance")
router.register("action-instances", views.ActionInstanceViewSet, basename="action-instance")
router.register("action-results", views.ActionResultViewSet, basename="action-result")
router.register(
    "action-attachments",
    views.ActionAttachmentViewSet,
    basename="action-attachment",
)

urlpatterns = router.urls
