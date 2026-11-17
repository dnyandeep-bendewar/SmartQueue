from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.tree import DecisionTreeRegressor


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "data" / "queue_dataset.csv"
MODEL_PATH = Path(__file__).resolve().with_name("saved_model.pkl")
RESULTS_PATH = Path(__file__).resolve().with_name("model_results.csv")
ACTUAL_PREDICTED_PLOT = Path(__file__).resolve().with_name("actual_vs_predicted.png")
RESIDUALS_PLOT = Path(__file__).resolve().with_name("residuals.png")

NUMERIC_FEATURES = [
    "people_waiting",
    "active_counters",
    "avg_service_time",
    "hour",
    "day_of_week",
]
CATEGORICAL_FEATURES = ["service_type"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET = "actual_waiting_time"
VALID_RANGES = {
    "people_waiting": (0, 50),
    "active_counters": (1, 5),
    "avg_service_time": (1, 15),
    "hour": (9, 18),
    "day_of_week": (0, 6),
    TARGET: (0, 240),
}
VALID_SERVICE_TYPES = {
    "Certificate",
    "Fee Payment",
    "General Enquiry",
    "Admission",
}


def validate_dataset(dataset: pd.DataFrame) -> None:
    """Report input quality and stop if values cannot safely train the models."""
    required_columns = FEATURES + [TARGET]
    missing_columns = [column for column in required_columns if column not in dataset.columns]
    extra_columns = [column for column in dataset.columns if column not in required_columns]
    if missing_columns:
        raise ValueError(f"Dataset is missing required columns: {missing_columns}")
    if extra_columns:
        print(f"Unexpected columns (not used for training): {extra_columns}")

    missing_values = dataset[required_columns].isna().sum()
    print("\nMissing values:")
    print(missing_values.to_string())
    missing_total = int(missing_values.sum())

    duplicate_count = int(dataset.duplicated().sum())
    print(f"\nDuplicate records: {duplicate_count}")
    if duplicate_count:
        print("Duplicate records are retained and reported; none are silently removed.")

    capped_count = int(dataset[TARGET].eq(240).sum())
    print(f"Records with {TARGET} equal to 240 minutes: {capped_count}")
    if capped_count:
        print("These capped records are retained without alteration.")

    invalid_reasons: list[str] = []
    if missing_total:
        invalid_reasons.append(f"{missing_total} missing required values")

    non_numeric = [
        column
        for column in NUMERIC_FEATURES + [TARGET]
        if not pd.api.types.is_numeric_dtype(dataset[column])
    ]
    if non_numeric:
        invalid_reasons.append(f"non-numeric values/types in numeric columns: {non_numeric}")
    else:
        non_finite_counts = {
            column: int((~np.isfinite(dataset[column])).sum())
            for column in NUMERIC_FEATURES + [TARGET]
            if not np.isfinite(dataset[column]).all()
        }
        if non_finite_counts:
            invalid_reasons.append(f"non-finite numeric values: {non_finite_counts}")

        for column, (minimum, maximum) in VALID_RANGES.items():
            invalid_count = int((~dataset[column].between(minimum, maximum)).sum())
            if invalid_count:
                invalid_reasons.append(
                    f"{invalid_count} values in {column!r} outside [{minimum}, {maximum}]"
                )

    unexpected_services = sorted(
        set(dataset["service_type"].unique()) - VALID_SERVICE_TYPES
    )
    if unexpected_services:
        invalid_reasons.append(f"unexpected service_type values: {unexpected_services}")

    if invalid_reasons:
        for reason in invalid_reasons:
            print(f"DATA ISSUE: {reason}")
        raise ValueError("Dataset validation failed; no models or output artifacts were created.")


def build_pipeline(regressor: object) -> Pipeline:
    """Create preprocessing and regression as one leakage-safe pipeline."""
    preprocessing = ColumnTransformer(
        transformers=[
            ("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ],
        remainder="passthrough",
    )
    return Pipeline(
        steps=[
            ("preprocessor", preprocessing),
            ("regressor", regressor),
        ]
    )


def evaluate_model(
    model_name: str,
    model: Pipeline,
    x_test: pd.DataFrame,
    y_test: pd.Series,
) -> tuple[dict[str, float | str], np.ndarray]:
    """Compute regression metrics and predictions for the untouched test split."""
    predictions = model.predict(x_test)
    mse = mean_squared_error(y_test, predictions)
    result: dict[str, float | str] = {
        "model": model_name,
        "MAE": mean_absolute_error(y_test, predictions),
        "MSE": mse,
        "RMSE": np.sqrt(mse),
        "R2": r2_score(y_test, predictions),
    }
    return result, predictions


def save_evaluation_plots(
    y_test: pd.Series,
    predictions_by_model: dict[str, np.ndarray],
) -> None:
    """Save holdout actual-vs-predicted and residual diagnostic plots."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, (model_name, predictions) in zip(axes, predictions_by_model.items()):
        ax.scatter(y_test, predictions, alpha=0.65, edgecolors="none")
        lower = min(float(y_test.min()), float(predictions.min()))
        upper = max(float(y_test.max()), float(predictions.max()))
        ax.plot([lower, upper], [lower, upper], color="red", linestyle="--", label="Ideal prediction")
        ax.set(
            title=f"{model_name}: Actual vs Predicted",
            xlabel="Actual waiting time (minutes)",
            ylabel="Predicted waiting time (minutes)",
        )
        ax.legend()
    fig.tight_layout()
    fig.savefig(ACTUAL_PREDICTED_PLOT, dpi=150, bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, (model_name, predictions) in zip(axes, predictions_by_model.items()):
        residuals = y_test.to_numpy() - predictions
        ax.scatter(predictions, residuals, alpha=0.65, edgecolors="none")
        ax.axhline(0, color="red", linestyle="--")
        ax.set(
            title=f"{model_name}: Residuals",
            xlabel="Predicted waiting time (minutes)",
            ylabel="Residual (actual - predicted, minutes)",
        )
    fig.tight_layout()
    fig.savefig(RESIDUALS_PLOT, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    if not DATASET_PATH.is_file():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    dataset = pd.read_csv(DATASET_PATH)
    print(f"Loaded dataset: {DATASET_PATH}")
    print(f"Dataset shape: {dataset.shape}")
    validate_dataset(dataset)

    # Keep feature selection explicit and use the same named columns at prediction time.
    x = dataset[FEATURES]
    y = dataset[TARGET]
    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.2,
        random_state=42,
    )
    print(f"\nTraining records: {len(x_train)}; testing records: {len(x_test)}")

    # The encoder is fitted only by Pipeline.fit on the training partition.
    models = {
        "Linear Regression": build_pipeline(LinearRegression()),
        "Decision Tree (max_depth=5)": build_pipeline(
            DecisionTreeRegressor(max_depth=5, random_state=42)
        ),
    }
    results: list[dict[str, float | str]] = []
    predictions_by_model: dict[str, np.ndarray] = {}
    for model_name, model in models.items():
        model.fit(x_train, y_train)
        result, predictions = evaluate_model(model_name, model, x_test, y_test)
        results.append(result)
        predictions_by_model[model_name] = predictions

    results_frame = pd.DataFrame(results)
    # MAE is the primary criterion; R² breaks an exact MAE tie.
    best_index = min(
        range(len(results)),
        key=lambda index: (float(results[index]["MAE"]), -float(results[index]["R2"])),
    )
    selected_name = str(results[best_index]["model"])
    results_frame["selected"] = results_frame["model"].eq(selected_name)

    print("\nTest-set model comparison:")
    print(results_frame.to_string(index=False, float_format=lambda value: f"{value:.4f}"))
    print(f"\nSelected model (lowest test MAE; R² used as tie-breaker): {selected_name}")

    save_evaluation_plots(y_test, predictions_by_model)
    results_frame.to_csv(RESULTS_PATH, index=False)
    joblib.dump(models[selected_name], MODEL_PATH)

    print(f"\nSaved selected preprocessing/model pipeline: {MODEL_PATH}")
    print(f"Saved evaluation results: {RESULTS_PATH}")
    print(f"Saved actual-vs-predicted plot: {ACTUAL_PREDICTED_PLOT}")
    print(f"Saved residual plot: {RESIDUALS_PLOT}")
    print("Training and evaluation completed successfully.")


if __name__ == "__main__":
    main()