from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


DATASET_PATH = Path(__file__).resolve().with_name("queue_dataset.csv")
PLOTS_DIR = Path(__file__).resolve().with_name("eda_plots")

REQUIRED_COLUMNS = [
    "people_waiting",
    "active_counters",
    "avg_service_time",
    "hour",
    "day_of_week",
    "service_type",
    "actual_waiting_time",
]
NUMERIC_COLUMNS = [
    "people_waiting",
    "active_counters",
    "avg_service_time",
    "hour",
    "day_of_week",
    "actual_waiting_time",
]
VALID_RANGES = {
    "people_waiting": (0, 50),
    "active_counters": (1, 5),
    "avg_service_time": (1, 15),
    "hour": (9, 18),
    "day_of_week": (0, 6),
    "actual_waiting_time": (0, 240),
}
VALID_SERVICE_TYPES = {
    "Certificate",
    "Fee Payment",
    "General Enquiry",
    "Admission",
}


def save_plot(fig: plt.Figure, filename: str) -> None:
    """Save a figure in the EDA output directory and close it."""
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / filename, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved plot: {PLOTS_DIR / filename}")


def main() -> None:
    if not DATASET_PATH.is_file():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    # Read-only analysis: this script never writes to the source CSV.
    dataset = pd.read_csv(DATASET_PATH)

    print(f"Dataset: {DATASET_PATH}")
    print(f"\nShape: {dataset.shape}")
    print(f"\nColumns: {dataset.columns.tolist()}")
    print("\nData types:")
    print(dataset.dtypes.to_string())
    print("\nMissing values by column:")
    print(dataset.isna().sum().to_string())

    duplicate_count = int(dataset.duplicated().sum())
    print(f"\nDuplicate records: {duplicate_count}")
    if duplicate_count:
        print("WARNING: Duplicate records were found; they are not removed.")

    print("\nDescriptive statistics:")
    print(dataset.describe(include="all").to_string())

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in dataset.columns]
    extra_columns = [column for column in dataset.columns if column not in REQUIRED_COLUMNS]
    if missing_columns:
        print(f"\nDATA ISSUE: Required columns are missing: {missing_columns}")
    if extra_columns:
        print(f"\nDATA ISSUE: Unexpected columns are present: {extra_columns}")
    if missing_columns:
        raise ValueError("Cannot create all requested plots because required columns are missing.")

    non_numeric_columns = [
        column for column in NUMERIC_COLUMNS
        if not pd.api.types.is_numeric_dtype(dataset[column])
    ]
    if non_numeric_columns:
        print(f"\nDATA ISSUE: Expected numeric columns have non-numeric data types: {non_numeric_columns}")
        raise TypeError("Cannot create numeric plots until the input data types are corrected.")

    print("\nValue-range checks:")
    for column, (minimum, maximum) in VALID_RANGES.items():
        invalid_count = int((~dataset[column].between(minimum, maximum) & dataset[column].notna()).sum())
        if invalid_count:
            print(
                f"DATA ISSUE: {invalid_count} values in {column!r} fall outside "
                f"the expected range [{minimum}, {maximum}]."
            )
        else:
            print(f"{column}: all non-missing values are within [{minimum}, {maximum}].")

    unexpected_services = sorted(
        set(dataset["service_type"].dropna().unique()) - VALID_SERVICE_TYPES
    )
    if unexpected_services:
        print(f"DATA ISSUE: Unexpected service_type values: {unexpected_services}")
    if dataset["service_type"].isna().any():
        print("DATA ISSUE: Some service_type values are missing.")

    waiting_times = dataset["actual_waiting_time"].dropna()
    if waiting_times.empty:
        print("DATA ISSUE: No non-missing actual_waiting_time values are available.")
    else:
        q1 = waiting_times.quantile(0.25)
        q3 = waiting_times.quantile(0.75)
        upper_outlier_limit = q3 + 1.5 * (q3 - q1)
        outliers = dataset.loc[
            dataset["actual_waiting_time"] > upper_outlier_limit,
            ["actual_waiting_time"],
        ].copy()
        outliers.insert(0, "record_number", outliers.index + 1)

        capped_records = dataset.loc[
            dataset["actual_waiting_time"] == 240,
            ["actual_waiting_time"],
        ].copy()
        capped_records.insert(0, "record_number", capped_records.index + 1)

        print(
            "\nUnusually high waiting times "
            f"(Tukey upper limit: {upper_outlier_limit:.2f} minutes): "
            f"{len(outliers)} record(s)"
        )
        if outliers.empty:
            print("None.")
        else:
            print(outliers.to_string(index=False))

        print(f"\nRecords capped at 240 minutes: {len(capped_records)}")
        if capped_records.empty:
            print("None.")
        else:
            print(capped_records.to_string(index=False))

        print(
            "\nWaiting-time summary: "
            f"mean={waiting_times.mean():.2f}, median={waiting_times.median():.2f}, "
            f"maximum={waiting_times.max():.2f} minutes."
        )

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid")

    # Distribution of the target variable.
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.histplot(data=dataset, x="actual_waiting_time", bins=30, kde=True, ax=ax)
    ax.set(title="Distribution of Actual Waiting Time", xlabel="Waiting time (minutes)", ylabel="Record count")
    save_plot(fig, "actual_waiting_time_histogram.png")

    # Compare queue size, counter availability, and service time with waiting time.
    scatter_plots = [
        ("people_waiting", "People Waiting vs Actual Waiting Time", "people_waiting_scatter.png"),
        ("active_counters", "Active Counters vs Actual Waiting Time", "active_counters_scatter.png"),
        ("avg_service_time", "Average Service Time vs Actual Waiting Time", "avg_service_time_scatter.png"),
    ]
    for x_column, title, filename in scatter_plots:
        fig, ax = plt.subplots(figsize=(8, 5))
        sns.scatterplot(data=dataset, x=x_column, y="actual_waiting_time", alpha=0.65, ax=ax)
        ax.set(title=title, xlabel=x_column.replace("_", " ").title(), ylabel="Waiting time (minutes)")
        save_plot(fig, filename)

    # Grouped means make both requested bar charts explicit and comparable.
    for group_column, title, filename, x_label in [
        ("service_type", "Average Waiting Time by Service Type", "waiting_time_by_service_type.png", "Service type"),
        ("active_counters", "Average Waiting Time by Active Counters", "waiting_time_by_active_counters.png", "Active counters"),
    ]:
        averages = (
            dataset.groupby(group_column, dropna=False, observed=True)["actual_waiting_time"]
            .mean()
            .reset_index()
        )
        fig, ax = plt.subplots(figsize=(8, 5))
        sns.barplot(data=averages, x=group_column, y="actual_waiting_time", color="steelblue", ax=ax)
        ax.set(title=title, xlabel=x_label, ylabel="Average waiting time (minutes)")
        if group_column == "service_type":
            ax.tick_params(axis="x", rotation=20)
        save_plot(fig, filename)

    # Include every numeric column present in the dataset in the correlation plot.
    numeric_data = dataset.select_dtypes(include=np.number)
    if numeric_data.empty:
        print("\nDATA ISSUE: No numeric columns are available for the correlation heatmap.")
    else:
        fig, ax = plt.subplots(figsize=(9, 7))
        sns.heatmap(numeric_data.corr(), annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=ax)
        ax.set_title("Correlation Heatmap for Numerical Columns")
        save_plot(fig, "numerical_correlation_heatmap.png")

    print("\nCorrelation with actual_waiting_time:")
    correlations = numeric_data.corr()["actual_waiting_time"].drop("actual_waiting_time", errors="ignore")
    print(correlations.sort_values(ascending=False).to_string())
    print(f"\nEDA complete. Plots saved in: {PLOTS_DIR}")


if __name__ == "__main__":
    main()
