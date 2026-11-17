import math
from numbers import Real
from pathlib import Path

import joblib
import pandas as pd


MODEL_PATH = Path(__file__).resolve().with_name("saved_model.pkl")
FEATURE_COLUMNS = [
    "people_waiting",
    "active_counters",
    "avg_service_time",
    "hour",
    "day_of_week",
    "service_type",
]
VALID_SERVICE_TYPES = {
    "Certificate",
    "Fee Payment",
    "General Enquiry",
    "Admission",
}


def _validate_integer(name: str, value: int, minimum: int, maximum: int | None = None) -> None:
    """Raise a clear error unless a value is a finite integer within the allowed range."""
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(float(value))
        or int(value) != value
    ):
        raise ValueError(f"{name} must be an integer.")
    if value < minimum or (maximum is not None and value > maximum):
        bounds = f"at least {minimum}" if maximum is None else f"between {minimum} and {maximum}"
        raise ValueError(f"{name} must be {bounds}; received {value}.")


def predict_waiting_time(
    people_waiting: int,
    active_counters: int,
    avg_service_time: int,
    hour: int,
    day_of_week: int,
    service_type: str,
) -> float:
    """Predict queue waiting time in minutes using the saved preprocessing/model pipeline.

    Args:
        people_waiting: Number of people currently waiting (0 or more).
        active_counters: Active counter count (1 through 5).
        avg_service_time: Average service duration in minutes (1 through 15).
        hour: Hour of day (9 through 18).
        day_of_week: Day index, where 0 is Monday and 6 is Sunday.
        service_type: One of the supported college office service categories.

    Returns:
        Predicted waiting time in minutes, rounded to two decimal places.

    Raises:
        ValueError: If any input is outside its allowed range or category.
        FileNotFoundError: If the trained model pipeline has not been saved.
    """
    _validate_integer("people_waiting", people_waiting, minimum=0, maximum=50)
    _validate_integer("active_counters", active_counters, minimum=1, maximum=5)
    _validate_integer("avg_service_time", avg_service_time, minimum=1, maximum=15)
    _validate_integer("hour", hour, minimum=9, maximum=18)
    _validate_integer("day_of_week", day_of_week, minimum=0, maximum=6)
    if service_type not in VALID_SERVICE_TYPES:
        choices = ", ".join(sorted(VALID_SERVICE_TYPES))
        raise ValueError(f"service_type must be one of: {choices}; received {service_type!r}.")

    if not MODEL_PATH.is_file():
        raise FileNotFoundError(
            f"Trained model pipeline not found at {MODEL_PATH}. "
            "Run models/train_model.py before requesting predictions."
        )

    # Keep column names and order aligned with the training feature matrix.
    features = pd.DataFrame(
        [
            {
                "people_waiting": people_waiting,
                "active_counters": active_counters,
                "avg_service_time": avg_service_time,
                "hour": hour,
                "day_of_week": day_of_week,
                "service_type": service_type,
            }
        ],
        columns=FEATURE_COLUMNS,
    )
    model = joblib.load(MODEL_PATH)
    prediction = model.predict(features)
    return round(float(prediction[0]), 2)


if __name__ == "__main__":
    # Example scenarios for a quick manual smoke test.
    examples = [
        {
            "people_waiting": 10,
            "active_counters": 2,
            "avg_service_time": 5,
            "hour": 11,
            "day_of_week": 2,
            "service_type": "Admission",
        },
        {
            "people_waiting": 25,
            "active_counters": 3,
            "avg_service_time": 7,
            "hour": 14,
            "day_of_week": 3,
            "service_type": "Fee Payment",
        },
        {
            "people_waiting": 40,
            "active_counters": 1,
            "avg_service_time": 10,
            "hour": 10,
            "day_of_week": 4,
            "service_type": "Certificate",
        },
    ]

    for index, scenario in enumerate(examples, start=1):
        waiting_time = predict_waiting_time(**scenario)
        print(f"Scenario {index}: predicted waiting time = {waiting_time:.2f} minutes")