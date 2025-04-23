from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BookingViewSet, SyncView

router = DefaultRouter()
router.register(r'bookings', BookingViewSet, basename='booking')

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/sync/<int:apartment_id>/', SyncView.as_view(), name='sync'),
    path('ical/availability/<int:apartment_id>.ics', SyncView.as_view(format_suffixes=['ics']), name='ics'),
]

