"""Booking periods as a person would say them."""

from django import template
from django.template.defaultfilters import date as date_filter
from django.utils import timezone

register = template.Library()


@register.simple_tag
def period(start, end, day_format="l, d F Y"):
    """"Friday, 02 October 2026, 15:00 to 17:00" when both ends fall on one
    day; the second date is spelt out only when it differs."""
    start = timezone.localtime(start)
    end = timezone.localtime(end)
    first = f"{date_filter(start, day_format)}, {date_filter(start, 'H:i')}"
    if start.date() == end.date():
        return f"{first} to {date_filter(end, 'H:i')}"
    return f"{first} to {date_filter(end, day_format)}, {date_filter(end, 'H:i')}"
