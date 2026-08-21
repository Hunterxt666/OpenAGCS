"""Adaptive Kalman filtering for circular heading measurements.

This module implements Algorithm 1 from the paper: a scalar Kalman filter
whose wrapped innovation is divided into normal, moderate, and severe
residual regimes. Moderate residuals inflate the effective measurement
covariance. Severe residuals require a second consecutive innovation in the
same direction before an update is accepted.
"""

import math


def wrap_pi(angle):
    """Normalize an angle in radians to [-pi, pi)."""
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


class AdaptiveHeadingKalmanFilter:
    """Double-threshold adaptive Kalman filter for heading angles.

    Measurements passed to ``update_degrees`` are expressed in degrees, while
    all filter state, covariance, and paper parameters are maintained in
    radians and radians squared.
    """

    def __init__(
        self,
        process_variance=0.03,
        measurement_variance=2.742e-3,
        lower_threshold=math.radians(35.0),
        upper_threshold=math.radians(140.0),
        covariance_inflation=10.0,
        initial_covariance=1.0,
    ):
        if process_variance < 0:
            raise ValueError("process_variance must be non-negative")
        if measurement_variance <= 0:
            raise ValueError("measurement_variance must be positive")
        if not 0 <= lower_threshold < upper_threshold:
            raise ValueError("thresholds must satisfy 0 <= lower < upper")
        if covariance_inflation <= 1:
            raise ValueError("covariance_inflation must be greater than 1")
        if initial_covariance < 0:
            raise ValueError("initial_covariance must be non-negative")

        self.process_variance = float(process_variance)
        self.measurement_variance = float(measurement_variance)
        self.lower_threshold = float(lower_threshold)
        self.upper_threshold = float(upper_threshold)
        self.covariance_inflation = float(covariance_inflation)
        self.initial_covariance = float(initial_covariance)

        self.heading = None
        self.covariance = self.initial_covariance
        self.last_innovation = None
        self.last_effective_measurement_variance = None
        self.last_gain = None
        self.pending_severe_sign = 0

    def reset(self):
        """Discard the current estimate and restore the initial covariance."""
        self.heading = None
        self.covariance = self.initial_covariance
        self.last_innovation = None
        self.last_effective_measurement_variance = None
        self.last_gain = None
        self.pending_severe_sign = 0

    def update_radians(self, measured_heading):
        """Update the filter from one heading measurement in radians."""
        if not math.isfinite(measured_heading):
            raise ValueError("measured_heading must be finite")

        measurement = wrap_pi(float(measured_heading))
        if self.heading is None:
            self.heading = measurement
            self.last_innovation = 0.0
            self.last_effective_measurement_variance = self.measurement_variance
            self.last_gain = 0.0
            return self.heading

        predicted_heading = self.heading
        predicted_covariance = self.covariance + self.process_variance
        innovation = wrap_pi(measurement - predicted_heading)
        absolute_innovation = abs(innovation)

        if absolute_innovation <= self.lower_threshold:
            inflation = 1.0
            self.pending_severe_sign = 0
        elif absolute_innovation < self.upper_threshold:
            inflation = 1.0 + (
                (self.covariance_inflation - 1.0)
                * (absolute_innovation - self.lower_threshold)
                / (self.upper_threshold - self.lower_threshold)
            )
            self.pending_severe_sign = 0
        else:
            innovation_sign = 1 if innovation >= 0.0 else -1
            if self.pending_severe_sign * innovation_sign <= 0:
                self.heading = predicted_heading
                self.covariance = predicted_covariance
                self.pending_severe_sign = innovation_sign
                self.last_innovation = innovation
                self.last_effective_measurement_variance = None
                self.last_gain = 0.0
                return self.heading
            inflation = 1.0
            self.pending_severe_sign = 0

        effective_measurement_variance = inflation * self.measurement_variance
        gain = predicted_covariance / (
            predicted_covariance + effective_measurement_variance
        )

        self.heading = wrap_pi(predicted_heading + gain * innovation)
        self.covariance = (1.0 - gain) * predicted_covariance
        self.last_innovation = innovation
        self.last_effective_measurement_variance = (
            effective_measurement_variance
        )
        self.last_gain = gain
        return self.heading

    def update_degrees(self, measured_heading):
        """Update the filter and return the estimated heading in degrees."""
        filtered_heading = self.update_radians(math.radians(measured_heading))
        return math.degrees(filtered_heading)
