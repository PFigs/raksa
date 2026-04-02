import re

import httpx

from raksa.models import FaultNotification, ShareholderRenovation


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
query faultNotificationsOfCodominiums($condominiumIds: [ID!]!) {
  faultNotificationsOfCodominiums(condominiumIds: $condominiumIds) {
    _id
    condominiumId
    createdAt
    informantInfo { firstName lastName email phone }
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
    informantInfo { firstName lastName email phone }
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
        data = self._gql(LIST_FAULTS_QUERY, {"condominiumIds": [condo_id]})
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
