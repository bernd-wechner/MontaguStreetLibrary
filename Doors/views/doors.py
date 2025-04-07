# from django.views.generic import TemplateView
import math, re, numpy as np

from datetime import timedelta

from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models import FixedTicker, BasicTicker, SingleIntervalTicker, CategoricalTicker, Range1d, CategoricalTickFormatter, CustomJS
from bokeh.resources import Resources

from django.db.models import Count, Min, Max, Avg

from django_rich_views.views import RichTemplateView
from django_rich_views.css import get_css_custom_properties, parse_color

from Doors.models import Door, Visit, Event, Opening, Uptime

from .context import general_context

from Site.logutils import log

# An experiment, that failed
custom_js = """
return factors[tick % 2 == 0 ? tick / 2 : null];
"""


def histogram(data, category_label, value_label="Number of Visits", bar_color="green", tick_every=1, max_xticks=30, max_yticks=40):
    # t = template.loader.get_template(self.template_name)
    # JS = JSResources(minified=False, mode='cdn')
    resources = Resources(minified=False, mode='cdn')

    cats = list(map(str, data.keys()))
    vals = list(data.values())
    cat_labels = cats[::tick_every]

    plot = figure(sizing_mode='stretch_both',  # Fill the container (use CSS of container to size)
                  x_axis_label=category_label,
                  y_axis_label=value_label,
                  x_range=cats,
                  background_fill_alpha=0,
                  border_fill_alpha=0,
                  )

    plot.toolbar.logo = None
    plot.toolbar_location = None
    plot.toolbar.active_drag = None
    plot.toolbar.active_scroll = None
    plot.toolbar.active_tap = None

    # Now we want to run the x axis from the min to max number of
    # players. And the frequency axis we'd like to run from 0 to the
    # max frequency.
    # xticks = len(cats)
    # xspace = 1 + xticks // max_xticks
    #
    # yticks = 1 + max(vals)
    # yspace = 1 + yticks // max_yticks
    #
    # xticker = list(range(0, xticks + 1, xspace))
    # yticker = list(range(0, max(vals) + 1, yspace))

    # plot.xaxis.ticker = MyTicker()
    # plot.yaxis.ticker = yticker

    # print(f"\n{category_label}")
    # print(f"DEBUG: {cats=}")
    # print(f"DEBUG: {xticker=}")
    # code = f"""
    # var labels = {cats};
    # var n = {tick_every};
    # return labels[tickIndex % n];
    # """
    # formatter = CustomJS(code=code)
    # plot.xaxis.formatter = formatter

    plot.y_range.start = 0

    plot.xaxis.major_label_orientation = math.pi / 2
    plot.xaxis.major_label_text_font_size = "16px"
    plot.yaxis.major_label_text_font_size = "16px"
    plot.xaxis.axis_label_text_font_size = "20px"
    plot.yaxis.axis_label_text_font_size = "20px"

    bars = plot.vbar(x=cats, top=vals, width=0.9, color=bar_color)

    graph_script, graph_div = components(plot)

    return {"JSfiles": resources.js_files, "script": graph_script, "div": graph_div}


def graph(data, xlabel, ylabel, line_color='green'):
    '''
    Produced a line graph.

    :param data: a dict, with x as key and y as value
    :param xlabel: an x-axis label
    :param ylabel: a y-axis label
    '''
    JS = JSResources(minified=False, mode='cdn')

    x = list(data.keys())
    y = list(data.values())
    y_smooth = np.poly1d(np.polyfit(x, y, 5))(x)

    plot = figure(sizing_mode='stretch_both',  # Fill the container (use CSS of container to size)
                  x_axis_label=xlabel,
                  y_axis_label=ylabel,
                  y_range=Range1d(0, max(y)),
                  # tools="pan,wheel_zoom,box_zoom,reset",
                  background_fill_alpha=0,
                  border_fill_alpha=0,
                  )

    plot.toolbar.logo = None
    plot.toolbar_location = None
    # plot.toolbar.active_drag = None
    # plot.toolbar.active_scroll = None
    # plot.toolbar.active_tap = None

    plot.yaxis.ticker = list(range(0, max(y)))

    line = plot.line(x, y_smooth, color=line_color, line_width=5)
    points = plot.dot(x, y, color='red', size=10)

    graph_script, graph_div = components(plot)

    return {"JSfiles": JS.js_files, "script": graph_script, "div": graph_div}


class HomePage(RichTemplateView):
    template_name = "homepage.html"

    def extra_context_provider(self, context={}):
        return general_context(self, context)


class Recent(RichTemplateView):
    template_name = "recent.html"

    def extra_context_provider(self, context={}):
        context["recent_visits"] = Visit.recent()

        return general_context(self, context)


class Trends(RichTemplateView):
    template_name = "trends.html"

    def extra_context_provider(self, context={}):
        # Extract colour information fromt he template
        variables = get_css_custom_properties(template=self.template_name, context=context)
        # This one is broken and needs diagnosing
        # bar_color = variables.get("text-header2", None)
        bar_color = variables.get("text-header", None)
        if bar_color:
            self.bar_color = parse_color(bar_color)
            print(f"{bar_color} -> {self.bar_color}")
        else:
            self.bar_color = "red"

        # match = re.search(r"HSL\(\s*(\d*\.?\d+)\s*,\s*(\d*\.?\d+)%\s*,\s*(\d*\.?\d+)%\s*\)", bar_color)
        # if match:
        #     h, s, l = map(float, match.groups())
        #     r, g, b = hls_to_rgb(h / 360, l / 100, s / 100)
        #     rgb_value = (int(r * 255), int(g * 255), int(b * 255))
        #     self.bar_color = rgb_value

        event_histogram = Event.histogram

        # A little asertion here on data integrity. Not literallya serted (with an asert) because while
        # teething in it has actually failed a fair bit. Just dumps enough diagnostics identify where
        # the assertion fails.
        orphans = len(Event.orphans)
        io = Event.invalid_orphans()

        allowance = 0
        for door in Door.objects.all():
            first = Event.first('doorcontact_state', door)
            last = Event.last('doorcontact_state', door)
            if first.value == 'Closed': allowance += 1
            if last.value == 'Open': allowance += 1

        if Opening.objects.all().count() * 2 + len(io) + allowance != event_histogram['doorcontact_state']:
            log.debug("Databases inconsistency")
            log.debug(f"\tEvents with code 'Door Contact State' : {event_histogram['doorcontact_state']}")
            log.debug(f"\tEvents with code 'Door Contact State' that are orphans (have no associate Opening): {event_histogram['doorcontact_state_orphans']}")
            log.debug(f"\tEvent.orphans: {orphans}")
            log.debug(f"\tEvent.invalid_orphans: {len(io)}    An valid orphan is one in which the door contact states either side (before and after) are NOT identical.")
            log.debug(f"\tA count of Openings: {Opening.objects.all().count()}")
            log.debug(f"\tExpected events for {Opening.objects.all().count()} Openings: {Opening.objects.all().count()*2}")
            log.debug(f"\tFirst events (Closed would be an orphan): {[Event.first('doorcontact_state', door).value for door in Door.objects.all()]}")
            log.debug(f"\tLast events (Open would be an orphan): {[Event.last('doorcontact_state', door).value for door in Door.objects.all()]}")
            log.debug(f"\tAllowance (being valid orphans, from First or Last): {allowance}")
            log.debug(f"\tCheck sum: {Opening.objects.all().count()*2}+{len(io)}+{allowance}={Opening.objects.all().count()*2+len(io)+allowance} and should = {event_histogram['doorcontact_state']}")

        # Visit histograms
        context["histogram_by_per_day"] = histogram(Visit.histogram("per_days"), "Visits per Day", bar_color=self.bar_color)
        context["histogram_by_hour_of_day"] = histogram(Visit.histogram("day"), "Hour of the Day", bar_color=self.bar_color)
        context["histogram_by_day_of_week"] = histogram(Visit.histogram("week"), "Day of the Week", bar_color=self.bar_color)
        context["histogram_by_day_of_month"] = histogram(Visit.histogram("month"), "Day of the Month", bar_color=self.bar_color)
        context["histogram_by_month_of_year"] = histogram(Visit.histogram("year", "months"), "Month", bar_color=self.bar_color)
        context["histogram_by_week_of_year"] = histogram(Visit.histogram("year", "weeks"), "Month", bar_color=self.bar_color)
        context["histogram_by_durations"] = histogram(Visit.histogram("durations", timedelta(seconds=30)), "Visit Duration (min:sec)", bar_color=self.bar_color, tick_every=3)
        context["histogram_by_quiet_times"] = histogram(Visit.histogram("quiet_times", timedelta(minutes=30)), "Quiet Time (min:sec)", bar_color=self.bar_color, tick_every=2)
        context["histogram_total_doors_per_visit"] = histogram(Visit.histogram("doors_per_visit_total"), "Total Doors Opened", bar_color=self.bar_color)
        context["histogram_unique_doors_per_visit"] = histogram(Visit.histogram("doors_per_visit_unique"), "Unique Doors Opened", bar_color=self.bar_color)

        # Opening histograms
        context["histogram_by_doors"] = histogram(Visit.histogram("opens_per_door"), "Door", value_label="Number of Openings", bar_color=self.bar_color)
        context["histogram_by_opening_durations"] = histogram(Opening.histogram("durations", timedelta(seconds=30)), "Opening Duration (min:sec)", value_label="Number of Openings", bar_color=self.bar_color, tick_every=2)

        return general_context(self, context)


class Technical(RichTemplateView):
    template_name = "technical.html"

    def extra_context_provider(self, context={}):
        # Extract colour information from the template
        variables = get_css_custom_properties(template=self.template_name, context=context)
        # This one is broken and needs diagnosing
        # bar_color = variables.get("text-header2", None)
        bar_color = variables.get("text-header", None)
        if bar_color:
            self.bar_color = parse_color(bar_color)
            print(f"{bar_color} -> {self.bar_color}")
        else:
            self.bar_color = "red"

        # Calculate the uptime statistcs
        uptimes = Uptime.objects.all().aggregate(count=Count('duration'), min=Min('duration'), max=Max('duration'), avg=Avg('duration'))

        context["count_uptimes"] = uptimes["count"]
        context["min_uptime"] = uptimes["min"]
        context["max_uptime"] = uptimes["max"]
        context["avg_uptime"] = uptimes["avg"]
        context["uptime_histogram"] = histogram(Uptime.histogram(), "Uptime duration (seconds)", "Frequency", bar_color=self.bar_color)

        context[f"battery_graphs"] = {}
        for door in Door.objects.all():
            context[f"battery_graphs"][door.id] = graph(Event.battery_graph(door), "Time (days)", "Battery Charge", line_color=self.bar_color)

        context["orphans"] = Event.orphans

        return general_context(self, context)


class Nearby(RichTemplateView):
    template_name = "nearby.html"

    def extra_context_provider(self, context={}):
        return general_context(self, context)

class Build(RichTemplateView):
    template_name = "build.html"

    def extra_context_provider(self, context={}):
        return general_context(self, context)
