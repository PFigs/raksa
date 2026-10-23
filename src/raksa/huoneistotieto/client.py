"""Huoneistotieto.fi REST API client."""
import json
from pathlib import Path

import httpx


BASE_URL = "https://api.huoneistotieto.fi"


class HuoneistotietoClient:
    def __init__(
        self,
        token: str,
        user_id: str,
        office_id: str,
        condominium_id: str,
        condominium_number: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._token = token
        self._user_id = user_id
        self._office_id = office_id
        self._condominium_id = condominium_id
        self._condominium_number = condominium_number
        self._http = http_client or httpx.Client(timeout=120.0)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def list_folders(self) -> list[dict]:
        """List all document folders for the condominium."""
        resp = self._http.post(
            f"{BASE_URL}/api/services/app/Asiakirja/GetCondominiumFolders",
            json={
                "officeId": int(self._office_id),
                "condominiumNumbers": [int(self._condominium_number)],
                "levels": [1, 2, 3],
            },
            headers={
                **self._headers(),
                "Content-Type": "application/json-patch+json",
            },
        )
        resp.raise_for_status()
        result = resp.json()["result"]
        # API returns the folder tree as a JSON string (double-encoded)
        if isinstance(result, str):
            result = json.loads(result)
        return result

    def create_folder(self, name: str, parent_id: str) -> str:
        """Create a folder and return its ID.

        If the folder already exists, looks it up via list_folders and returns
        the existing ID.
        """
        resp = self._http.post(
            f"{BASE_URL}/api/services/app/Asiakirja/AddCondominiumFolder",
            params={
                "officeId": self._office_id,
                "condominiumNumber": self._condominium_number,
                "name": name,
                "parentId": parent_id,
                "level": "3",
            },
            headers=self._headers(),
        )
        resp.raise_for_status()
        result = resp.json()["result"]

        # result is a dict like:
        #   {"success": True, "returnObject": "<json string>", "errorMessage": None}
        #   {"success": False, "returnObject": None, "errorMessage": "Kansio on jo olemassa"}
        if isinstance(result, dict):
            if result.get("success") and result.get("returnObject"):
                obj = result["returnObject"]
                if isinstance(obj, str):
                    obj = json.loads(obj)
                return obj["key"]
            if not result.get("success"):
                # Folder already exists -- find its ID from the folder tree
                return self._find_folder_id(name, parent_id)

        # Fallback: result is directly the folder ID string
        return result

    def _find_folder_id(self, name: str, parent_id: str) -> str:
        """Find a folder's ID by name under a given parent."""
        tree = self.list_folders()

        def search(items: list[dict]) -> str | None:
            for item in items:
                if item.get("type") != "folder":
                    continue
                if item.get("key") == parent_id or item.get("key", "").startswith("root"):
                    for child in item.get("children", []):
                        if child.get("label") == name and child.get("type") == "folder":
                            return child["key"]
                found = search(item.get("children", []))
                if found:
                    return found
            return None

        folder_id = search(tree)
        if not folder_id:
            raise RuntimeError(f"Folder '{name}' not found under parent {parent_id}")
        return folder_id

    def upload_files(self, folder_id: str, files: list[Path]) -> None:
        file_tuples = []
        for f in files:
            mime = "application/pdf" if f.suffix == ".pdf" else "application/yaml"
            file_tuples.append(("upload[]", (f.name, f.read_bytes(), mime)))

        resp = self._http.post(
            f"{BASE_URL}/uploadfiles",
            params={
                "officeId": self._office_id,
                "condominiumId": self._condominium_id,
                "userId": self._user_id,
                "folderId": folder_id,
                "level": "3",
            },
            headers=self._headers(),
            files=file_tuples,
        )
        resp.raise_for_status()
