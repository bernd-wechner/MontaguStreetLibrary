"""MontaguStreetLibrary URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from Doors.views.doors import HomePage, Recent, Trends, Technical
from Doors.views.generic import view_List, view_Detail
from Doors.views.ajax import ajax_List, ajax_Detail

urlpatterns = [
    path('', HomePage.as_view(), name='home'),
    path('recent/', Recent.as_view(), name='recent'),
    path('trends/', Trends.as_view(), name='trends'),
    path('technical/', Technical.as_view(), name='technical'),
    path('admin/', admin.site.urls, name='admin'),

    path('list/<model>', view_List.as_view(), name='list'),
    path('view/<model>/<pk>', view_Detail.as_view(), name='view'),

    path('json/<model>', ajax_List, name='get_list_html'),
    path('json/<model>/<pk>', ajax_Detail, name='get_detail_html'),
]
