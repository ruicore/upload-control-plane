from __future__ import annotations

from collections.abc import Mapping

_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def label_key(labels: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((key, value) for key, value in (labels or {}).items()))


def render_counter(
    lines: list[str],
    name: str,
    description: str,
    counters: Mapping[tuple[str, tuple[tuple[str, str], ...]], float],
    default_labels: Mapping[str, str] | None = None,
) -> None:
    render_help(lines, name, description, "counter")
    found = False
    for (metric_name, labels), value in sorted(counters.items()):
        if metric_name == name:
            found = True
            lines.append(render_sample(name, dict(labels), value))
    if not found:
        lines.append(render_sample(name, default_labels or {}, 0.0))


def render_histogram(
    lines: list[str],
    name: str,
    description: str,
    histograms: Mapping[tuple[str, tuple[tuple[str, str], ...]], list[float]],
    default_labels: Mapping[str, str] | None = None,
) -> None:
    render_help(lines, name, description, "histogram")
    found = False
    for (metric_name, labels), observations in sorted(histograms.items()):
        if metric_name != name:
            continue
        found = True
        label_dict = dict(labels)
        for bucket in _LATENCY_BUCKETS:
            count = sum(1 for value in observations if value <= bucket)
            lines.append(
                render_sample(f"{name}_bucket", {**label_dict, "le": str(bucket)}, float(count))
            )
        lines.append(
            render_sample(f"{name}_bucket", {**label_dict, "le": "+Inf"}, float(len(observations)))
        )
        lines.append(render_sample(f"{name}_count", label_dict, float(len(observations))))
        lines.append(render_sample(f"{name}_sum", label_dict, float(sum(observations))))
    if not found:
        default_label_dict = dict(default_labels or {})
        for bucket in _LATENCY_BUCKETS:
            lines.append(
                render_sample(f"{name}_bucket", {**default_label_dict, "le": str(bucket)}, 0.0)
            )
        lines.append(render_sample(f"{name}_bucket", {**default_label_dict, "le": "+Inf"}, 0.0))
        lines.append(render_sample(f"{name}_count", default_label_dict, 0.0))
        lines.append(render_sample(f"{name}_sum", default_label_dict, 0.0))


def render_zero_counter(lines: list[str], name: str, labels: Mapping[str, str]) -> None:
    render_help(lines, name, "Not yet instrumented in local implementation.", "counter")
    lines.append(render_sample(name, labels, 0.0))


def render_zero_gauge(lines: list[str], name: str, labels: Mapping[str, str]) -> None:
    render_help(lines, name, "Not yet provider-backed in local implementation.", "gauge")
    lines.append(render_sample(name, labels, 0.0))


def render_help(lines: list[str], name: str, description: str, metric_type: str) -> None:
    lines.append(f"# HELP {name} {description}")
    lines.append(f"# TYPE {name} {metric_type}")


def render_sample(name: str, labels: Mapping[str, str], value: float) -> str:
    label_text = ""
    if labels:
        label_text = (
            "{" + ",".join(f'{key}="{_escape_label(value)}"' for key, value in labels.items()) + "}"
        )
    return f"{name}{label_text} {_format_value(value)}"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_value(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")
