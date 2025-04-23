from django.urls import path, re_path, include
from rest_framework.routers import DefaultRouter
from .views import BookingViewSet, SyncView

app_name = "sync"

router = DefaultRouter()
router.register(r'bookings', BookingViewSet, basename='booking')

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/sync/<int:apartment_id>/', SyncView.as_view(), name='sync'),
    # match “.ics” literally; SyncView.format_suffixes handles the suffix
    re_path(
      r'^ical/availability/(?P<apartment_id>\d+)\.ics$',
      SyncView.as_view(),
      name='ics'
    ),
]
