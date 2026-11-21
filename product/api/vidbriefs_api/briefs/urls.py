from django.urls import path

from .views import AskView, VideoView

urlpatterns = [
    path('videos/', VideoView.as_view(), name='videos'),
    path('videos/<str:youtube_id>/ask/', AskView.as_view(), name='ask'), # path to pass url 
]