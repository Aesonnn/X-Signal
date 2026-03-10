from django.contrib import admin
from django.urls import include, path


handler403 = "xsignal_django.views.handler403"
handler404 = "xsignal_django.views.handler404"


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("dashboard.urls")),
]
