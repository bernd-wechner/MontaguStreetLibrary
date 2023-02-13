from django_rich_views.views import RichListView, RichDetailView
from django_rich_views.options import list_display_format, object_display_format


class view_List(RichListView):
    template_name = 'list.html'
    format = list_display_format()


class view_Detail(RichDetailView):
    template_name = 'detail.html'
    format = object_display_format()
