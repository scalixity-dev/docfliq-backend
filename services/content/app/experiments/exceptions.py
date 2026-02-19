"""Experiments domain exceptions (raised by service, caught by controller)."""


class CohortNotFound(Exception):
    def __init__(self, cohort_id: object) -> None:
        super().__init__(f"Cohort {cohort_id} not found.")


class ExperimentNotFound(Exception):
    def __init__(self, experiment_id: object) -> None:
        super().__init__(f"Experiment {experiment_id} not found.")


class ExperimentTransitionError(Exception):
    """Invalid status transition (e.g. starting a COMPLETED experiment)."""


class ExperimentDurationError(Exception):
    """end_date is less than 7 days after start."""


class VariantTrafficError(Exception):
    """variants[].traffic_pct values do not sum to 100."""
