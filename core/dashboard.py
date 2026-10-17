"""Presentation helpers for the overview page (charts, calendar, greeting)."""
import calendar
from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

CHART_W, CHART_H, CHART_PAD_TOP, CHART_PAD_BOTTOM = 640, 220, 16, 8

OUTCOMES = [
    ('reviewed', 'Reviewed', '#0a9e74'),
    ('pending', 'Pending review', '#2cdea4'),
    ('repeat', 'Repeat requested', '#f2b54a'),
    ('unreadable', 'Unable to read', '#e8737a'),
]


def greeting(now=None):
    hour = timezone.localtime(now).hour
    if hour < 12:
        return 'Good morning'
    if hour < 17:
        return 'Good afternoon'
    return 'Good evening'


def _nice_max(value):
    for step in (4, 8, 12, 20, 40, 60, 100, 200, 400, 1000):
        if value <= step:
            return step
    return value


def _smooth_path(points):
    """Catmull-Rom spline through points, emitted as cubic Bézier segments."""
    if len(points) < 2:
        return ''
    d = [f'M{points[0][0]:.1f},{points[0][1]:.1f}']
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i else points[i]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        # Keep the curve inside the plot so zero days never dip below the axis.
        floor = CHART_H - CHART_PAD_BOTTOM
        c1 = (c1[0], min(c1[1], floor))
        c2 = (c2[0], min(c2[1], floor))
        d.append(f'C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}')
    return ' '.join(d)


def activity_chart(qs, days=14):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    rows = (qs.filter(submitted_at__date__gte=start)
              .annotate(day=TruncDate('submitted_at'))
              .values('day').annotate(n=Count('id')))
    by_day = {r['day']: r['n'] for r in rows}
    series = [(start + timedelta(days=i), by_day.get(start + timedelta(days=i), 0)) for i in range(days)]
    top = _nice_max(max([n for _, n in series] + [1]))
    plot_h = CHART_H - CHART_PAD_TOP - CHART_PAD_BOTTOM
    step = CHART_W / (days - 1)
    points, items = [], []
    for i, (day, n) in enumerate(series):
        x = i * step
        y = CHART_PAD_TOP + plot_h * (1 - n / top)
        points.append((x, y))
        items.append({'x': round(x, 1), 'y': round(y, 1), 'left': round(x / CHART_W * 100, 2),
                      'top': round(y / CHART_H * 100, 2), 'count': n,
                      'label': day.strftime('%a %d %b'), 'short': day.strftime('%d %b'),
                      'show_label': i % 2 == (days - 1) % 2, 'is_today': day == today})
    line = _smooth_path(points)
    area = f'{line} L{CHART_W},{CHART_H} L0,{CHART_H} Z' if line else ''
    grid = []
    for k in range(5):
        value = round(top * (4 - k) / 4)
        grid.append({'y': round(CHART_PAD_TOP + plot_h * k / 4, 1), 'value': value,
                     'top': round((CHART_PAD_TOP + plot_h * k / 4) / CHART_H * 100, 2)})
    total = sum(n for _, n in series)
    prev = qs.filter(submitted_at__date__gte=start - timedelta(days=days), submitted_at__date__lt=start).count()
    change = None if not prev else round((total - prev) / prev * 100)
    return {'w': CHART_W, 'h': CHART_H, 'line': line, 'area': area, 'points': items, 'grid': grid,
            'total': total, 'change': change, 'days': days}


def outcome_donut(counts):
    total = sum(counts.get(key, 0) for key, *_ in OUTCOMES)
    segments, stops, cursor = [], [], 0.0
    for key, label, colour in OUTCOMES:
        n = counts.get(key, 0)
        share = (n / total * 100) if total else 0
        segments.append({'key': key, 'label': label, 'colour': colour, 'count': n, 'share': round(share)})
        if n:
            stops.append(f'{colour} {cursor:.2f}% {cursor + share:.2f}%')
            cursor += share
    gradient = f"conic-gradient({', '.join(stops)})" if stops else 'conic-gradient(#e6eceb 0 100%)'
    return {'segments': segments, 'gradient': gradient, 'total': total}


def month_calendar(qs):
    today = timezone.localdate()
    first = today.replace(day=1)
    active_days = set(qs.filter(submitted_at__date__gte=first, submitted_at__date__lte=today)
                        .annotate(day=TruncDate('submitted_at')).values_list('day', flat=True))
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(today.year, today.month)
    cells = [[{'day': d.day, 'outside': d.month != today.month, 'today': d == today,
               'active': d in active_days, 'iso': d.isoformat()} for d in week] for week in weeks]
    return {'label': today.strftime('%B %Y'), 'weeks': cells, 'weekdays': ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']}
