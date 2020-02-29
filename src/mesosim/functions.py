#!/usr/bin/env python

"""
Helper Functions for Chase Applet

These are the functions to make the chase applet work.
"""

import pandas as pd
from math import floor
from pyproj import Geod


city_csv = 'uscitiesv1.4.csv'  # from https://simplemaps.com/data/us-cities
g = Geod('sphere')  # set up Geod


def move_lat_lon(lat, lon, distance_miles, angle_degrees):
    """Calculate displacement to new point."""
    distance_m = distance_miles * 1609.344  # convert
    new_lon, new_lat, _ = g.fwd(lon, lat, angle_degrees, distance_m)
    return new_lat, new_lon


def money_format(money):
    # Make a nice money string from a float
    return '${:,.2f}'.format(money)


def nearest_city(lat, lon, config):
    """Find the nearest City, ST, Distance, Direction from this point."""

    # Get city data
    data = pd.read_csv(city_csv)

    # Get search bounds
    corner_lat, corner_lon = move_lat_lon(lat, lon, config.min_town_distance_search, 45)
    diff_lat, diff_lon = corner_lat - lat, corner_lon - lon

    # Get cities within box
    subset = data[(data['population'] > config.min_town_population) &
                  (lat - diff_lat <= data['lat']) & (data['lat'] <= lat + diff_lon) &
                  (lon - diff_lon <= data['lng']) & (data['lng'] <= lon + diff_lon)]

    candidate_cities = []
    for _, row in subset.iterrows():
        forward_az, _, distance_m = g.inv(lon, lat, row['lng'], row['lat'])
        distance_miles = distance_m / 1609.344  # convert
        angle_degrees = forward_az % 360.
        candidate_cities.append((
            row['city_ascii'],
            row['state_id'],
            distance_miles,
            angle_degrees))

    # Return closest city (min distance)
    if len(candidate_cities) > 0:
        return sorted(candidate_cities, key=lambda tup: tup[-1])[0]
    else:
        return (None,) * 4


def direction_angle_to_str(angle):
    """Convert the given angle to a direction string."""
    idx = floor((angle + 11.25) % 360 / 22.5)
    angle_str_list = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW',
                      'WSW', 'W', 'WNW', 'NW', 'NNW']
    return angle_str_list[idx]
