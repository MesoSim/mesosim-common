# Copyright (c) 2020 MesoSim Developers.
# Distributed under the terms of the Apache 2.0 License.
# SPDX-License-Identifier: Apache-2.0
r"""Vechicle TODO"""


class Vehicle:
    """
    Manage the vehicles!
    """

    # Configuration Variables (Default)
    vehicle_type = None
    print_name = "(None)"
    top_speed = 135  # mph
    top_speed_on_dirt = 45  # mph
    efficient_speed = 60  # mph
    mpg = 38  # mpg
    fuel_cap = 13  # gallons
    stuck_probability = 0.01  # chance per current minute

    def __init__(self, vehicle_type, config):
        self._cursor = config.cur
        data = self._query(
            (
                "SELECT print_name, top_speed, top_speed_on_dirt, "
                "efficient_speed, mpg, fuel_cap, stuck_probability, traction_rating FROM "
                "vehicles WHERE vehicle_type = ?"
            ),
            [vehicle_type],
        )
        if len(data) != 1:
            raise ValueError("Vehicle type" + str(vehicle_type) + " not found.")
        else:
            self.vehicle_type = vehicle_type
            self.print_name = data[0][0]
            self.top_speed = float(data[0][1])
            self.top_speed_on_dirt = float(data[0][2])
            self.efficient_speed = float(data[0][3])
            self.mpg = float(data[0][4])
            self.fuel_cap = float(data[0][5])
            self.stuck_probability = float(data[0][6])
            self.traction_rating = data[0][7]

    def _query(self, *args):
        # Run a DB query on the DB cursor given
        self._cursor.execute(*args)
        return self._cursor.fetchall()

    def calculate_mpg(self, current_speed):
        # Calculate mpg based on current speed and vehicle specs
        if current_speed <= self.efficient_speed:
            multiplier = 1 + (
                (current_speed - self.efficient_speed) ** 4 * (3 / self.efficient_speed ** 4)
            )
        else:
            multiplier = 1 + (
                (current_speed - self.efficient_speed) ** 2
                * (3 / (self.top_speed - self.efficient_speed) ** 2)
            )

        return self.mpg / multiplier
