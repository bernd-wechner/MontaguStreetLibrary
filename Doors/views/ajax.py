import json

from django.urls import reverse
from django.http.response import HttpResponse

from .generic import view_List, view_Detail


def ajax_List(request, model):
    '''
    Support AJAX rendering of lists of objects on the list view.

    To achieve this we instantiate a view_List and fetch its queryset then emit its html view.
    '''
    view = view_List()
    view.request = request
    view.kwargs = {'model':model}
    view.get_queryset()

    view_url = reverse("list", kwargs={"model":view.model.__name__})
    json_url = reverse("get_list_html", kwargs={"model":view.model.__name__})
    html = view.as_html()

    response = {'view_URL':view_url, 'json_URL':json_url, 'HTML':html}

    return HttpResponse(json.dumps(response))


def ajax_Detail(request, model, pk):
    '''
    Support AJAX rendering of objects on the detail view.

    To achieve this we instantiate a view_Detail and fetch the object then emit its html view.
    '''
    view = view_Detail()
    view.request = request
    view.kwargs = {'model':model, 'pk': pk}
    view.get_object()

    view_url = reverse("view", kwargs={"model":view.model.__name__, "pk": view.obj.pk})
    json_url = reverse("get_detail_html", kwargs={"model":view.model.__name__, "pk": view.obj.pk})
    html = view.as_html()

    response = {'view_URL':view_url, 'json_URL':json_url, 'HTML':html}

    # Add object browser details if available. Should be added by RichDetailView
    if hasattr(view, 'object_browser'):
        response['object_browser'] = view.object_browser

        if view.object_browser[0]:
            response['json_URL_prior'] = reverse("get_detail_html", kwargs={"model":view.model.__name__, "pk": view.object_browser[0]})
        else:
            response['json_URL_prior'] = response['json_URL']

        if view.object_browser[1]:
            response['json_URL_next'] = reverse("get_detail_html", kwargs={"model":view.model.__name__, "pk": view.object_browser[1]})
        else:
            response['json_URL_next'] = response['json_URL']

    return HttpResponse(json.dumps(response))
