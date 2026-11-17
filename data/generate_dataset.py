from pathlib import Path

import numpy as np
import pandas as pd


RANDOM_SEED = 42
RECORD_COUNT = 1_000
SERVICE_TYPES = ["Certificate", "Fee Payment", "General Enquiry", "Admission"]


def main() -> None:
    rng = np.random.default_rng(RANDOM_SEED)

    people_waiting = rng.integers(0, 51, size=RECORD_COUNT)
    active_counters = rng.integers(1, 6, size=RECORD_COUNT)
    avg_service_time = rng.integers(1, 16, size=RECORD_COUNT)

    # Mid-morning and mid-afternoon are busier than opening and closing hours.
    hours = np.arange(9, 19)
    hour_probabilities = np.array([0.06, 0.12, 0.15, 0.13, 0.09, 0.08, 0.13, 0.12, 0.08, 0.04])
    hour = rng.choice(hours, size=RECORD_COUNT, p=hour_probabilities)
    day_of_week = rng.integers(0, 7, size=RECORD_COUNT)
    service_type = rng.choice(SERVICE_TYPES, size=RECORD_COUNT)

    # Model queue workload across counters, then adjust for office demand patterns.
    service_factor = pd.Series(service_type).map(
        {
            "Certificate": 1.05,
            "Fee Payment": 1.15,
            "General Enquiry": 0.7,
            "Admission": 1.25,
        }
    ).to_numpy()
    hour_factor = np.where(np.isin(hour, [10, 11, 12, 15, 16]), 1.2, 1.0)
    day_factor = np.where(day_of_week < 5, 1.0, 0.7)
    expected_wait = (
        people_waiting
        * avg_service_time
        / active_counters
        * service_factor
        * hour_factor
        * day_factor
        * 0.45
    )

    # Add measurement and visitor-to-visitor variation, while keeping waits plausible.
    variation = rng.normal(loc=0, scale=3 + expected_wait * 0.08, size=RECORD_COUNT)
    actual_waiting_time = np.clip(expected_wait + variation, 0, 240).round(1)

    dataset = pd.DataFrame(
        {
            "people_waiting": people_waiting,
            "active_counters": active_counters,
            "avg_service_time": avg_service_time,
            "hour": hour,
            "day_of_week": day_of_week,
            "service_type": service_type,
            "actual_waiting_time": actual_waiting_time,
        }
    )

    output_path = Path(__file__).resolve().with_name("queue_dataset.csv")
    dataset.to_csv(output_path, index=False)

    print(f"Dataset shape: {dataset.shape}")
    print("\nFirst five rows:")
    print(dataset.head())
    print("\nStatistical summary:")
    print(dataset.describe(include="all"))


if __name__ == "__main__":
    main()
