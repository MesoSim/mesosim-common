# Copyright (c) 2020 MesoSim Developers.
# Distributed under the terms of the Apache 2.0 License.
# SPDX-License-Identifier: Apache-2.0
"""
Warning-related helper functions
"""

import re

# Imports
import pytz
from dateutil import parser, tz

from .core.timing import cur_time_from_arc


# Process the warning text (heavy lifiting!)
def process_warning_text(warning, timings):

    # Get the references
    cur_start_time = parser.parse(timings["cur_start_time"])

    # Now that we have that, process piece by piece!

    # Now let's try the %y%m%dT%H%MZ formated times
    # Note: parser.parse('160522T2322Z', yearfirst=True) parses out the warning
    # start/end times to datetime objects

    matches = list(
        re.finditer(
            r"(?P<timestamp>[0-9]{6}T[0-9]{4}Z)",
            warning,
        )
    )
    offset = 0
    try:
        for match in matches:
            new_timestamp = cur_time_from_arc(
                parser.parse(match.group("timestamp"), yearfirst=True), timings
            ).strftime("%y%m%dT%H%MZ")
            text_growth = len(new_timestamp) - len(match.group("timestamp"))

            warning = (
                warning[0 : (match.start("timestamp") + offset)]
                + new_timestamp
                + warning[(match.end("timestamp") + offset) :]
            )
            offset += text_growth

        # Also, since we need it later, get the starting timestamp in our standard
        # format
        warning_arc_time = parser.parse(matches[0].group("timestamp"), yearfirst=True)
        warning_arc_end_time = parser.parse(matches[1].group("timestamp"), yearfirst=True)

        # Replace the %d%H%M strings for start and end
        warning = warning.replace(
            warning_arc_time.strftime("%d%H%M"),
            cur_time_from_arc(warning_arc_time, timings).strftime("%d%H%M"),
        )
        warning = warning.replace(
            warning_arc_end_time.strftime("%d%H%M"),
            cur_time_from_arc(warning_arc_end_time, timings).strftime("%d%H%M"),
        )

        # Clean out the double time zone strings
        matches = list(
            re.finditer(
                (r"(?P<time_keep>[0-9]+ (PM|AM) (CDT|MDT))\/" + r"([0-9]+ (PM|AM) (CDT|MDT))\/?"),
                warning,
            )
        )
        for match in matches:
            warning = warning.replace(match.group(), match.group("time_keep"))

        # Update the '622 PM CDT SUN MAY 22 2016' string
        match = re.search(
            r"(?P<time>[0-9]+) (?P<apm>PM|AM) (?P<zone>CDT|MDT) "
            + r"(?P<weekday>[A-Za-z]{3}) (?P<month>[A-Za-z]{3}) "
            + r"(?P<day>[0-9]+) (?P<year>20[0-9]{2})",
            warning,
        )
        if match:
            if match.group("zone") == "CDT":
                zone_txt = "CDT"
                zone = "-05:00"
                tz_zone_offset = -18000
            elif match.group("zone") == "MDT":
                zone_txt = "MDT"
                zone = "-06:00"
                tz_zone_offset = -21600

            year = int(match.group("year"))
            month = parser.parse(match.group("month")).month
            day = int(match.group("day"))
            hour = int(match.group("time")[:-2]) + (0 if match.group("apm") == "AM" else 12)
            minute = int(match.group("time")[-2:])

            arc_local_time = parser.parse(
                "{}-{}-{}T{}:{}{}".format(year, month, day, hour, minute, zone)
            )
            arc_utc_time = arc_local_time.astimezone(pytz.UTC)
            cur_utc_time = cur_time_from_arc(arc_utc_time, timings)
            cur_local_time = cur_utc_time.astimezone(tz.tzoffset(None, tz_zone_offset))

            str_to_swap = []
            for time_obj in (arc_local_time, cur_local_time):
                swap_time = time_obj.strftime("%-I%M %p")
                swap_zone = match.group("zone") if time_obj < cur_start_time else zone_txt
                swap_weekday = time_obj.strftime("%a").upper()
                swap_month = time_obj.strftime("%b").upper()
                swap_day = time_obj.strftime("%-d")
                swap_year = time_obj.strftime("%Y")
                str_to_swap.append(
                    " ".join((swap_time, swap_zone, swap_weekday, swap_month, swap_day, swap_year))
                )

            # TODO: this needs to be changed to be a case insensitive swap for cases
            # after the warnings WERE NO LONGER YELLING
            print(str_to_swap)
            warning = re.sub(*str_to_swap, warning, flags=re.IGNORECASE)

            # Now, do likewise (with some magic) for all the '622 PM CDT'
            # after the end of that
            pattern = re.compile(r"(?P<time>[0-9]+) (?P<apm>PM|AM) (?P<zone>CDT|MDT)")
            matches = pattern.finditer(warning, pos=match.end())
            offset = 0
            for match in matches:

                hour = int(match.group("time")[:-2]) + (0 if match.group("apm") == "AM" else 12)
                minute = int(match.group("time")[-2:])
                if match.group("zone") == "CDT":
                    zone_txt = "CDT"
                    zone = "-05:00"
                    tz_zone_offset = -18000
                elif match.group("zone") == "MDT":
                    zone_txt = "MDT"
                    zone = "-06:00"
                    tz_zone_offset = -21600

                arc_local_time = parser.parse(
                    "{}-{}-{}T{}:{}{}".format(year, month, day, hour, minute, zone)
                )
                arc_utc_time = arc_local_time.astimezone(pytz.UTC)
                cur_utc_time = cur_time_from_arc(arc_utc_time, timings)
                cur_local_time = cur_utc_time.astimezone(tz.tzoffset(None, tz_zone_offset))

                replacement = cur_local_time.strftime("%-I%M %p") + " " + zone_txt
                text_growth = len(replacement) - len(match.group())

                warning = (
                    warning[0 : (match.start() + offset)]
                    + replacement
                    + warning[(match.end() + offset) :]
                )
                offset += text_growth

        # All done with the processing! Return the processed text and the valid
        # cur time
        return warning, cur_time_from_arc(warning_arc_time, timings)
    except:
        print("ERROR in processing warning...return null result")
        return "", cur_start_time 
