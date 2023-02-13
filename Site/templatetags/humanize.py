from django import template
import humanize

register = template.Library()

# registers all humanize functions as template tags
for funcname in [name for name in dir(humanize) if callable(getattr(humanize, name))]:
    func = getattr(humanize, funcname)
    register.simple_tag(func, False, funcname)
