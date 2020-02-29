"""
LSR-specific helper functions

...
"""

# Imports
import pytz
import textwrap
from dateutil import parser
from .Timing import cur_time_from_arc
from math import floor


# Go from lsr `type` to gr_icon (also used to just keep our LSRs of interest)
def type_to_icon(type_str):
    type_dict = {'C': 1, 'H': 2, 'T': 3, 'D': 4}
    if type_str in type_dict:
        return type_dict[type_str]
    else:
        return None


# Go from the type and magnitude to the correct sprite location
def get_hail_pos(type, size):
    # If not hail, it is one
    if type != 'HAIL':
        return 1
    else:
        try:
            pos = floor(float(size)/0.25) + 1
        except Exception as e:
            return 1  # If it errors, just basic

        if pos > 16:
            return 16  # Max out at 16
        elif pos < 1:
            return 1  # Min at 1
        else:
            return pos


# Create a GR Placefile entry for a lsr tuple
def gr_lsr_placefile_entry_from_tuple(lsr_tuple, wrap_length):
    return """Object: {lat:.2f}, {lon:.2f}
Icon: 0,0,000,{icon},{pos},"{text}"
End:""".format(
        lat=lsr_tuple[2],
        lon=lsr_tuple[3],
        icon=type_to_icon(lsr_tuple[8]),
        pos=get_hail_pos(lsr_tuple[9], lsr_tuple[4]),
        text=("%r" % gr_lsr_text(lsr_tuple, wrap_length=wrap_length))[1:-1]
    )


# Create the GR LSR text box text
def gr_lsr_text(lsr_tuple, wrap_length):
    fields = [lsr_tuple[9],
              parser.parse(lsr_tuple[10]).astimezone(
                  pytz.timezone('US/Central')).strftime('%-I:%M %p'),
              lsr_tuple[0],
              '{}, {}'.format(lsr_tuple[1], lsr_tuple[7]),
              lsr_tuple[6],
              "\n".join(textwrap.wrap(lsr_tuple[5], wrap_length))]

    if fields[0] == 'HAIL':
        fields[-1] = '{} INCH'.format(lsr_tuple[4])

    template = ('Event:  {}\nTime:   {}\nPlace:  {}\nCounty: {}\n' +
                'Source: {}\n\n{}')

    return template.format(*fields)


# Scale the raw lsr tuples from arc to cur time (element 10)
def scale_raw_lsr_to_cur_time(raw_tuple_list, timings):
    scaled_tuple_list = []
    for raw_tuple in raw_tuple_list:
        scaled_tuple_list.append((
            raw_tuple[0],
            raw_tuple[1],
            raw_tuple[2],
            raw_tuple[3],
            raw_tuple[4],
            raw_tuple[5],
            raw_tuple[6],
            raw_tuple[7],
            raw_tuple[8],
            raw_tuple[9],
            cur_time_from_arc(raw_tuple[10], timings=timings),
            raw_tuple[11],
        ))
    return scaled_tuple_list
