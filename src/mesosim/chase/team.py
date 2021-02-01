# Copyright (c) 2020 MesoSim Developers.
# Distributed under the terms of the Apache 2.0 License.
# SPDX-License-Identifier: Apache-2.0
r"""Team TODO"""

from datetime import datetime
from sqlite3 import dbapi2 as sql

import numpy as np
import pytz
from dateutil import parser

from ..core.timing import arc_time_from_cur, db_time_fmt
from ..core.utils import direction_angle_to_str, money_format, nearest_city
from .actions import Action, Hazard
from .vehicle import Vehicle


class Team:
    """Class for manipulating team status for the chase."""

    status = {}
    active_hazards = []
    previous_active_hazard_tuples = []

    def __init__(self, path, hazard_registry, config):
        """Construct underlying database connection, and set initial state."""
        self.con = sql.connect(path)
        self.cur = self.con.cursor()

        self.cur.execute("SELECT team_setting, team_value FROM team_info")
        self.status = dict(self.cur.fetchall())

        self.cur.execute(
            "SELECT hazard_type, expiry_time, message, message_end, overridden_by, "
            "speed_limit, direction_lock, speed_lock FROM hazard_queue WHERE "
            "status='active'"
        )
        for hazard_tuple in self.cur.fetchall():
            hazard = hazard_registry[hazard_tuple[0]].update_from_tuple(hazard_tuple)
            self.previous_active_hazard_tuples.append(hazard_tuple)
            self.active_hazards.append(hazard)

        self.config = config
        self.vehicle = Vehicle(self.status["vehicle"], config)

    @property
    def can_refuel(self):
        """Determine if this team can refuel."""
        _, _, distance, _ = nearest_city(self.latitude, self.longitude, self.config)
        return (
            (distance is not None and distance <= self.config.min_town_distance_refuel)
            or self.fuel_level <= 0
        )

    @property
    def speed_locked(self):
        """Determine if this team has speed locked by a hazard."""
        return any(active_hazard.speed_lock for active_hazard in self.active_hazards)

    @property
    def direction_locked(self):
        """Determine if this team has direction locked by a hazard."""
        return any(active_hazard.direction_lock for active_hazard in self.active_hazards)

    @property
    def current_max_speed(self):
        """Determine the current maximum speed based on vehicle and hazards."""

        def _find_speed_limit_from_hazard(active_hazard):
            if active_hazard.type == "dirt_road":
                return self.vehicle.top_speed_on_dirt
            elif active_hazard.speed_limit is not None:
                return active_hazard.speed_limit
            else:
                return np.nan

        return np.nanmin(
            [self.vehicle.top_speed]
            + [
                _find_speed_limit_from_hazard(active_hazard)
                for active_hazard in self.active_hazards
            ]
        )

    @property
    def last_update(self):
        """Give the datetime of last update (in current time)."""
        return parser.parse(self.status["last_update"])

    def __getattr__(self, name):
        """Fall back to status.

        Used for
        --------
        latitude
        longitude
        speed
        direction
        fuel_level
        balance
        status_color
        status_text
        """
        return self.status[name]

    def __setattr__(self, name, value):
        """Fall back to status.

        See __getattr__."""
        self.status[name] = value

    def clear_active_hazards(self):
        """Clear all active hazards."""
        self.active_hazards = []
        self.status_color = "green"
        self.status_text = "Chase On"

    def has_action_queue_item(self):
        self.cur.execute("SELECT * FROM action_queue WHERE action_taken IS NULL")
        return len(self.cur.fetchall()) > 0

    def _get_action_queue_generator(self, hazards):
        self.cur.execute("SELECT * FROM action_queue WHERE action_taken IS NULL")
        for action_tuple in self.cur.fetchall():
            if action_tuple[2] == "hazard":
                hazard = hazards[action_tuple[3]]
                hazard.action_id = action_tuple[0]
                yield hazard
            else:
                yield Action(action_tuple=action_tuple)

    def get_action_queue(self, hazard_registry):
        return list(self._get_action_queue_generator(hazard_registry))

    def apply_action(self, action):
        """Apply the action to this team.

        Same thing as action.alter_status(team, config, action).
        """
        action.alter_status(self, self.config, action)

    def dismiss_action(self, action):
        """Dismiss action from the action queue."""
        if action.action_id is not None:
            self.cur.execute(
                "UPDATE action_queue SET action_taken = ? WHERE action_id = ?",
                [datetime.now(tz=pytz.UTC).strftime(db_time_fmt), action.action_id],
            )

    def apply_hazard(self, hazard):
        """Apply the hazard to this team."""
        hazard.alter_status(self, self.config, hazard)
        self.active_hazards.append(hazard)

    def write_status(self):
        """Save the current status of this team in DB."""
        self.status["last_update"] = datetime.now(tz=pytz.UTC).strftime(db_time_fmt)

        # Current team status table
        for key, value in self.status.items():
            self.cur.execute(
                "UPDATE team_info SET team_value = ? WHERE team_setting = ?", [value, key]
            )

        # History table
        self.cur.execute(
            (
                "INSERT INTO team_history (cur_timestamp, arc_timestamp, latitude, "
                "longitude, speed, direction, status_color, status_text, balance, "
                "points, fuel_level) VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?)"
            ),
            (
                [
                    self.status["last_update"],
                    arc_time_from_cur(self.status["last_update"], self.config.timing),
                ]
                + [
                    self.status[key]
                    for key in (
                        "latitude",
                        "longitude",
                        "speed",
                        "direction",
                        "status_color",
                        "status_text",
                        "balance",
                        "points",
                        "fuel_level",
                    )
                ]
            ),
        )

        # Hazards
        for active_hazard in self.active_hazards:
            if active_hazard.type not in set(
                tup[0] for tup in self.previous_active_hazard_tuples
            ):
                # New hazard, so insert
                self.cur.execute(
                    (
                        "INSERT INTO hazard_queue (hazard_type, expiry_time, message, "
                        "message_end, overridden_by, speed_limit, direction_lock, "
                        "speed_lock, status) VALUES (?,?,?,?,?,?,?,?,?)"
                    ),
                    (list(active_hazard.to_hazard_tuple()) + ["active"]),
                )
            # Leave active pre-existing hazards alone
        for previous_active_hazard_tup in self.previous_active_hazard_tuples:
            if previous_active_hazard_tup[0] not in set(
                active_hazard.type for active_hazard in self.active_hazards
            ):
                # Expire removed hazards
                self.cur.execute(
                    "UPDATE hazard_queue SET status='expired' WHERE hazard_type = ?",
                    [previous_active_hazard_tup[0]],
                )

        self.con.commit()

    def output_status_dict(self):
        """Output the dict for JSON to web app."""
        color = {"green": "success", "yellow": "warning", "red": "danger"}[
            self.status["status_color"]
        ]

        city, st, dist, angle = nearest_city(self.lat, self.lon, self.config)
        if city is None:
            location_str = "{lat:.3f}, {lat:.3f} (Middle of Nowhere)".format(
                lat=self.latitude, lon=self.longitude
            )
        else:
            location_str = "{lat:.3f}, {lat:.3f} ({dist:.0f} Mi {ang} {city},{st})".format(
                lat=self.latitude,
                lon=self.longitude,
                dist=dist,
                ang=direction_angle_to_str(angle),
                city=city,
                st=st,
            )

        fuel_percent = self.fuel_level / self.vehicle.fuel_cap * 100
        if fuel_percent > 25:
            fuel_color = "success"
        elif fuel_percent > 5:
            fuel_color = "warning"
        else:
            fuel_color = "danger"

        if self.balance > 100:
            balance_color = "success"
        elif self.balance > 0:
            balance_color = "warning"
        else:
            balance_color = "danger"

        output = {
            "team_id": self.team_id,
            "location": location_str,
            "status_text": self.status_text,
            "status_color": color,
            "fuel_text": (
                "{level:.1f} gallons ({percent:.0f}%) remaining".format(
                    level=self.fuel_level, percent=fuel_percent
                )
            ),
            "fuel_on_empty_fee": self.fuel_level <= 0,
            "fuel_color": fuel_color,
            "can_refuel": self.can_refuel,
            "current_mpg": self.vehicle.calculate_mpg(self.speed),
            "balance": money_format(self.balance),
            "balance_color": balance_color,
            "points": self.points,
            "speed": self.speed,
            "current_max_speed": self.current_max_speed(),
            "direction": self.direction,
            "direction_lock": self.direction_locked,
            "can_move": not self.speed_locked,
        }
        return output
