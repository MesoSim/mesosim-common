#!/usr/bin/env python

"""
Functions for hazards

These are the functions to make the chase applet work.
"""

import numpy as np
from datetime import datetime
import pytz


from .App import Hazard, Vehicle


def create_hazard_registry(config):
    """Create the list of all possible hazards given current config."""
    hazard_list = []

    # Speeding
    def speeding_func(status):
        if status['speed'] - config.speed_limit > 15:
            # Ticket!
            status['balance'] -= config.hazard_config('speeding_ticket')
            status['status_text'] = 'Pulled Over and Ticketed'
        else:
            # Warning.
            status['status_text'] = 'Pulled Over'
        status['speed'] = 0.
        status['status_color'] = 'red'
        status['active_hazard'] = 'speeding'

        return status

    def speeding_prob(status):
        exceedance = status['speed'] - config.speed_limit
        if exceedance > 50:
            return 0.64
        elif exceedance > 0:
            return (exceedance / 50)**2.5 * 0.64
        else:
            return 0.

    hazard_list.append(Hazard(
        'speeding',
        speeding_func,
        speeding_prob,
        'You were pulled over for speeding.',
        message_end='You are free to go.',
        duration_min=1.5,
        speed_lock=True
    ))

    # Dirt Road
    def dirt_road_func(status):
        status['speed'] = min(status['speed'],
                              Vehicle(status['vehicle'], config).top_speed_on_dirt)
        status['status_color'] = 'yellow'
        status['status_text'] = 'On a dirt road'
        status['active_hazard'] = 'dirt_road'

        return status

    hazard_list.append(Hazard(
        'dirt_road',
        dirt_road_func,
        (lambda x: 0.01),
        'You turned on to a dirt road.',
        message_end='You are back on pavement.',
        duration_min=2.,
        overridden_by_list=['end_chase', 'stuck_in_mud']
    ))

    # Stuck in mud
    def stuck_in_mud_func(status):
        status['speed'] = 0.
        status['status_color'] = 'red'
        status['status_text'] = 'Stuck in mud!'
        status['active_hazard'] = 'stuck_in_mud'

        return status

    def stuck_in_mud_prob(status):
        time_mult = max(3., (datetime.now(tz=pytz.UTC) - config.start_time).seconds / 1800)
        if status['active_hazard'] == 'dirt_road':
            return Vehicle(status['vehicle'], config).stuck_probability * time_mult
        else:
            return 0

    hazard_list.append(Hazard(
        'stuck_in_mud',
        stuck_in_mud_func,
        stuck_in_mud_prob,
        'You\'ve gotten stuck in the mud.',
        message_end='You finally got unstuck.',
        duration_min=1. + np.random.random() * 7,
        speed_lock=True
    ))

    # Chaser convergence
    def cc_func(status):
        status['speed'] = 15 + 5 * np.floor(np.random.random() * 7)
        status['status_color'] = 'yellow'
        status['status_text'] = 'Chaser Convergence'
        status['active_hazard'] = 'cc'

    def cc_prob(status):
        time_mult = max(2., (datetime.now(tz=pytz.UTC) - config.start_time).seconds / 1800)
        if status['active_hazard'] == 'dirt_road':
            return 0
        else:
            return 0.021 * time_mult

    hazard_list.append(Hazard(
        'cc',
        cc_func,
        cc_prob,
        'You\'ve encountered chaser convergence.',
        message_end='The chaser convergence has cleared.',
        duration_min=1. + np.random.random() * 7,
        speed_limit=15 + 5 * np.floor(np.random.random() * 7)
    ))

    # Flat tire
    def flat_tire_func(status):
        status['speed'] = 0.
        status['status_color'] = 'red'
        status['status_text'] = 'Flat Tire!'
        status['active_hazard'] = 'flat_tire'

        return status

    hazard_list.append(Hazard(
        'flat_tire',
        flat_tire_func,
        (lambda x: 0.001),
        'You\'ve gotten a flat tire.',
        message_end='You finally got the flat fixed.',
        duration_min=3. + np.random.random() * 3,
        speed_lock=True
    ))

    # End chase
    def end_chase_func(status):
        status['speed'] = 0.
        status['status_color'] = 'red'
        status['status_text'] = 'Chase Ended'
        status['active_hazard'] = 'end_chase'

        return status

    hazard_list.append(Hazard(
        'flat_tire',
        flat_tire_func,
        (lambda x: 0.),
        '...CHASE TERMINATED...',
        duration_min=1000,
        speed_lock=True,
        direction_lock=True
    ))

    return {hazard.type: hazard for hazard in hazard_list}


def shuffle_new_hazard(team, seconds, hazards):
    """Given a time interval, use registered hazards to shuffle a chance of a new hazard."""
    # Hazards
    hazard_list = list(hazards.values())
    hazard_probs = [hazard.probability(team.status) for hazard in hazard_list]
    # Non-Hazard (remaining chance)
    hazard_list.append(None)
    hazard_probs.append(max(1. - np.sum(hazard_probs), 0.))
    # Select one randomly
    return np.random.choice(hazard_list, p=hazard_probs)
