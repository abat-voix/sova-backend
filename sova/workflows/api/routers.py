from rest_framework.routers import DefaultRouter

from sova.workflows.api import views

app_name = "workflows"

router = DefaultRouter()
router.register("workflows", views.WorkflowViewSet, basename="workflow")
router.register("workflow-stages", views.WorkflowStageViewSet, basename="workflow-stage")
router.register("workflow-actions", views.WorkflowActionViewSet, basename="workflow-action")
router.register("action-outcomes", views.ActionOutcomeViewSet, basename="action-outcome")
router.register(
    "action-transitions",
    views.ActionTransitionViewSet,
    basename="action-transition",
)
router.register(
    "action-dependencies",
    views.ActionDependencyViewSet,
    basename="action-dependency",
)
router.register(
    "stage-transitions",
    views.StageTransitionViewSet,
    basename="stage-transition",
)
router.register("workflow-changes", views.WorkflowChangeViewSet, basename="workflow-change")

urlpatterns = router.urls
