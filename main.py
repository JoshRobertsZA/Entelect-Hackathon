import json
import math
from enum import Enum

# ── Enums ──────────────────────────────────────────────────────────

class SegmentType(Enum):
    STRAIGHT = "straight"
    CORNER = "corner"

class TyreCompound(Enum):
    SOFT = "Soft"
    MEDIUM = "Medium"
    HARD = "Hard"
    INTERMEDIATE = "Intermediate"
    WET = "Wet"

class WeatherType(Enum):
    DRY = "dry"
    COLD = "cold"
    LIGHT_RAIN = "light_rain"
    HEAVY_RAIN = "heavy_rain"

# ── Models ──────────────────────────────────────────────────────────

class Car:
    def __init__(self, data):
        self.max_speed = data["max_speed_m/s"]
        self.accel = data["accel_m/se2"]
        self.brake = data["brake_m/se2"]
        self.limp_speed = data["limp_constant_m/s"]
        self.crawl_speed = data["crawl_constant_m/s"]
        self.fuel_tank_capacity = data["fuel_tank_capacity_l"]
        self.initial_fuel = data["initial_fuel_l"]

class Race:
    def __init__(self, data):
        self.name = data["name"]
        self.laps = data["laps"]
        self.base_pit_stop_time = data["base_pit_stop_time_s"]
        self.pit_tyre_swap_time = data["pit_tyre_swap_time_s"]
        self.pit_refuel_rate = data["pit_refuel_rate_l/s"]
        self.corner_crash_penalty = data["corner_crash_penalty_s"]
        self.pit_exit_speed = data["pit_exit_speed_m/s"]
        self.fuel_soft_cap_limit = data["fuel_soft_cap_limit_l"]
        self.starting_weather_condition_id = data["starting_weather_condition_id"]
        self.time_reference = data["time_reference_s"]

class Segment:
    def __init__(self, data):
        self.id = data["id"]
        self.type = SegmentType(data["type"])
        self.length = data["length_m"]
        self.radius = data.get("radius_m", None)

class Tyre:
    def __init__(self, compound, props):
        self.compound = TyreCompound(compound)
        self.life_span = props["life_span"]
        self.friction_multipliers = {
            WeatherType.DRY: props["dry_friction_multiplier"],
            WeatherType.COLD: props["cold_friction_multiplier"],
            WeatherType.LIGHT_RAIN: props["light_rain_friction_multiplier"],
            WeatherType.HEAVY_RAIN: props["heavy_rain_friction_multiplier"],
        }
        self.degradation_rates = {
            WeatherType.DRY: props["dry_degradation"],
            WeatherType.COLD: props["cold_degradation"],
            WeatherType.LIGHT_RAIN: props["light_rain_degradation"],
            WeatherType.HEAVY_RAIN: props["heavy_rain_degradation"],
        }

class TyreSet:
    def __init__(self, ids, compound):
        self.ids = ids
        self.compound = TyreCompound(compound)

class WeatherCondition:
    def __init__(self, data):
        self.id = data["id"]
        self.condition = WeatherType(data["condition"])
        self.duration = data["duration_s"]
        self.acceleration_multiplier = data["acceleration_multiplier"]
        self.deceleration_multiplier = data["deceleration_multiplier"]

# ── Parser ──────────────────────────────────────────────────────────

def parse_json(filepath):
    with open(filepath) as f:
        data = json.load(f)

    car = Car(data["car"])
    race = Race(data["race"])
    segments = [Segment(s) for s in data["track"]["segments"]]
    tyres = {TyreCompound(k): Tyre(k, v) for k, v in data["tyres"]["properties"].items()}
    available_sets = [TyreSet(s["ids"], s["compound"]) for s in data["available_sets"]]
    weather = [WeatherCondition(w) for w in data["weather"]["conditions"]]

    return car, race, segments, tyres, available_sets, weather

GRAVITY = 9.81  # m/s^2

# ── Main ──────────────────────────────────────────────────────────

def main():
    car, race, segments, tyres, available_sets, weather = parse_json("1.txt")


def calculate_best_tire_set(available_sets, weather):
    best_set = None
    best_multiplier = 0
    best_friction = -1

    for tyre_set in available_sets:
        tyre = tyres[tyre_set.compound]
        multiplier = 0
        friction = 0

        for condition in weather:
            multiplier += tyre.degradation_rates[condition.condition] * condition.duration
            friction += tyre.friction_multipliers[condition.condition] * condition.duration

        if multiplier > best_multiplier or (multiplier == best_multiplier and friction > best_friction):
            best_multiplier = multiplier
            best_friction = friction
            best_set = tyre_set

    return best_set

def calculate_max_corner_speed(car, segment, tyre, weather_condition):
    tyre_friction = tyre.friction_multipliers[weather_condition.condition]
    segment_radius = segment.radius
    crawl_speed = car.crawl_speed

    max_corner_speed = math.sqrt(tyre_friction * GRAVITY * segment_radius) + crawl_speed
    return max_corner_speed

def calculate_braking_distance(car, initial_speed, weather_condition):
    deceleration = car.brake * weather_condition.deceleration_multiplier
    if deceleration <= 0:
        return float('inf')  # Cannot brake

    braking_distance = (car.max_speed ** 2 - initial_speed ** 2) / (2 * deceleration)
    return braking_distance

def calculate_acceleration_speed(car, initial_speed, braking_distance, segment, weather_condition):
    acceleration = car.accel * weather_condition.acceleration_multiplier
    if acceleration <= 0:
        return initial_speed  # Cannot accelerate

    time_to_max_speed = (car.max_speed - initial_speed) / acceleration
    final_speed = min(car.max_speed, initial_speed + acceleration * time_to_max_speed)
    return final_speed

if __name__ == "__main__":
    main()