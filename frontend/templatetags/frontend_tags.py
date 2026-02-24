"""Template tags and filters for the frontend app."""

import json

from django import template

register = template.Library()


@register.filter
def get_field(form, field_name):
    """Get a form field by name: {{ form|get_field:'name' }}."""
    try:
        return form[field_name]
    except KeyError:
        return ""


@register.filter
def get_item(dictionary, key):
    """Get a dictionary value by key: {{ dict|get_item:key }}."""
    if isinstance(dictionary, dict):
        return dictionary.get(key, "")
    return ""


@register.filter
def get_attr(obj, attr_name):
    """Get an object attribute by name: {{ obj|get_attr:'field' }}."""
    if isinstance(obj, dict):
        return obj.get(attr_name, "")
    return getattr(obj, attr_name, "")


@register.filter
def json_pretty(value):
    """Pretty-print a JSON-serializable value."""
    try:
        return json.dumps(value, indent=2, default=str)
    except (TypeError, ValueError):
        return str(value)


@register.filter
def split(value, sep):
    """Split a string by separator: {{ 'a,b,c'|split:',' }}."""
    if isinstance(value, str):
        return value.split(sep)
    return []
