from rest_framework.routers import DefaultRouter

from sova.training.api import views

app_name = "training"

router = DefaultRouter()
router.register("streams", views.TrainingStreamViewSet, basename="stream")
router.register("applications", views.TrainingApplicationViewSet, basename="application")
router.register(
    "application-learners",
    views.TrainingApplicationLearnerViewSet,
    basename="application-learner",
)
router.register("learners", views.LearnerViewSet, basename="learner")
router.register("instructors", views.TrainingInstructorViewSet, basename="instructor")
router.register(
    "instructor-qualifications",
    views.TrainingInstructorQualificationViewSet,
    basename="instructor-qualification",
)

urlpatterns = router.urls
