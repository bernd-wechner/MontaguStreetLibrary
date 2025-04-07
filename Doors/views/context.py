from Doors.models import Event, Opening, Visit, DataFetch
from Doors.models.conf import VISIT_SEPARATION


def general_context(self, context={}):
    '''
    Used by all the views to add some basic context for the base template

    :param context: the context to augment (a dict)
    '''
    context['view_name'] = self.request.resolver_match.view_name
    context['menu_items'] = ['home', 'recent', 'trends', 'technical', 'nearby', 'build']

    first_event = Event.first().date_time
    last_event = Event.last().date_time
    last_fetch = DataFetch.objects.last()
    if last_fetch:
        last_fetch = last_fetch.date_time
    else:
        last_fetch = "unknown"

    context["data_stats"] = {
        'first_event': first_event,
        'last_event': last_event,
        'last_fetch': last_fetch,
        'time_span': last_event - first_event,
        'event_count': Event.histogram['doorcontact_state'],
        'open_count': Opening.objects.all().count(),
        'visit_count': Visit.objects.all().count(),
        'visit_separation': VISIT_SEPARATION
        }

    return context
