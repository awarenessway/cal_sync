# project_root/urls.py

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # … any other apps …
    path('', include('sync.urls', namespace='sync')),
]
