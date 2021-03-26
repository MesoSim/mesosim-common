# Copyright (c) 2020 MesoSim Developers.
# Distributed under the terms of the Apache 2.0 License.
# SPDX-License-Identifier: Apache-2.0
r"""Configuration documentation TODO"""

import json
from sqlite3 import dbapi2 as sql

from dateutil import parser


class Config:
    """Base class for application configuration.

    Used for global settings.

    Old Global Settings:
    --------------------
    sim_time
    speedup
    slp_time (approx between radar scans)
    spd_limit
    fill_rate
    stuck_time
    cc_time (chaser convergence start time)
    sunset_time (affects hazard chances)
    dr_chance (dirt road prob)
    cc_chance (chaser convergence chance)
    tire_chance (flat tire chance)
    dead_end_chance
    flood_chance
    extra_all_time (extra time to add to _all placefile)

    New Global Settings:
    --------------------
    speed_factor
    gas_price ($/gallon)
    fill_rate (gallon/sec)
    min_town_distance_search
    min_town_distance_refuel
    min_town_population
    speed_limit
    """

    def __init__(self, path):
        """Construct underlying sqlite connection."""
        self.con = sql.connect(path)
        self.cur = self.con.cursor()

    def get_config_value(self, config_setting):
        self.cur.execute(
            "SELECT config_value FROM config WHERE config_setting = ?", [config_setting]
        )
        return self.cur.fetchall()[0][0]

    @property
    def speed_factor(self):
        return int(self.get_config_value("speed_factor"))

    @property
    def min_town_population(self):
        return int(self.get_config_value("min_town_population"))

    def __getattr__(self, name):
        # Default to float transform
        return float(self.get_config_value(name))

    def hazard_config(self, name):
        # Get the hazard config
        self.cur.execute(
            "SELECT hazard_value FROM hazard_config WHERE hazard_setting = ?", [name]
        )
        return self.cur.fetchall()[0][0]

    @property
    def active_hazards(self):
        # Return list of active hazard IDs
        return list(json.loads(self.hazard_config("active_hazards")))

    @property
    def start_time(self):
        return parser.parse(self.get_config_value("cur_start_time"))

    @property
    def timings(self):
        return dict(
            (key, f(self.get_config_value(key)))
            for key, f in zip(
                ("cur_start_time", "arc_start_time", "speed_factor"),
                (lambda x: x, lambda x: x, float)
            )
        )
