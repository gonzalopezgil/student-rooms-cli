import logging
import time
from typing import Any, Dict, List, Optional

import requests

API_PREFIX = "https://yugo.com/en-gb/"
API_CALLS = {
    "countries": {
        "name": "countries",
        "api": "countries",
    },
    "cities": {
        "name": "cities",
        "api": "cities?countryId={}",
        "param": "countryId",
    },
    "residences": {
        "name": "residences",
        "api": "residences?cityId={}",
        "param": "contentId",
    },
    "rooms": {
        "name": "rooms",
        "api": "rooms?residenceId={}",
        "param": "residenceId",
    },
    "options": {
        "name": "tenancyOptions",
        "api": "tenancyOptionsBySSId?residenceId={}&residenceContentId={}&roomId={}",
    },
}

logger = logging.getLogger(__name__)


class YugoClient:
    def __init__(
        self,
        session: Optional[requests.Session] = None,
        base_url: str = API_PREFIX,
        timeout: int = 30,
        retries: int = 3,
        retry_backoff_seconds: float = 1.0,
    ):
        self.session = session or requests.Session()
        self.base_url = base_url
        self.timeout = timeout
        self.retries = max(1, retries)
        self.retry_backoff_seconds = max(0.1, retry_backoff_seconds)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = self.base_url + path
        last_error: Optional[Exception] = None

        for attempt in range(1, self.retries + 1):
            try:
                response = self.session.request(method.upper(), url, params=params, data=data, timeout=self.timeout)
                if response.status_code >= 500:
                    response.raise_for_status()
                if response.status_code >= 400:
                    # 4xx usually means bad params, no retry needed
                    response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.retries:
                    raise
                sleep_for = self.retry_backoff_seconds * attempt
                logger.warning("Yugo API request failed (%s %s): %s [retry %s/%s in %.1fs]", method, path, exc, attempt, self.retries, sleep_for)
                time.sleep(sleep_for)

        if last_error:
            raise last_error
        raise RuntimeError(f"Unexpected request failure for {method} {path}")

    def _get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request_json("GET", path, params=params)

    def _post_json(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request_json("POST", path, data=data)

    def list_countries(self) -> List[Dict[str, Any]]:
        data = self._get_json(API_CALLS["countries"]["api"])
        return data.get(API_CALLS["countries"]["name"], [])

    def list_cities(self, country_id: str) -> List[Dict[str, Any]]:
        data = self._get_json("cities", params={"countryId": country_id})
        return data.get(API_CALLS["cities"]["name"], [])

    def list_residences(self, city_id: str) -> List[Dict[str, Any]]:
        data = self._get_json("residences", params={"cityId": city_id})
        return data.get(API_CALLS["residences"]["name"], [])

    def list_rooms(self, residence_id: str) -> List[Dict[str, Any]]:
        data = self._get_json("rooms", params={"residenceId": residence_id})
        return data.get(API_CALLS["rooms"]["name"], [])

    def list_tenancy_options(self, residence_id: str, residence_content_id: str, room_id: str) -> List[Dict[str, Any]]:
        data = self._get_json(
            "tenancyOptionsBySSId",
            params={
                "residenceId": residence_id,
                "residenceContentId": residence_content_id,
                "roomId": room_id,
            },
        )
        return data.get("tenancy-options", [])

    # Booking-flow endpoints (read/probe + handover link generation)
    def get_residence_property(self, residence_id: str) -> Dict[str, Any]:
        return self._get_json("residence-property", params={"residenceId": residence_id})

    def get_available_beds(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self._get_json("available-beds", params=params)

    def get_flats_with_beds(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self._get_json("flats-with-beds", params=params)

    def get_skip_room_selection(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self._get_json("skip-room-selection", params=params)

    def post_student_portal_redirect(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._post_json("student-portal-redirect", data=data)


def find_by_name(items: List[Dict[str, Any]], name: Optional[str]) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    target = name.strip().lower()
    for item in items:
        if str(item.get("name", "")).strip().lower() == target:
            return item
    return None
