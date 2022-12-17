# from django.views.generic import TemplateView
from django_rich_views.views import RichTemplateView


class HomePage(RichTemplateView):
    template_name = "homepage.html"
