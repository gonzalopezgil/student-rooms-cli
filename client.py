import logging
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
    def __init__(self, session: Optional[requests.Session] = None, base_url: str = API_PREFIX, timeout: int = 30):
        self.session = session or requests.Session()
        self.base_url = base_url
        self.timeout = timeout

    def _get_json(self, path: str) -> Dict[str, Any]:
        url = self.base_url + path
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def list_countries(self) -> List[Dict[str, Any]]:
        data = self._get_json(API_CALLS["countries"]["api"])
        return data.get(API_CALLS["countries"]["name"], [])

    def list_cities(self, country_id: str) -> List[Dict[str, Any]]:
        data = self._get_json(API_CALLS["cities"]["api"].format(country_id))
        return data.get(API_CALLS["cities"]["name"], [])

    def list_residences(self, city_id: str) -> List[Dict[str, Any]]:
        data = self._get_json(API_CALLS["residences"]["api"].format(city_id))
        return data.get(API_CALLS["residences"]["name"], [])

    def list_rooms(self, residence_id: str) -> List[Dict[str, Any]]:
        data = self._get_json(API_CALLS["rooms"]["api"].format(residence_id))
        return data.get(API_CALLS["rooms"]["name"], [])

    def list_tenancy_options(self, residence_id: str, residence_content_id: str, room_id: str) -> List[Dict[str, Any]]:
        data = self._get_json(API_CALLS["options"]["api"].format(residence_id, residence_content_id, room_id))
        return data.get("tenancy-options", [])


def find_by_name(items: List[Dict[str, Any]], name: Optional[str]) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    for item in items:
        if item.get("name", "").strip().lower() == name.strip().lower():
            return item
    return None
