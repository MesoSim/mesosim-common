#!/usr/bin/env python

"""
Base Classes for Chase Applet

These are the base classes to make the chase applet work, regardless of interface.
"""

import pytz
from sqlite3 import dbapi2 as sql
from dateutil import parser
from datetime import datetime, timedelta
from ChaseLib.functions import direction_angle_to_str, money_format, nearest_city


db_time_fmt = '%Y-%m-%dT%H:%M:%S'


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
        self.cur.execute('SELECT config_value FROM config WHERE config_setting = ?',
                         [config_setting])
        return self.cur.fetchall()[0][0]

    @property
    def speed_factor(self):
        return int(self.get_config_value('speed_factor'))

    @property
    def min_town_population(self):
        return int(self.get_config_value('min_town_population'))

    def __getattr__(self, name):
        # Default to float transform
        return float(self.get_config_value(name))

    def hazard_config(self, name):
        # Get the hazard config
        self.cur.execute('SELECT hazard_value FROM hazard_config WHERE hazard_setting = ?',
                         [name])
        return self.cur.fetchall()[0][0]

    @property
    def start_time(self):
        return parser.parse(self.get_config_value('start_time'))


class Team:
    status = {}
    active_hazard = None
    vehicle = None
    config = None

    def __init__(self, path, hazards, config):
        """Construct underlying sqlite connection, and set initial state."""
        self.con = sql.connect(path)
        self.cur = self.con.cursor()

        self.cur.execute('SELECT team_setting, team_value FROM team_info')
        self.status = dict(self.cur.fetchall())

        if str(self.status['active_hazard']).lower() not in ['', 'none', 'false']:
            self.active_hazard = hazards[self.status['active_hazard']]
            self.active_hazard.expiry_time = parser.parse(self.status['hazard_exp_time'])

        self.config = config
        self.vehicle = Vehicle(self.status['vehicle'], config)

    @property
    def cannot_refuel(self):
        """Determine if the current team cannot refuel."""
        # Get distance to nearst city
        _, _, distance, _ = nearest_city(self.lat, self.lon, self.config)
        return (distance is None or distance > self.config.min_town_distance_refuel)

    @property
    def stopped(self):
        """Determine if the current team is stopped."""
        return False or (self.active_hazard is not None and self.active_hazard.speed_lock)

    def current_max_speed(self):
        """Determine the current maximum speed."""
        if self.active_hazard is not None:
            if self.active_hazard.type == 'dirt_road':
                return self.vehicle.top_speed_on_dirt
            elif self.active_hazard.speed_limit is not None:
                return self.active_hazard.speed_limit
        else:
            return self.vehicle.top_speed

    @property
    def last_update_time(self):
        """Give the datetime of last update (in current time)."""
        return parser.parse(self.status['timestamp'])

    @property
    def lat(self):
        """Get the latitude."""
        return self.status['latitude']

    @lat.setter
    def lat(self, value):
        """Set the latitude."""
        self.status['latitude'] = value

    @property
    def lon(self):
        """Get the longitude."""
        return self.status['longitude']

    @lon.setter
    def lon(self, value):
        """Set the longitude."""
        self.status['longitude'] = value

    @property
    def speed(self):
        """Get the speed."""
        return self.status['speed']

    @speed.setter
    def speed(self, value):
        """Set the speed."""
        self.status['speed'] = value

    @property
    def direction(self):
        """Get the direction."""
        return self.status['direction']

    @direction.setter
    def direction(self, value):
        """Set the direction."""
        self.status['direction'] = value

    @property
    def fuel_level(self):
        """Get the fuel_level."""
        return self.status['fuel_level']

    @fuel_level.setter
    def fuel_level(self, value):
        """Set the fuel_level."""
        self.status['fuel_level'] = value

    @property
    def balance(self):
        """Get the balance."""
        return self.status['balance']

    @balance.setter
    def balance(self, value):
        """Set the balance."""
        self.status['balance'] = value

    def clear_active_hazard(self):
        """Clear the active hazard."""
        self.active_hazard = None
        self.status['active_hazard'] = ''
        self.status['status_color'] = 'green'
        self.status['status_text'] = 'Chase On'

    def has_action_queue_item(self):
        self.cur.execute('SELECT * FROM action_queue WHERE action_taken IS NULL')
        return (len(self.cur.fetchall()) > 0)

    def get_action_queue(self, hazards):
        self.cur.execute('SELECT * FROM action_queue WHERE action_taken IS NULL')
        for action_tuple in self.cur.fetchall():
            if action_tuple[2] == 'hazard':
                hazard = hazards[action_tuple[3]]
                hazard.action_id = action_tuple[0]
                yield hazard
            else:
                yield Action(action_tuple=action_tuple)

    def apply_action(self, action):
        """Apply the action to this team."""
        self.status = action.alter_status(self.status)

    def dismiss_action(self, action):
        """Dismiss action from the action queue."""
        if action.action_id is not None:
            self.cur.execute('UPDATE action_queue SET action_taken = ? WHERE action_id = ?',
                             [datetime.now(tz=pytz.UTC).strftime(db_time_fmt),
                              action.action_id])

    def apply_hazard(self, hazard):
        """Apply the hazard to this team."""
        self.status = hazard.alter_status(self.status)
        self.active_hazard = hazard

    def write_status(self):
        """Save the current status of this team in DB."""
        if self.active_hazard is None:
            self.status['active_hazard'] = ''
            self.status['hazard_exp_time'] = ''
        else:
            self.status['active_hazard'] = self.active_hazard.type
            self.status['hazard_exp_time'] = (
                self.active_hazard.expiry_time.strftime(db_time_fmt))

        self.status['timestamp'] = datetime.now(tz=pytz.UTC).strftime(db_time_fmt)

        for key, value in self.status.items():
            self.cur.execute('UPDATE team_info SET team_value = ? WHERE team_setting = ?',
                             [value, key])

        self.cur.execute(('INSERT INTO team_history (timestamp, latitude, longitude, '
                          'speed, direction, status_color, status_text, balance, '
                          'points, fuel_level, active_hazard) VALUES '
                          '(?,?,?,?,?,?,?,?,?,?,?)'),
                         [self.status[key] for key in ('timestamp', 'latitude',
                                                       'longitude', 'speed',
                                                       'direction', 'status_color',
                                                       'status_text', 'balance',
                                                       'points', 'fuel_level',
                                                       'active_hazard')])
        self.con.commit()

    def output_status_dict(self):
        """Output the dict for JSON to web app."""
        color = {'green': 'success', 'yellow': 'warning', 'red': 'danger'}[
            self.status['status_color']]
        direction_lock = False or (self.active_hazard is not None and
                                   self.active_hazard.direction_lock)
        speed_lock = False or (self.active_hazard is not None and
                               self.active_hazard.speed_lock)

        city, st, dist, angle = nearest_city(self.lat, self.lon, self.config)
        if city is None:
            location_str = '{lat:.3f}, {lat:.3f} (Middle of Nowhere)'.format(lat=self.lat,
                                                                             lon=self.lon)
        else:
            location_str = ('{lat:.3f}, {lat:.3f} ({dist:.0f} Mi {ang} {city},{st})'.format(
                            lat=self.lat, lon=self.lon, dist=dist,
                            ang=direction_angle_to_str(angle), city=city, st=st))

        fuel_percent = self.fuel_level / self.vehicle.fuel_cap * 100
        if fuel_percent > 25:
            fuel_color = 'success'
        elif fuel_percent > 5:
            fuel_color = 'warning'
        else:
            fuel_color = 'danger'

        if self.balance > 100:
            balance_color = 'success'
        elif self.balance > 0:
            balance_color = 'warning'
        else:
            balance_color = 'danger'

        output = {
            'team_id': self.status['team_id'],
            'location': location_str,
            'status_text': self.status['status_text'],
            'status_color': color,
            'fuel_text': ('{level:.1f} gallons ({percent:.0f}%) remaining'.format(
                          level=self.fuel_level, percent=fuel_percent)),
            'fuel_color': fuel_color,
            'can_refuel': not self.cannot_refuel,
            'balance': money_format(self.balance),
            'balance_color': balance_color,
            'points': self.status['points'],
            'speed': self.speed,
            'current_max_speed': self.current_max_speed(),
            'direction': self.direction,
            'direction_lock': direction_lock,
            'can_move': not speed_lock
        }
        return output


class Vehicle:
    """
    Manage the vehicles!
    """

    # Configuration Variables (Default)
    vehicle_type = None
    print_name = '(None)'
    top_speed = 135  # mph
    top_speed_on_dirt = 45  # mph
    efficient_speed = 60  # mph
    mpg = 38  # mpg
    fuel_cap = 13  # gallons
    stuck_probability = 0.01  # chance per current minute

    def __init__(self, vehicle_type, config):
        self._cursor = config.cur
        data = self._query(('SELECT print_name, top_speed, top_speed_on_dirt, '
                            'efficient_speed, mpg, fuel_cap, stuck_probability FROM'
                            'vehicles WHERE vehicle_type = ?'), [vehicle_type])
        if len(data) != 1:
            raise ValueError('Vehicle type' + str(vehicle_type) + ' not found.')
        else:
            self.vehicle_type = vehicle_type
            self.print_name = data[0][0]
            self.top_speed = float(data[0][1])
            self.top_speed_on_dirt = float(data[0][2])
            self.efficient_speed = float(data[0][3])
            self.mpg = float(data[0][4])
            self.fuel_cap = float(data[0][5])
            self.stuck_probability = float(data[0][6])

    def _query(self, *args):
        # Run a DB query on the DB cursor given
        self._cursor.execute(*args)
        return self._cursor.fetchall()

    def calculate_mpg(self, current_speed):
        # Calculate mpg based on current speed and vehicle specs
        if current_speed <= self.efficient_speed:
            multiplier = 1 + ((current_speed - self.efficient_speed)**4 *
                              (3 / self.efficient_speed**4))
        else:
            multiplier = 1 + ((current_speed - self.efficient_speed)**2 *
                              (3 / (self.top_speed - self.efficient_speed)**2))

        return self.mpg / multiplier


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
    message = ''

    def __init__(self, action_tuple):
        # Initialize given action_tuple=(id, message, type, amount, _)
        self.action_id = action_tuple[0]
        self.message = action_tuple[1]
        if '_' in action_tuple[2]:
            self.action_type, self.action_field = action_tuple[2].split('_', 1)
        else:
            self.action_type = action_tuple[2]
        self.action_amount = action_tuple[3]

        if self.action_type in ['set', 'change']:
            self.is_adjustment = True

    def generate_message(self):
        """Generate the message."""
        return datetime.now(tz=pytz.UTC).strftime('%H%MZ') + ': ' + self.message

    def alter_status(self, status):
        """Alter status if needed by action_type."""
        if self.is_adjustment:
            # only adjust if this action is an adjustment
            if self.action_type == 'set':
                status[self.action_field] = self.action_amount
            elif self.action_type == 'change':
                status[self.action_field] = (float(status[self.action_field]) +
                                             float(self.action_amount))
        return status


class Hazard(Action):
    """
    Hazards! Real stuff is going down here.
    """
    is_adjustment = False
    is_hazard = True
    action_type = 'hazard'
    expiry_time = None
    overridden_by_list = []
    message_end = None
    speed_limit = None
    direction_lock = False
    speed_lock = False

    def __init__(self, hazard_type, alter_status, probability, message, message_end=None,
                 duration_min=None, overridden_by_list=['end_chase'], speed_limit=None,
                 direction_lock=False, speed_lock=False):
        self.type = hazard_type  # string
        self.alter_status = alter_status  # function(status)
        self.probability = probability  # function(status)
        self.message = message  # string
        self.message_end = message_end
        self.expiry_time = datetime.now(tz=pytz.UTC) + timedelta(minutes=duration_min)
        self.overridden_by_list = overridden_by_list
        self.speed_limit = speed_limit
        self.direction_lock = direction_lock
        self.speed_lock = speed_lock

    def generate_expiry_message(self):
        """Generate the expiry message."""
        if self.message_end is not None:
            return datetime.now(tz=pytz.UTC).strftime('%H%MZ') + ': ' + self.message_end
        else:
            return ''

    def overridden_by(self, other_hazard):
        """Check if this hazard is overridden by the other hazard type."""
        return (other_hazard.type in self.overridden_by_list)
