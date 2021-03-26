# Copyright (c) 2020 MesoSim Developers.
# Distributed under the terms of the Apache 2.0 License.
# SPDX-License-Identifier: Apache-2.0
r"""Actions/Hazards documentation TODO"""

import json
from datetime import datetime, timedelta
from functools import partial

import numpy as np
import pytz
from dateutil import parser

from ..core.timing import db_time_fmt
from ..core.utils import maybe_cast_float


class Action:
    """
    Actions! Basic changes or messages as itself, and base interface for hazards.
    """

    action_id = None
    action_type = None
    action_field = None
    action_amount = None
    is_adjustment = False
    is_hazard = False
    message = ""

    def __init__(self, action_tuple):
        # Initialize given action_tuple=(id, message, type, amount, _)
        self.action_id = action_tuple[0]
        self.message = action_tuple[1]
        if "_" in action_tuple[2]:
            self.action_type, self.action_field = action_tuple[2].split("_", 1)
        else:
            self.action_type = action_tuple[2]
        self.action_amount = action_tuple[3]

        if self.action_type in ["set", "change"]:
            self.is_adjustment = True

    def generate_message(self):
        """Generate the message."""
        return datetime.now(tz=pytz.UTC).strftime("%H%MZ") + ": " + self.message

    def alter_status(self, team):
        """Alter status if needed by action_type."""
        if self.is_adjustment:
            # only adjust if this action is an adjustment
            if self.action_type == "set":
                team.status[self.action_field] = self.action_amount
            elif self.action_type == "change":
                team.status[self.action_field] = float(team.status[self.action_field]) + float(
                    self.action_amount
                )


class Hazard(Action):
    """
    Hazards! Real stuff is going down here.
    """

    is_adjustment = False
    is_hazard = True
    action_type = "hazard"
    expiry_time = None
    overridden_by_list = []
    message_end = None
    speed_limit = None
    direction_lock = False
    speed_lock = False

    def __init__(
        self,
        hazard_type,
        alter_status=None,
        probability=None,
        message=None,
        message_end=None,
        duration_min=None,
        overridden_by_list=["end_chase"],
        speed_limit=None,
        direction_lock=False,
        speed_lock=False,
    ):
        self.type = hazard_type  # string
        self.alter_status = alter_status  # function(team, config, hazard)
        self.probability = probability  # function(team, config, hazard)
        self.message = message  # string or iterable of strings
        self.message_end = message_end
        self.expiry_time = datetime.now(tz=pytz.UTC) + timedelta(minutes=duration_min)
        self.overridden_by_list = overridden_by_list
        self.speed_limit = speed_limit
        self.direction_lock = direction_lock
        self.speed_lock = speed_lock

    @classmethod
    def from_hazard_tuple(cls, hazard_tuple):
        return cls(
            hazard_tuple[0],
            message=json.loads(hazard_tuple[2]),
            message_end=json.loads(hazard_tuple[3]),
            expiry_time=parser.parse(hazard_tuple[1]),
            overridden_by_list=json.loads(hazard_tuple[4]),
            speed_limit=maybe_cast_float(hazard_tuple[5]),
            direction_lock=bool(hazard_tuple[6]),
            speed_lock=bool(hazard_tuple[7]),
        )

    def update_from_tuple(self, hazard_tuple):
        self.message = json.loads(hazard_tuple[2])
        self.message_end = json.loads(hazard_tuple[3])
        self.expiry_time = parser.parse(hazard_tuple[1])
        self.overridden_by_list = json.loads(hazard_tuple[4])
        self.speed_limit = maybe_cast_float(hazard_tuple[5])
        self.direction_lock = bool(hazard_tuple[6])
        self.speed_lock = bool(hazard_tuple[7])
        return self

    def to_hazard_tuple(self):
        return (
            self.type,
            self.expiry_time.strftime(db_time_fmt),
            json.dumps(self.message),
            json.dumps(self.message_end),
            json.dumps(self.overridden_by_list),
            str(self.speed_limit),
            str(self.direction_lock),
            str(self.speed_lock),
        )

    def _choose_message(self, end=False):
        """Flexibly choose message or end message as given or random from list."""
        msg = self.message_end if end else self.message
        if isinstance(msg, (list, tuple)):
            return np.random.choice(msg)
        else:
            return msg

    def generate_expiry_message(self):
        """Generate the expiry message."""
        message = self._choose_message(end=True)
        if message is not None:
            return datetime.now(tz=pytz.UTC).strftime("%H%MZ") + ": " + message
        else:
            return ""

    def overridden_by(self, other_hazard):
        """Check if this hazard is overridden by the other hazard type."""
        return other_hazard.type in self.overridden_by_list


def create_hazard_registry(config):
    """Create the dictionary of all possible hazards given current config."""
    hazard_list = []

    ############
    # Speeding #
    ############
    def speeding_alter_status(team, config, hazard):
        if team.speed - config.speed_limit > 15:
            # Ticket!
            team.balance -= config.hazard_config("speeding_ticket")
            team.status_text = "Pulled Over and Ticketed"
        else:
            # Warning.
            team.status_text = "Pulled Over"
        team.speed = 0.0
        team.status_color = "red"

    def speeding_prob(team, config, hazard):
        max_chance = config.hazard_config("speeding_max_chance")
        exceedance = team.speed - config.speed_limit
        if team.override_hazard("speeding") or exceedance <= 0:
            return 0.0
        elif exceedance < 50:
            return (exceedance / 50) ** 2.5 * max_chance
        else:
            return max_chance

    if "speeding" in config.active_hazards:
        hazard_list.append(
            Hazard(
                "speeding",
                speeding_alter_status,
                speeding_prob,
                "You were pulled over for speeding.",
                message_end="You are free to go.",
                duration_min=1.5,
                speed_lock=True,
            )
        )

    #############
    # Dirt Road #
    #############
    def dirt_road_alter_status(team, config, hazard):
        team.speed = min(team.speed, team.vehicle.top_speed_on_dirt)
        team.status_color = "yellow"
        team.status_text = "On a dirt road"

    dirt_road_prob = config.hazard_config("dirt_road_prob")

    if "dirt_road" in config.active_hazards:
        hazard_list.append(
            Hazard(
                "dirt_road",
                dirt_road_alter_status,
                (lambda x, y, z: dirt_road_prob),
                "You turned on to a dirt road.",
                message_end="You are back on pavement.",
                duration_min=2.0,
                overridden_by_list=["end_chase", "stuck_in_mud"],
            )
        )

    ################
    # Stuck in mud #
    ################
    def stuck_in_mud_alter_status(team, config, hazard):
        team.speed = 0.0
        team.status_color = "red"
        team.status_text = "Stuck in mud!"

    def stuck_in_mud_prob(team, config, hazard):
        # Start with zero chance, then ramp up to triple chance at 90 minutes into sim
        time_mult = max(3.0, (datetime.now(tz=pytz.UTC) - config.start_time).seconds / 1800)
        if team.is_hazard_active("dirt_road"):
            return team.vehicle.stuck_probability * time_mult
        else:
            return 0.0

    if "dirt_road" in config.active_hazards and "stuck_in_mud" in config.active_hazards:
        hazard_list.append(
            Hazard(
                "stuck_in_mud",
                stuck_in_mud_alter_status,
                stuck_in_mud_prob,
                "You've gotten stuck in the mud.",
                message_end="You finally got unstuck.",
                duration_min=1.0 + np.random.random() * 7,
                speed_lock=True,
                overridden_by_list=["end_chase"],
            )
        )

    ######################
    # Chaser convergence #
    ######################
    cc_speed_limit_init = np.random.choice(np.arange(15, 50, 5))

    def cc_alter_status(team, config, hazard):
        team.speed = hazard.speed_limit
        team.status_color = "yellow"
        team.status_text = "Chaser Convergence"

    def cc_prob(team, config, hazard):
        # Zero to start, ramping to double by 60 minutes in
        time_mult = max(2.0, (datetime.now(tz=pytz.UTC) - config.start_time).seconds / 1800)
        if team.is_hazard_active("dirt_road") or team.speed == 0.0:
            return 0.0
        else:
            return config.hazard_config("cc_prob") * time_mult

    if "cc" in config.active_hazards:
        hazard_list.append(
            Hazard(
                "cc",
                cc_alter_status,
                cc_prob,
                "You've encountered chaser convergence.",
                message_end="The chaser convergence has cleared.",
                duration_min=(
                    1.0 + (cc_speed_limit_init - 15) / 30
                    + np.random.random() * (1 + (cc_speed_limit_init - 15) / 15)**1.5706
                ),
                speed_limit=cc_speed_limit_init,
            )
        )

    #############
    # Flat tire #
    #############
    pay_for_flat_init = np.random.random() < float(config.hazard_config("pay_for_flat_prob"))

    def flat_tire_alter_status(team, config, hazard):
        team.speed = 0.0
        team.status_color = "red"
        team.status_text = "Flat Tire!"
        if pay_for_flat_init:
            team.balance -= float(config.hazard_config("pay_for_flat_amt"))

    flat_tire_prob = config.hazard_config("flat_tire_prob")
    if pay_for_flat_init:
        flat_msg = "You've gotten a flat tire, and it looks like you have to pay for repairs."
    else:
        flat_msg = "You've gotten a flat tire."

    if "flat_tire" in config.active_hazards:
        hazard_list.append(
            Hazard(
                "flat_tire",
                flat_tire_alter_status,
                (lambda x, y, z: flat_tire_prob),
                flat_msg,
                message_end="You finally got the flat fixed.",
                duration_min=3.0 + np.random.random() * 3,
                speed_lock=True,
            )
        )

    ############
    # Dead End #
    ############
    def dead_end_alter_status(team):
        team.direction = (team.direction + 180) % 360
        team.status_color = "yellow"
        team.status_text = "Reached a dead end"

    dead_end_prob = config.hazard_config("dead_end_prob")

    if "dead_end" in config.active_hazards:
        hazard_list.append(
            Hazard(
                "dead_end",
                dead_end_alter_status,
                (lambda x, y, z: dead_end_prob),
                "You reached a dead end on this road.",
                message_end="You can now turn off this road.",
                duration_min=1.0 + np.random.random(),
                direction_lock=True,
            )
        )

    ################
    # Flooded Road #
    ################
    def flooded_road_alter_status(team):
        team.direction = (team.direction + 180) % 360
        team.status_color = "yellow"
        team.status_text = "Reached a flooded road"
        team.speed /= 2

    flooded_road_prob = config.hazard_config("flooded_road_prob")

    if "flooded_road" in config.active_hazards:
        hazard_list.append(
            Hazard(
                "flooded_road",
                flooded_road_alter_status,
                (lambda x, y, z: flooded_road_prob),
                "You reached a flooded roadway.",
                message_end="You can now turn off this road.",
                duration_min=1.0 + np.random.random(),
                direction_lock=True,
            )
        )

    #############
    # End chase #
    #############
    def end_chase_alter_status(team):
        team.speed = 0.0
        team.status_color = "red"
        team.status_text = "Chase Ended"

    hazard_list.append(
        Hazard(
            "end_chase",
            end_chase_alter_status,
            (lambda x, y, z: 0.0),
            "...CHASE TERMINATED...",
            duration_min=1000,
            speed_lock=True,
            direction_lock=True,
        )
    )

    return {hazard.type: hazard for hazard in hazard_list}


def shuffle_new_hazard(team, seconds, hazards, config):
    """Given a time interval, use registered hazards to shuffle a chance of a new hazard."""
    # Hazards
    hazard_list = list(hazards.values())
    hazard_probs = [seconds / 60 * hazard.probability(team, config, hazard) for hazard in hazard_list]
    # Non-Hazard (remaining chance)
    hazard_list.append(None)
    hazard_probs.append(max(1.0 - np.sum(hazard_probs), 0.0))
    # Select one randomly
    return np.random.choice(hazard_list, p=hazard_probs)
