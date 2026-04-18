import json
import math
from enum import Enum

# ── Constants ──────────────────────────────────────────────────────
GRAVITY = 9.81

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

# ── Helpers ─────────────────────────────────────────────────────────

def get_next_corner(segments, start_index):
    for j in range(start_index + 1, len(segments)):
        if segments[j].type == SegmentType.CORNER:
            return segments[j]
    return None

# ── Physics Functions ──────────────────────────────────────────────

def calculate_best_tyre_set(available_sets, tyres, weather_condition):
    best_set = None
    best_friction = -1.0

    for tyre_set in available_sets:
        tyre = tyres[tyre_set.compound]
        friction = tyre.friction_multipliers[weather_condition.condition]
        if friction > best_friction:
            best_friction = friction
            best_set = tyre_set

    return best_set

def calculate_tyre_friction(tyre, weather_condition, total_degradation=0.0):
    multiplier = tyre.friction_multipliers[weather_condition.condition]
    return max(0.0, tyre.life_span - total_degradation) * multiplier

def calculate_max_corner_speed(
    car,
    segment,
    tyre,
    weather_condition,
    total_degradation=0.0,
    safety_factor=0.92
):
    if segment.radius is None or segment.radius <= 0:
        return car.crawl_speed

    tyre_friction = calculate_tyre_friction(tyre, weather_condition, total_degradation)
    raw_corner_speed = math.sqrt(max(0.0, tyre_friction * GRAVITY * segment.radius))
    safe_corner_speed = (raw_corner_speed * safety_factor) + car.crawl_speed
    return min(safe_corner_speed, car.max_speed)

def calculate_braking_distance(car, initial_speed, final_speed, weather_condition):
    deceleration = car.brake * weather_condition.deceleration_multiplier
    if deceleration <= 0:
        return float("inf")
    braking_distance = (initial_speed ** 2 - final_speed ** 2) / (2 * deceleration)
    return max(braking_distance, 0.0)

def calculate_acceleration_distance(car, initial_speed, target_speed, weather_condition):
    acceleration = car.accel * weather_condition.acceleration_multiplier
    if acceleration <= 0:
        return float("inf")
    target_speed = min(target_speed, car.max_speed)
    if initial_speed >= target_speed:
        return 0.0
    return (target_speed ** 2 - initial_speed ** 2) / (2 * acceleration)

def calculate_straight_target_speed(car, segment, next_corner_speed, weather_condition, entry_speed):
    """
    Work out the best reachable speed on the straight while still braking
    to the next corner speed.
    """
    accel = car.accel * weather_condition.acceleration_multiplier
    brake = car.brake * weather_condition.deceleration_multiplier

    if accel <= 0 or brake <= 0:
        return round(min(entry_speed, car.max_speed), 2), 0.0

    # Can we hit max speed and still brake in time?
    accel_to_max = calculate_acceleration_distance(car, entry_speed, car.max_speed, weather_condition)
    brake_from_max = calculate_braking_distance(car, car.max_speed, next_corner_speed, weather_condition)

    if accel_to_max + brake_from_max <= segment.length:
        target_speed = car.max_speed
        brake_start = brake_from_max
        return round(target_speed, 2), round(brake_start, 2)

    # Otherwise solve for reachable peak speed using the straight length
    denom = (1.0 / (2.0 * accel)) + (1.0 / (2.0 * brake))
    rhs = (
        segment.length
        + (entry_speed ** 2) / (2.0 * accel)
        + (next_corner_speed ** 2) / (2.0 * brake)
    )
    v_peak_sq = rhs / denom
    target_speed = min(math.sqrt(max(v_peak_sq, 0.0)), car.max_speed)
    brake_start = calculate_braking_distance(car, target_speed, next_corner_speed, weather_condition)

    return round(target_speed, 2), round(brake_start, 2)

# ── Strategy ──────────────────────────────────────────────────────

def build_lap_segments(
    car,
    segments,
    tyre,
    weather_condition,
    lap_num,
    entry_speed=0.0,
    total_degradation=0.0,
    safety_factor=0.92
):
    result = []
    current_speed = entry_speed

    # Known dangerous corners from your sim output
    dangerous_corner_speed_scale = {
        5: 0.88,
        11: 0.85,
        13: 0.85,
    }

    for i, segment in enumerate(segments):
        if segment.type == SegmentType.STRAIGHT:
            next_corner = get_next_corner(segments, i)

            if next_corner is not None:
                next_corner_speed = calculate_max_corner_speed(
                    car,
                    next_corner,
                    tyre,
                    weather_condition,
                    total_degradation,
                    safety_factor
                )

                if next_corner.id in dangerous_corner_speed_scale:
                    next_corner_speed *= dangerous_corner_speed_scale[next_corner.id]
            else:
                next_corner_speed = car.max_speed

            target_speed, brake_start = calculate_straight_target_speed(
                car=car,
                segment=segment,
                next_corner_speed=next_corner_speed,
                weather_condition=weather_condition,
                entry_speed=current_speed
            )

            result.append({
                "id": segment.id,
                "type": "straight",
                "target_m/s": round(target_speed, 2),
                "brake_start_m_before_next": round(brake_start, 2)
            })

            current_speed = next_corner_speed

        else:
            current_speed = calculate_max_corner_speed(
                car,
                segment,
                tyre,
                weather_condition,
                total_degradation,
                safety_factor
            )

            result.append({
                "id": segment.id,
                "type": "corner"
            })

    return result

# ── Output ────────────────────────────────────────────────────────

def build_output(race, segments, tyre_set, car, tyres, available_sets, weather):
    weather_condition = weather[0]
    tyre = tyres[tyre_set.compound]

    laps = []
    for lap_num in range(1, race.laps + 1):
        if lap_num == 1:
            lap_segments = build_lap_segments(
                car,
                segments,
                tyre,
                weather_condition,
                lap_num=1,
                entry_speed=0.0,
                total_degradation=0.0,
                safety_factor=0.92
            )
        else:
            lap_segments = [s.copy() for s in laps[0]["segments"]]

        laps.append({
            "lap": lap_num,
            "segments": lap_segments,
            "pit": {"enter": False}
        })

    return {
        "initial_tyre_id": tyre_set.ids[0],
        "laps": laps
    }

# ── Main ──────────────────────────────────────────────────────────

def main():
    car, race, segments, tyres, available_sets, weather = parse_json("1.txt")

    weather_condition = weather[0]
    best_tyre_set = calculate_best_tyre_set(available_sets, tyres, weather_condition)

    output = build_output(race, segments, best_tyre_set, car, tyres, available_sets, weather)

    with open("output.txt", "w") as f:
        json.dump(output, f, indent=2)

    print(f"Done! Tyre: {best_tyre_set.compound.value}, Laps: {race.laps}")
    print("Output written to output.txt")


if __name__ == "__main__":
    main()