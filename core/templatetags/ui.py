from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def icon(name, size=None, cls=''):
    """Render an icon from the sprite in partials/icons.html."""
    style = format_html(' style="width:{0}px;height:{0}px"', size) if size else ''
    return format_html('<svg class="i {}"{} aria-hidden="true" focusable="false"><use href="#i-{}"></use></svg>', cls, style, name)


@register.simple_tag
def status_icon(status):
    return {
        'pending': 'clock', 'reviewed': 'circle-check', 'repeat': 'refresh-cw',
        'unreadable': 'eye-off', 'draft': 'file-text',
    }.get(status, 'info')
