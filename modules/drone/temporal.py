"""Temporal Processing Engine for EarthMind Drone Module (Stage D4).

Implements Component 8 (ITemporalProcessor) conforming strictly to EarthMind architecture:
- Validates timestamps, timezone information, and temporal metadata.
- Normalizes timestamps to UTC internally while preserving original timestamps and timezone strings.
- Organizes measurements into time-based sequences and collection intervals.
- Detects duplicate timestamps, out-of-order records, missing intervals, and temporal gaps.
- Supports documented time-window filtering and mathematically sound aggregation.
- Rejects unparseable or nonsensical timestamps via TimestampInvalidError.
"""

from datetime import datetime, timezone
import math
import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from core.errors.exceptions import TimestampInvalidError
from core.interfaces.drone import ITemporalProcessor
from core.logging.logger import get_logger
from core.schemas.drone import (
    ProcessedSensorMeasurementContract,
    TemporalCoverage,
    TemporalProcessingReport,
)

logger = get_logger("modules.drone.temporal")


class TemporalProcessor(ITemporalProcessor):
    """Component 8: Temporal coverage and sampling normalization."""

    def __init__(self, default_gap_threshold_seconds: float = 10.0):
        self._default_gap_threshold_seconds = default_gap_threshold_seconds

    def parse_and_normalize_timestamp(self, ts_input: Any) -> Tuple[datetime, str, str]:
        """
        Parse raw timestamp input (ISO 8601 string, UNIX epoch int/float, datetime object).
        Returns:
            Tuple[datetime (UTC-aware), normalized_utc_iso_string, detected_original_tz]
        """
        if ts_input is None:
            raise TimestampInvalidError(
                details="Timestamp input cannot be None.",
                operation="parse_and_normalize_timestamp",
            )

        orig_tz = "UNKNOWN"
        dt_utc: Optional[datetime] = None

        if isinstance(ts_input, (int, float)):
            # UNIX epoch timestamp
            if math.isnan(ts_input) or math.isinf(ts_input):
                raise TimestampInvalidError(
                    details="Timestamp is NaN or Infinite.",
                    operation="parse_and_normalize_timestamp",
                )
            try:
                # Determine if seconds or milliseconds
                if ts_input > 1e11:  # Likely milliseconds
                    dt_utc = datetime.fromtimestamp(ts_input / 1000.0, tz=timezone.utc)
                else:
                    dt_utc = datetime.fromtimestamp(ts_input, tz=timezone.utc)
                orig_tz = "UTC_EPOCH"
            except Exception as exc:
                raise TimestampInvalidError(
                    details=f"Invalid epoch timestamp '{ts_input}': {exc}",
                    operation="parse_and_normalize_timestamp",
                )

        elif isinstance(ts_input, datetime):
            if ts_input.tzinfo is None:
                orig_tz = "NAIVE_UTC"
                dt_utc = ts_input.replace(tzinfo=timezone.utc)
            else:
                orig_tz = str(ts_input.tzinfo)
                dt_utc = ts_input.astimezone(timezone.utc)

        elif isinstance(ts_input, str):
            ts_str = ts_input.strip()
            if not ts_str:
                raise TimestampInvalidError(
                    details="Empty timestamp string.",
                    operation="parse_and_normalize_timestamp",
                )

            # Check for timezone specifiers
            if ts_str.endswith("Z"):
                orig_tz = "UTC"
                clean_str = ts_str[:-1] + "+00:00"
            elif "+" in ts_str or ("-" in ts_str[10:]):  # Has offset
                clean_str = ts_str
                # Extract offset
                match = re.search(r"([+-]\d{2}:?\d{2})$", ts_str)
                if match:
                    orig_tz = match.group(1)
            else:
                # Timezone-naive string: assume UTC but mark detected timezone
                orig_tz = "NAIVE"
                clean_str = ts_str

            try:
                dt = datetime.fromisoformat(clean_str)
                if dt.tzinfo is None:
                    dt_utc = dt.replace(tzinfo=timezone.utc)
                else:
                    dt_utc = dt.astimezone(timezone.utc)
            except Exception:
                # Try common fallback formats
                parsed = False
                for fmt in (
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d %H:%M:%S.%f",
                    "%Y/%m/%d %H:%M:%S",
                    "%d-%m-%Y %H:%M:%S",
                    "%Y%m%dT%H%M%SZ",
                ):
                    try:
                        dt = datetime.strptime(ts_str, fmt)
                        dt_utc = dt.replace(tzinfo=timezone.utc)
                        parsed = True
                        break
                    except ValueError:
                        continue
                if not parsed:
                    raise TimestampInvalidError(
                        details=f"Unable to parse timestamp string '{ts_input}'.",
                        operation="parse_and_normalize_timestamp",
                    )

        else:
            raise TimestampInvalidError(
                details=f"Unsupported timestamp data type: {type(ts_input).__name__}",
                operation="parse_and_normalize_timestamp",
            )

        # Format to canonical ISO 8601 UTC: YYYY-MM-DDTHH:MM:SSZ (or with microseconds if present)
        if dt_utc.microsecond:
            iso_utc = dt_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        else:
            iso_utc = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        return dt_utc, iso_utc, orig_tz

    def process_temporal(
        self,
        collection_timestamp: str,
        end_timestamp: Optional[str] = None,
    ) -> TemporalCoverage:
        """
        Validate UTC timestamps, mission durations, and sampling intervals.
        Adheres to ITemporalProcessor protocol.
        """
        dt_start, start_iso, _ = self.parse_and_normalize_timestamp(collection_timestamp)

        end_iso: Optional[str] = None
        duration: Optional[float] = None

        if end_timestamp is not None:
            dt_end, end_iso, _ = self.parse_and_normalize_timestamp(end_timestamp)
            delta = (dt_end - dt_start).total_seconds()
            if delta < 0:
                raise TimestampInvalidError(
                    details=f"End timestamp '{end_timestamp}' precedes start timestamp '{collection_timestamp}'.",
                    operation="process_temporal",
                )
            duration = delta

        return TemporalCoverage(
            start_time=start_iso,
            end_time=end_iso,
            duration_seconds=duration,
            sampling_frequency_hz=None,
        )

    def sequence_measurements(
        self,
        measurements: List[ProcessedSensorMeasurementContract],
        gap_threshold_seconds: Optional[float] = None,
    ) -> Tuple[List[ProcessedSensorMeasurementContract], TemporalProcessingReport]:
        """
        Organize measurements into a chronological sequence.
        Detects duplicates, out-of-order records, and temporal gaps without losing raw telemetry.
        """
        threshold = gap_threshold_seconds or self._default_gap_threshold_seconds
        if not measurements:
            raise TimestampInvalidError(
                details="Cannot sequence empty measurements list.",
                operation="sequence_measurements",
            )

        parsed_items: List[Tuple[datetime, str, ProcessedSensorMeasurementContract, int]] = []
        detected_tzs = set()
        warnings_list: List[str] = []

        for idx, m in enumerate(measurements):
            dt, iso_norm, orig_tz = self.parse_and_normalize_timestamp(m.timestamp)
            parsed_items.append((dt, iso_norm, m, idx))
            detected_tzs.add(orig_tz)

        # Check chronological status before sorting
        is_chronological = True
        for i in range(len(parsed_items) - 1):
            if parsed_items[i][0] > parsed_items[i + 1][0]:
                is_chronological = False
                break

        # Count duplicates and out of order
        out_of_order_count = 0
        if not is_chronological:
            warnings_list.append("Measurements were not in strict chronological order and have been re-sequenced.")

        # Sort items chronologically (stable sort preserving original relative order for ties)
        sorted_items = sorted(parsed_items, key=lambda x: x[0])

        for orig_idx, (dt, iso, m, initial_pos) in enumerate(sorted_items):
            if initial_pos != orig_idx:
                out_of_order_count += 1

        # Check duplicate timestamps
        duplicate_count = 0
        timestamps_seen = set()
        for dt, iso, m, _ in sorted_items:
            if iso in timestamps_seen:
                duplicate_count += 1
            timestamps_seen.add(iso)

        if duplicate_count > 0:
            warnings_list.append(f"Identified {duplicate_count} measurements with duplicate timestamps.")

        # Analyze intervals and gaps
        gaps: List[float] = []
        intervals: List[float] = []
        for i in range(len(sorted_items) - 1):
            delta = (sorted_items[i + 1][0] - sorted_items[i][0]).total_seconds()
            intervals.append(delta)
            if delta > threshold:
                gaps.append(delta)

        if gaps:
            warnings_list.append(
                f"Identified {len(gaps)} temporal gap(s) exceeding {threshold}s threshold (max gap={max(gaps):.2f}s)."
            )

        # Duration & sampling frequency
        start_time_iso = sorted_items[0][1]
        end_time_iso = sorted_items[-1][1]
        total_duration = (sorted_items[-1][0] - sorted_items[0][0]).total_seconds()

        sampling_freq = None
        if len(sorted_items) > 1 and total_duration > 0:
            positive_intervals = [dt for dt in intervals if dt > 0]
            if positive_intervals:
                mean_interval = sum(positive_intervals) / len(positive_intervals)
                if mean_interval > 0:
                    sampling_freq = round(1.0 / mean_interval, 3)

        # Sequenced measurements list
        sequenced_measurements = [item[2] for item in sorted_items]

        report = TemporalProcessingReport(
            normalized_start_time=start_time_iso,
            normalized_end_time=end_time_iso,
            duration_seconds=total_duration,
            sampling_frequency_hz=sampling_freq,
            original_timestamps_preserved=True,
            detected_timezones=sorted(list(detected_tzs)),
            is_chronological=is_chronological,
            duplicate_timestamps_count=duplicate_count,
            out_of_order_count=out_of_order_count,
            temporal_gaps_count=len(gaps),
            gap_intervals_seconds=gaps,
            warnings=warnings_list,
        )

        return sequenced_measurements, report

    def filter_time_window(
        self,
        measurements: List[ProcessedSensorMeasurementContract],
        start_time: str,
        end_time: str,
    ) -> List[ProcessedSensorMeasurementContract]:
        """
        Filter measurements within an inclusive [start_time, end_time] UTC window.
        Preserves original measurement objects.
        """
        dt_start, _, _ = self.parse_and_normalize_timestamp(start_time)
        dt_end, _, _ = self.parse_and_normalize_timestamp(end_time)

        if dt_start > dt_end:
            raise TimestampInvalidError(
                details=f"Filter start_time '{start_time}' is after end_time '{end_time}'.",
                operation="filter_time_window",
            )

        filtered: List[ProcessedSensorMeasurementContract] = []
        for m in measurements:
            dt_m, _, _ = self.parse_and_normalize_timestamp(m.timestamp)
            if dt_start <= dt_m <= dt_end:
                filtered.append(m)

        return filtered

    def aggregate_measurements_temporal(
        self,
        measurements: List[ProcessedSensorMeasurementContract],
        interval_seconds: float,
        aggregation_func: Optional[Callable[[List[float]], float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Group and aggregate measurements over fixed time intervals.
        Mathematically valid aggregation (e.g., mean) per channel.
        """
        if interval_seconds <= 0:
            raise TimestampInvalidError(
                details=f"Aggregation interval must be > 0, got {interval_seconds}.",
                operation="aggregate_measurements_temporal",
            )

        if not measurements:
            return []

        # Sort measurements
        sequenced, _ = self.sequence_measurements(measurements)
        dt_base, _, _ = self.parse_and_normalize_timestamp(sequenced[0].timestamp)

        # Bucket mapping: bucket_index -> channel -> list of values
        buckets: Dict[int, Dict[str, List[float]]] = {}
        bucket_info: Dict[int, Tuple[datetime, datetime]] = {}

        for m in sequenced:
            dt_m, _, _ = self.parse_and_normalize_timestamp(m.timestamp)
            delta = (dt_m - dt_base).total_seconds()
            bucket_idx = int(delta // interval_seconds)

            if bucket_idx not in buckets:
                buckets[bucket_idx] = {}
                b_start = datetime.fromtimestamp(dt_base.timestamp() + bucket_idx * interval_seconds, tz=timezone.utc)
                b_end = datetime.fromtimestamp(dt_base.timestamp() + (bucket_idx + 1) * interval_seconds, tz=timezone.utc)
                bucket_info[bucket_idx] = (b_start, b_end)

            ch = m.channel_name
            if ch not in buckets[bucket_idx]:
                buckets[bucket_idx][ch] = []
            buckets[bucket_idx][ch].append(m.processed_value)

        agg_fn = aggregation_func or (lambda vals: sum(vals) / len(vals) if vals else 0.0)

        results: List[Dict[str, Any]] = []
        for b_idx in sorted(buckets.keys()):
            b_start, b_end = bucket_info[b_idx]
            ch_data = buckets[b_idx]
            aggregated_channels: Dict[str, Dict[str, Any]] = {}
            for ch, vals in ch_data.items():
                aggregated_channels[ch] = {
                    "count": len(vals),
                    "mean": sum(vals) / len(vals),
                    "min": min(vals),
                    "max": max(vals),
                    "aggregated_value": agg_fn(vals),
                }

            results.append({
                "interval_index": b_idx,
                "interval_start": b_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "interval_end": b_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "channels": aggregated_channels,
            })

        return results
