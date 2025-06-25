from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from users.views import dashboard_view
from users.views import SignUpView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('analyzer.urls')),  
    path('users/', include('users.urls')), 
    path('dashboard/', dashboard_view, name='dashboard'),
     path("", SignUpView.as_view(), name="home"),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


