import re
from pathlib import Path

import httpx

from raksa.models import FaultNotification, FileRef, ShareholderRenovation


class EstateAppError(Exception):
    pass


LIST_RENOVATIONS_QUERY = """
query getCondominiumShareholderRenovationGigs($condominiumId: ID!) {
  getCondominiumShareholderRenovationGigs(condominiumId: $condominiumId) {
    _id
    title
    status
    startDate
    endDate
    description
    createdAt
    condominiumId
    shareholderRenovationWork {
      condomininumName
      apartmentId
      premiseName
      apartmentAddress
      informant { _id name email phone }
      shareholder { _id name email phone }
      contractors {
        _id
        companyName
        companyBusinessId
        contact { _id name phone email }
      }
      informantIsApartmentOwner
      workDescription
      hazardousSubstanceSurveysDone
      renovationRequiresFireWork
      formSize
      workPerfromer { _id performer contractorWorkingSteps itselfWorkingSteps }
      chosenJobs {
        floorSurfaces
        balconyGlazingInstallation
        paintingDoorsWithoutFramesAndTrims
        doorReplacementAndMoldingReplacement
        dryCabinetReplacementOrInstall
        brokenSocketOrSwitchReplacement
        socketOrSwitchAddOrRemove
        builtInCabinetDemolition
        washingMachineInstalled
        washingMachineInstalledToWetZone
        washingMachineInstalledToDryZone
        dishwasherInstalled
        firstDishwasherInstallation
        replacedToNewDishwasher
        cabinetPipeOrElectricalPresence
        wallpaperRemovalOrSurfaceSanding
        partitionDemolitionOrConstruction
        heatPumpInstallation
        kitchenRenovation
        bathroomRenovation
        saunaRenovation
        toiletRenovation
        electricCarChargingSockets
        otherChanges
      }
      collateral {
        authorizedToSubmitRenovationWork
        understandContractorLiability
        infoProvidedIsAccurate
        acceptModificationTerms
        awareOfProcessingAfterPayment
      }
    }
  }
}
"""

GET_RENOVATION_QUERY = """
query getShareholderRenovationGigById($gigId: ID!) {
  getShareholderRenovationGigById(gigId: $gigId) {
    _id
    title
    status
    startDate
    endDate
    description
    createdAt
    condominiumId
    shareholderRenovationWork {
      condomininumName
      apartmentId
      premiseName
      apartmentAddress
      informant { _id name email phone }
      shareholder { _id name email phone }
      contractors {
        _id
        companyName
        companyBusinessId
        contact { _id name phone email }
      }
      informantIsApartmentOwner
      workDescription
      hazardousSubstanceSurveysDone
      renovationRequiresFireWork
      formSize
      workPerfromer { _id performer contractorWorkingSteps itselfWorkingSteps }
      chosenJobs {
        floorSurfaces
        balconyGlazingInstallation
        paintingDoorsWithoutFramesAndTrims
        doorReplacementAndMoldingReplacement
        dryCabinetReplacementOrInstall
        brokenSocketOrSwitchReplacement
        socketOrSwitchAddOrRemove
        builtInCabinetDemolition
        washingMachineInstalled
        washingMachineInstalledToWetZone
        washingMachineInstalledToDryZone
        dishwasherInstalled
        firstDishwasherInstallation
        replacedToNewDishwasher
        cabinetPipeOrElectricalPresence
        wallpaperRemovalOrSurfaceSanding
        partitionDemolitionOrConstruction
        heatPumpInstallation
        kitchenRenovation
        bathroomRenovation
        saunaRenovation
        toiletRenovation
        electricCarChargingSockets
        otherChanges
      }
      collateral {
        authorizedToSubmitRenovationWork
        understandContractorLiability
        infoProvidedIsAccurate
        acceptModificationTerms
        awareOfProcessingAfterPayment
      }
    }
  }
}
"""

CREATE_RENOVATION_MUTATION = """
mutation createShareholderRenovationGig(
  $gigInput: RequestAndQueryInput!
  $companyKey: String
  $formIsCompanySpecific: Boolean
  $managingCompanyId: String
) {
  createShareholderRenovationGig(
    gigInput: $gigInput
    companyKey: $companyKey
    formIsCompanySpecific: $formIsCompanySpecific
    managingCompanyId: $managingCompanyId
  )
}
"""

LIST_FAULTS_QUERY = """
query faultNotificationsOfCodominiums($condominiumId: ID!) {
  faultNotificationsOfCodominiums(condominiumId: $condominiumId) {
    _id
    condominiumId
    createdAt
    apartment
    faultDescription
    streetAddress
    space
    contactPhone
    contactName
    additionalInformation
    completedAt
  }
}
"""

GET_FAULT_QUERY = """
query faultNotificationById($faultNotificationId: ID!) {
  faultNotificationById(faultNotificationId: $faultNotificationId) {
    _id
    condominiumId
    createdAt
    apartment
    faultDescription
    streetAddress
    space
    contactPhone
    contactName
    additionalInformation
    completedAt
  }
}
"""

CREATE_FAULT_MUTATION = """
mutation editFaultNotification(
  $faultNotificationId: ID
  $condominiumId: ID!
  $faultNotificationInput: FaultNotificationInput
) {
  editFaultNotification(
    faultNotificationId: $faultNotificationId
    condominiumId: $condominiumId
    faultNotificationInput: $faultNotificationInput
  )
}
"""

LIST_FILES_QUERY = """
query filesByParentId($parentId: ID!, $collectionNames: [String]) {
  filesByParentId(parentId: $parentId, collectionNames: $collectionNames) {
    _id
    alt
    url
    type
    size
    completionDate
    parentId
    collectionName
  }
}
"""

REMOVE_FILE_MUTATION = """
mutation removeFile($fileRefId: ID!, $url: String!) {
  removeFile(fileRefId: $fileRefId, url: $url)
}
"""

APPROVE_RENOVATION_MUTATION = """
mutation editShareholderRenovationApproval($gigId: ID!, $approvalInput: ApprovalInput!) {
  editShareholderRenovationApproval(gigId: $gigId, approvalInput: $approvalInput)
}
"""

_CAMEL_RE = re.compile(r"(?<=[a-z0-9])([A-Z])")


def _to_snake(name: str) -> str:
    return _CAMEL_RE.sub(r"_\1", name).lower()


def _normalize(obj: object) -> object:
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            new_key = "id" if k == "_id" else _to_snake(k)
            result[new_key] = _normalize(v)
        return result
    if isinstance(obj, list):
        return [_normalize(item) for item in obj]
    return obj


class EstateAppClient:
    def __init__(
        self,
        token: str,
        base_url: str = "https://app.estateapp.com",
        http_client: httpx.Client | None = None,
    ) -> None:
        self._token = token
        self._base_url = base_url
        self._http = http_client or httpx.Client(timeout=60.0)

    def _gql(self, query: str, variables: dict | None = None) -> dict:
        payload: dict = {"query": query}
        if variables is not None:
            payload["variables"] = variables
        response = self._http.post(
            f"{self._base_url}/graphql",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "authorization": self._token,
            },
        )
        body = response.json()
        if "errors" in body:
            messages = ", ".join(e.get("message", str(e)) for e in body["errors"])
            raise EstateAppError(messages)
        return body["data"]

    def list_renovations(self, condo_id: str) -> list[ShareholderRenovation]:
        data = self._gql(LIST_RENOVATIONS_QUERY, {"condominiumId": condo_id})
        items = data["getCondominiumShareholderRenovationGigs"]
        return [ShareholderRenovation.model_validate(_normalize(item)) for item in items]

    def get_renovation(self, gig_id: str) -> ShareholderRenovation:
        data = self._gql(GET_RENOVATION_QUERY, {"gigId": gig_id})
        return ShareholderRenovation.model_validate(_normalize(data["getShareholderRenovationGigById"]))

    def create_renovation(self, gig_input: dict) -> str:
        data = self._gql(CREATE_RENOVATION_MUTATION, {"gigInput": gig_input})
        return data["createShareholderRenovationGig"]

    def list_faults(self, condo_id: str) -> list[FaultNotification]:
        data = self._gql(LIST_FAULTS_QUERY, {"condominiumId": condo_id})
        items = data["faultNotificationsOfCodominiums"]
        return [FaultNotification.model_validate(_normalize(item)) for item in items]

    def get_fault(self, fault_id: str) -> FaultNotification:
        data = self._gql(GET_FAULT_QUERY, {"faultNotificationId": fault_id})
        return FaultNotification.model_validate(_normalize(data["faultNotificationById"]))

    def create_fault(self, condo_id: str, fault_input: dict) -> str:
        data = self._gql(
            CREATE_FAULT_MUTATION,
            {
                "faultNotificationId": None,
                "condominiumId": condo_id,
                "faultNotificationInput": fault_input,
            },
        )
        return data["editFaultNotification"]

    # Files

    def upload_file(
        self,
        file_path: Path,
        parent_id: str,
        collection_name: str = "shareholderRenovation",
        user_id: str | None = None,
    ) -> FileRef:
        """Upload a file and return the created FileRef."""
        mime = "text/yaml" if file_path.suffix in (".yaml", ".yml") else "application/octet-stream"
        with open(file_path, "rb") as f:
            resp = self._http.post(
                f"{self._base_url}/upload",
                headers={"Authorization": self._token},
                data={
                    "collectionName": collection_name,
                    "collectionParentName": collection_name,
                    "collectionItemId": parent_id,
                    "userId": user_id or "anon",
                },
                files={"files": (file_path.name, f, mime)},
            )
        resp.raise_for_status()
        body = resp.json().get("body", {})
        files = body.get("files", [])
        if not files:
            raise EstateAppError(f"Upload returned no files: {resp.json()}")
        return FileRef.model_validate(files[0])

    def list_files(
        self,
        parent_id: str,
        collection_names: list[str] | None = None,
    ) -> list[FileRef]:
        variables: dict = {"parentId": parent_id}
        if collection_names:
            variables["collectionNames"] = collection_names
        data = self._gql(LIST_FILES_QUERY, variables)
        return [FileRef.model_validate(f) for f in data.get("filesByParentId", [])]

    def remove_file(self, file_ref_id: str, url: str) -> str:
        data = self._gql(REMOVE_FILE_MUTATION, {"fileRefId": file_ref_id, "url": url})
        return data["removeFile"]

    # Approval

    def approve_renovation(self, gig_id: str, approved: bool = True) -> None:
        self._gql(APPROVE_RENOVATION_MUTATION, {
            "gigId": gig_id,
            "approvalInput": {
                "approved": approved,
                "needsMonitoring": False,
                "needsFinalReport": False,
                "finalReportSubmitted": False,
            },
        })
