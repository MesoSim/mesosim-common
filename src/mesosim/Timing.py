"""
Timing-related helper functions

...

arc_time_from_cur, cur_time_from_arc (use timings)
"""

# Imports
from datetime import datetime
from dateutil import parser

# Define standard format
std_fmt = '%Y-%m-%dT%H:%M:%SZ'


# Archive time given current time
def arc_time_from_cur(cur_time, timings):

    # Get the references
    arc_start_time = parser.parse(timings['arc_start_time'])
    cur_start_time = parser.parse(timings['cur_start_time'])
    speed_factor = timings['speed_factor']

    if type(cur_time) is datetime:
        return arc_start_time + (cur_time - cur_start_time) * speed_factor
    elif type(cur_time) is str:
        return (arc_start_time +
                (parser.parse(cur_time) - cur_start_time) *
                speed_factor).strftime(std_fmt)
    else:
        raise ValueError('cur_time must be str or datetime.datetime')


# Current time given archive time
def cur_time_from_arc(arc_time, timings):

    # Get the references
    arc_start_time = parser.parse(timings['arc_start_time'])
    cur_start_time = parser.parse(timings['cur_start_time'])
    speed_factor = timings['speed_factor']

    if type(arc_time) is datetime:
        return cur_start_time + (arc_time - arc_start_time) / speed_factor
    elif type(arc_time) is str:
        return (cur_start_time +
                (parser.parse(arc_time) - arc_start_time) /
                speed_factor).strftime(std_fmt)
    else:
        raise ValueError('arc_time must be str or datetime.datetime')
