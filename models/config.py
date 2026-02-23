import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class TargetConfig:
    country: Optional[str] = None
    city: Optional[str] = None
    country_id: Optional[str] = None
    city_id: Optional[str] = None


@dataclass
class FilterConfig:
    private_bathroom: Optional[bool] = None
    private_kitchen: Optional[bool] = None
    max_weekly_price: Optional[float] = None
    max_monthly_price: Optional[float] = None


@dataclass
class Semester1Rules:
    # Strict keyword match for Semester 1 only by default
    name_keywords: List[str] = field(default_factory=lambda: ["semester 1"])
    require_keyword: bool = True

    # Optional date-shape constraints for Semester 1 windows
    start_months: List[int] = field(default_factory=lambda: [9, 10])
    end_months: List[int] = field(default_factory=lambda: [1, 2])
    enforce_month_window: bool = True


@dataclass
class AcademicYearConfig:
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    semester1: Semester1Rules = field(default_factory=Semester1Rules)


@dataclass
class PollingConfig:
    interval_seconds: int = 300
    jitter_seconds: int = 30


@dataclass
class OpenClawConfig:
    enabled: bool = False
    mode: str = "message"  # message | agent
    channel: str = "telegram"
    target: Optional[str] = None

    # If true, create an immediate cron job for reservation assist/autobook
    create_job_on_match: bool = False
    reservation_mode: str = "assist"  # assist | autobook
    job_model: str = "anthropic/claude-sonnet-4-6"
    job_timeout_seconds: int = 600
    job_channel: Optional[str] = None
    job_target: Optional[str] = None


@dataclass
class NotificationConfig:
    openclaw: OpenClawConfig = field(default_factory=OpenClawConfig)


@dataclass
class Config:
    target: TargetConfig = field(default_factory=TargetConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    academic_year: AcademicYearConfig = field(default_factory=AcademicYearConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)


def _get_dict(data, key, default=None):
    value = data.get(key)
    if value is None:
        return default or {}
    if isinstance(value, dict):
        return value
    return default or {}


def _as_int_list(value, fallback):
    if not isinstance(value, list):
        return fallback
    out = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out or fallback


def _load_yaml(path: str) -> Tuple[dict, List[str]]:
    warnings = []
    if not os.path.exists(path):
        warnings.append(f"config.yaml not found at {path}; using defaults.")
        return {}, warnings
    try:
        import yaml  # type: ignore
    except ImportError:
        warnings.append("PyYAML is not installed; skipping YAML config load.")
        return {}, warnings

    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        warnings.append("config.yaml root must be a mapping; using defaults.")
        return {}, warnings
    return data, warnings


def load_config(yaml_path: str = "config.yaml", ini_path: Optional[str] = None) -> Tuple[Config, List[str]]:
    data, warnings = _load_yaml(yaml_path)
    if ini_path:
        warnings.append("config.ini compatibility path is deprecated and ignored (Pushover removed).")

    target_data = _get_dict(data, "target", {})
    filter_data = _get_dict(data, "filters", {})
    academic_data = _get_dict(data, "academic_year", {})
    semester_data = _get_dict(academic_data, "semester1", {})
    polling_data = _get_dict(data, "polling", {})
    notify_data = _get_dict(data, "notifications", {})
    openclaw_data = _get_dict(notify_data, "openclaw", {})

    config = Config(
        target=TargetConfig(
            country=target_data.get("country"),
            city=target_data.get("city"),
            country_id=target_data.get("country_id"),
            city_id=target_data.get("city_id"),
        ),
        filters=FilterConfig(
            private_bathroom=filter_data.get("private_bathroom"),
            private_kitchen=filter_data.get("private_kitchen"),
            max_weekly_price=filter_data.get("max_weekly_price"),
            max_monthly_price=filter_data.get("max_monthly_price"),
        ),
        academic_year=AcademicYearConfig(
            start_year=academic_data.get("start_year"),
            end_year=academic_data.get("end_year"),
            semester1=Semester1Rules(
                name_keywords=semester_data.get("name_keywords")
                if isinstance(semester_data.get("name_keywords"), list)
                else Semester1Rules().name_keywords,
                require_keyword=bool(semester_data.get("require_keyword", True)),
                start_months=_as_int_list(semester_data.get("start_months"), [9, 10]),
                end_months=_as_int_list(semester_data.get("end_months"), [1, 2]),
                enforce_month_window=bool(semester_data.get("enforce_month_window", True)),
            ),
        ),
        polling=PollingConfig(
            interval_seconds=int(polling_data.get("interval_seconds", 300)),
            jitter_seconds=int(polling_data.get("jitter_seconds", 30)),
        ),
        notifications=NotificationConfig(
            openclaw=OpenClawConfig(
                enabled=bool(openclaw_data.get("enabled", False)),
                mode=str(openclaw_data.get("mode", "message")),
                channel=str(openclaw_data.get("channel", "telegram")),
                target=openclaw_data.get("target"),
                create_job_on_match=bool(openclaw_data.get("create_job_on_match", False)),
                reservation_mode=str(openclaw_data.get("reservation_mode", "assist")),
                job_model=str(openclaw_data.get("job_model", "anthropic/claude-sonnet-4-6")),
                job_timeout_seconds=int(openclaw_data.get("job_timeout_seconds", 600)),
                job_channel=openclaw_data.get("job_channel"),
                job_target=openclaw_data.get("job_target"),
            )
        ),
    )

    return config, warnings
