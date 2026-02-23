import configparser
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
    name_keywords: List[str] = field(default_factory=lambda: [
        "semester 1",
        "sem 1",
        "fall",
        "autumn",
    ])
    require_keyword: bool = True


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
class PushoverConfig:
    enabled: bool = False
    api_token: Optional[str] = None
    user_key: Optional[str] = None


@dataclass
class OpenClawConfig:
    enabled: bool = False
    endpoint: Optional[str] = None
    api_key: Optional[str] = None


@dataclass
class NotificationConfig:
    pushover: PushoverConfig = field(default_factory=PushoverConfig)
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


def _load_ini(path: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    if os.path.exists(path):
        parser.read(path)
    return parser


def load_config(yaml_path: str = "config.yaml", ini_path: str = "config.ini") -> Tuple[Config, List[str]]:
    data, warnings = _load_yaml(yaml_path)
    ini = _load_ini(ini_path)

    target_data = _get_dict(data, "target", {})
    filter_data = _get_dict(data, "filters", {})
    academic_data = _get_dict(data, "academic_year", {})
    semester_data = _get_dict(academic_data, "semester1", {})
    polling_data = _get_dict(data, "polling", {})
    notify_data = _get_dict(data, "notifications", {})
    pushover_data = _get_dict(notify_data, "pushover", {})
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
                require_keyword=semester_data.get("require_keyword", True),
            ),
        ),
        polling=PollingConfig(
            interval_seconds=int(polling_data.get("interval_seconds", 300)),
            jitter_seconds=int(polling_data.get("jitter_seconds", 30)),
        ),
        notifications=NotificationConfig(
            pushover=PushoverConfig(
                enabled=pushover_data.get("enabled", False),
                api_token=pushover_data.get("api_token"),
                user_key=pushover_data.get("user_key"),
            ),
            openclaw=OpenClawConfig(
                enabled=openclaw_data.get("enabled", False),
                endpoint=openclaw_data.get("endpoint"),
                api_key=openclaw_data.get("api_key"),
            ),
        ),
    )

    if ini.has_section("Pushover"):
        if not config.notifications.pushover.api_token:
            config.notifications.pushover.api_token = ini.get("Pushover", "api_token", fallback=None)
        if not config.notifications.pushover.user_key:
            config.notifications.pushover.user_key = ini.get("Pushover", "user_key", fallback=None)

    if config.notifications.pushover.api_token and config.notifications.pushover.user_key:
        config.notifications.pushover.enabled = True

    return config, warnings
