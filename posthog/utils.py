from dateutil.relativedelta import relativedelta
from django.utils.timezone import now
from django.db.models import Q
from typing import Dict, Any, List, Union
from django.template.loader import get_template
from django.http import HttpResponse, JsonResponse, HttpRequest
from dateutil import parser

import datetime
import json
import re
import os
import pytz

def relative_date_parse(input: str) -> datetime.datetime:
    try:
        return datetime.datetime.strptime(input, '%Y-%m-%d').replace(tzinfo=pytz.UTC)
    except ValueError:
        pass
    
    # when input also contains the time for intervals "hour" and "minute"
    # the above try fails. Try one more time from isoformat.
    try:
        return parser.isoparse(input).replace(tzinfo=pytz.UTC)
    except ValueError:
        pass

    regex = r"\-?(?P<number>[0-9]+)?(?P<type>[a-z])(?P<position>Start|End)?"
    match = re.search(regex, input)
    date = now()
    if not match:
        return date
    if match.group('type') == 'd':
        if match.group('number'):
            date = date - relativedelta(days=int(match.group('number')))
    elif match.group('type') == 'm':
        if match.group('number'):
            date = date - relativedelta(months=int(match.group('number')))
        if match.group('position') == 'Start':
            date = date - relativedelta(day=1)
        if match.group('position') == 'End':
            date = date - relativedelta(day=31)
    elif match.group('type') == 'y':
        if match.group('number'):
            date = date - relativedelta(years=int(match.group('number')))
        if match.group('position') == 'Start':
            date = date - relativedelta(month=1, day=1)
        if match.group('position') == 'End':
            date = date - relativedelta(month=12, day=31)
    return date.replace(hour=0, minute=0, second=0, microsecond=0)

def request_to_date_query(filters: Dict[str, Any]) -> Dict[str, datetime.date]:
    if filters.get('date_from'):
        date_from = relative_date_parse(filters['date_from']).date()
        if filters['date_from'] == 'all':
            date_from = None # type: ignore
    else:
        date_from = datetime.date.today() - relativedelta(days=7)

    date_to = None
    if filters.get('date_to'):
        date_to = relative_date_parse(filters['date_to']).date()

    resp = {}
    if date_from:
        resp['timestamp__gte'] = date_from
    if date_to:
        resp['timestamp__lte'] = date_to + relativedelta(days=1)
    return resp

def render_template(template_name: str, request: HttpRequest, context=None) -> HttpResponse:
    from posthog.models import Team
    if context is None:
        context = {}
    template = get_template(template_name)
    try:
        context.update({
            'opt_out_capture': request.user.team_set.get().opt_out_capture
        })
    except (Team.DoesNotExist, AttributeError):
        team = Team.objects.all()
        # if there's one team on the instance, and they've set opt_out
        # we'll opt out anonymous users too
        if team.count() == 1:
            context.update({
                'opt_out_capture': team.first().opt_out_capture, # type: ignore
            })

    if os.environ.get('SENTRY_DSN'):
        context.update({
            'sentry_dsn': os.environ['SENTRY_DSN']
        })

    attach_social_auth(context)
    html = template.render(context, request=request)
    return HttpResponse(html)

def attach_social_auth(context):
    if os.environ.get('SOCIAL_AUTH_GITHUB_KEY') and os.environ.get('SOCIAL_AUTH_GITHUB_SECRET'):
        context.update({
            'github_auth': True
        })
    if os.environ.get('SOCIAL_AUTH_GITLAB_KEY') and os.environ.get('SOCIAL_AUTH_GITLAB_SECRET'):
        context.update({
            'gitlab_auth': True
        })
    
def friendly_time(seconds: float):
    minutes, seconds = divmod(seconds, 60.0)
    hours, minutes = divmod(minutes, 60.0)
    return '{hours}{minutes}{seconds}'.format(\
        hours='{h} hours '.format(h=int(hours)) if hours > 0 else '',\
        minutes='{m} minutes '.format(m=int(minutes)) if minutes > 0 else '',\
        seconds='{s} seconds'.format(s=int(seconds)) if seconds > 0 or (minutes == 0 and hours == 0) else '').strip()

def append_data(dates_filled: List, interval=None, math='sum') -> Dict:
    append: Dict[str, Any] = {}
    append['data'] = []
    append['labels'] = []
    append['days'] = []

    labels_format = '%a. %-d %B'
    days_format = '%Y-%m-%d'

    if interval == 'hour' or interval == 'minute':
        labels_format += ', %H:%M'
        days_format += ' %H:%M:%S'

    for item in dates_filled:
        date=item[0]
        value=item[1]
        append['days'].append(date.strftime(days_format))
        append['labels'].append(date.strftime(labels_format))
        append['data'].append(value)
    if math == 'sum':
        append['count'] = sum(append['data'])
    return append

def get_ip_address(request: HttpRequest) -> str:
    """ use requestobject to fetch client machine's IP Address """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')    ### Real IP address of client Machine
    return ip

def dict_from_cursor_fetchall(cursor):
    columns = [col[0] for col in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]

def convert_property_value(input: Union[str, bool, dict, list]) -> str:
    if isinstance(input, bool):
        if input == True:
            return 'true'
        return 'false'
    if isinstance(input, dict) or isinstance(input, list):
        return json.dumps(input, sort_keys=True)
    return input