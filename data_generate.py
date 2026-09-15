import json
import os
import random
import time

LIVE_GAUGE_FILE = "gauge_readings.json"
MASTER_LOG_FILE = "master_flight_log.json"
INTENT_FILE = "intent.json"


def get_current_intent():
    """Reads pilot intent from intent.json if available."""
    if os.path.exists(INTENT_FILE):
        try:
            with open(INTENT_FILE, "r") as f:
                data = json.load(f)
                return data.get("intent", "CRUISE")
        except (json.JSONDecodeError, IOError):
            pass
    return "CRUISE"


def write_values(delay_seconds=1.0):
    clock = 1
    master_log = []
    
    # State tracking for gradual AOA transitions
    current_base_aoa = 3.5  # Baseline cruise AOA in degrees
    standard_cruise_aoa = 3.5

    print("=== SENSOR GENERATOR STARTED ===")
    print("Reading 'intent.json' & generating correlated AOA data...\n")

    try:
        while True:
            # 1. Check pilot command
            intent = get_current_intent()

            # 2. Correlate target AOA gradually based on intent
            if intent == "CLIMB":
                current_base_aoa += 1.0  # +1 degree pitch up
            elif intent == "DESCEND":
                current_base_aoa -= 1.0  # -1 degree pitch down
            else:
                # Smoothly return to standard cruise (3.5°)
                if current_base_aoa < standard_cruise_aoa:
                    current_base_aoa = min(standard_cruise_aoa, current_base_aoa + 0.2)
                elif current_base_aoa > standard_cruise_aoa:
                    current_base_aoa = max(standard_cruise_aoa, current_base_aoa - 0.2)

            # Airspeed correlates inversely with pitch/AOA
            airspeed = round(250.0 - (current_base_aoa - 3.5) * 5.0 + random.uniform(-1.0, 1.0), 1)

            # 3. Apply baseline AOA + minor natural turbulence noise
            aoa_sensors = {
                "aoa_sensor_1": round(current_base_aoa + random.uniform(-0.15, 0.15), 2),
                "aoa_sensor_2": round(current_base_aoa + random.uniform(-0.15, 0.15), 2),
                "aoa_sensor_3": round(current_base_aoa + random.uniform(-0.15, 0.15), 2),
            }

            # 4. 15% Chance of wild single-sensor error spike
            fault_injected = False
            faulty_sensor_id = None
            if random.random() < 0.15:
                faulty_sensor_id = random.choice(["aoa_sensor_1", "aoa_sensor_2", "aoa_sensor_3"])
                # Wild erroneous value
                aoa_sensors[faulty_sensor_id] = round(random.choice([18.5, 25.0, -12.0, 88.8]), 2)
                fault_injected = True

            # Data frame
            current_frame = {
                "clock_cycle": clock,
                "timestamp": time.time(),
                "pilot_intent": intent,
                "airspeed_kts": airspeed,
                "aoa_sensors": aoa_sensors,
                "fault_injected": fault_injected,
                "faulty_sensor": faulty_sensor_id,
            }

            # 5. Write live state file for computers
            with open(LIVE_GAUGE_FILE, "w") as f:
                json.dump(current_frame, f, indent=4)

            # 6. Update master flight log file
            master_log.append(current_frame)
            with open(MASTER_LOG_FILE, "w") as f:
                json.dump(master_log, f, indent=4)

            # Console output log
            status = f"[Cycle {clock}] Intent: {intent:7s} | Base AOA: {current_base_aoa:.1f}° | Sensors: {aoa_sensors}"
            if fault_injected:
                status += f" <-- [ERROR SPIKE on {faulty_sensor_id}]"
            print(status)

            clock += 1
            time.sleep(delay_seconds)

    except KeyboardInterrupt:
        print("\n=== SENSOR GENERATOR STOPPED ===")


if __name__ == "__main__":
    write_values(delay_seconds=1.0)
