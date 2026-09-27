from sova.training.api.views.learner import LearnerViewSet
from sova.training.api.views.training_application import TrainingApplicationViewSet
from sova.training.api.views.training_application_learner import TrainingApplicationLearnerViewSet
from sova.training.api.views.training_instructor import TrainingInstructorViewSet
from sova.training.api.views.training_instructor_qualification import TrainingInstructorQualificationViewSet
from sova.training.api.views.training_stream import TrainingStreamViewSet

__all__ = [
    "LearnerViewSet",
    "TrainingApplicationLearnerViewSet",
    "TrainingApplicationViewSet",
    "TrainingInstructorQualificationViewSet",
    "TrainingInstructorViewSet",
    "TrainingStreamViewSet",
]
