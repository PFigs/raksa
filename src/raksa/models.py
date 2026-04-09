import datetime
import re
import uuid

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Contact(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = Field(default="", alias="_id")
    name: str | None = None
    phone: str | None = None
    email: str | None = None


class Contractor(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    company_name: str | None = Field(default=None, alias="companyName")
    company_business_id: str | None = Field(default=None, alias="companyBusinessId")
    contact: Contact | None = None


class ChosenJobs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    floor_surfaces: bool | None = Field(default=None, alias="floorSurfaces")
    balcony_glazing_installation: bool | None = Field(default=None, alias="balconyGlazingInstallation")
    painting_doors_without_frames_and_trims: bool | None = Field(default=None, alias="paintingDoorsWithoutFramesAndTrims")
    door_replacement_and_molding_replacement: bool | None = Field(default=None, alias="doorReplacementAndMoldingReplacement")
    dry_cabinet_replacement_or_install: bool | None = Field(default=None, alias="dryCabinetReplacementOrInstall")
    broken_socket_or_switch_replacement: bool | None = Field(default=None, alias="brokenSocketOrSwitchReplacement")
    socket_or_switch_add_or_remove: bool | None = Field(default=None, alias="socketOrSwitchAddOrRemove")
    built_in_cabinet_demolition: bool | None = Field(default=None, alias="builtInCabinetDemolition")
    washing_machine_installed: bool | None = Field(default=None, alias="washingMachineInstalled")
    washing_machine_installed_to_wet_zone: bool | None = Field(default=None, alias="washingMachineInstalledToWetZone")
    washing_machine_installed_to_dry_zone: bool | None = Field(default=None, alias="washingMachineInstalledToDryZone")
    dishwasher_installed: bool | None = Field(default=None, alias="dishwasherInstalled")
    first_dishwasher_installation: bool | None = Field(default=None, alias="firstDishwasherInstallation")
    replaced_to_new_dishwasher: bool | None = Field(default=None, alias="replacedToNewDishwasher")
    cabinet_pipe_or_electrical_presence: bool | None = Field(default=None, alias="cabinetPipeOrElectricalPresence")
    wallpaper_removal_or_surface_sanding: bool | None = Field(default=None, alias="wallpaperRemovalOrSurfaceSanding")
    partition_demolition_or_construction: bool | None = Field(default=None, alias="partitionDemolitionOrConstruction")
    heat_pump_installation: bool | None = Field(default=None, alias="heatPumpInstallation")
    kitchen_renovation: bool | None = Field(default=None, alias="kitchenRenovation")
    bathroom_renovation: bool | None = Field(default=None, alias="bathroomRenovation")
    sauna_renovation: bool | None = Field(default=None, alias="saunaRenovation")
    toilet_renovation: bool | None = Field(default=None, alias="toiletRenovation")
    electric_car_charging_sockets: bool | None = Field(default=None, alias="electricCarChargingSockets")
    other_changes: bool | None = Field(default=None, alias="otherChanges")


class Collateral(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    authorized_to_submit_renovation_work: bool | None = None
    understand_contractor_liability: bool | None = None
    info_provided_is_accurate: bool | None = None
    accept_modification_terms: bool | None = None
    aware_of_processing_after_payment: bool | None = None


class WorkPerformer(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    performer: str | None = None
    contractor_working_steps: list | None = None
    itself_working_steps: list | None = None


class ShareholderRenovationWork(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    condominium_name: str | None = Field(default=None, alias="condomininumName")
    apartment_id: str | None = None
    premise_name: str | None = None
    apartment_address: str | None = None
    informant: Contact | None = None
    shareholder: Contact | None = None
    contractors: list[Contractor] = Field(default_factory=list)

    @field_validator("contractors", mode="before")
    @classmethod
    def _coerce_contractors(cls, v):
        return v if v is not None else []

    informant_is_apartment_owner: bool | None = None
    work_description: str | None = None
    hazardous_substance_surveys_done: bool | None = None
    renovation_requires_fire_work: bool | None = None
    form_size: str | None = None
    work_performer: WorkPerformer | None = Field(default=None, alias="workPerfromer")
    chosen_jobs: ChosenJobs = Field(default_factory=ChosenJobs)
    collateral: Collateral | None = None


class ShareholderRenovation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    title: str | None = None
    status: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    created_at: str | None = None
    condominium_id: str | None = None
    apartment_address: str | None = None
    informant: Contact | None = None
    chosen_jobs: ChosenJobs = Field(default_factory=ChosenJobs)
    shareholder_renovation_work: ShareholderRenovationWork | None = None


class InformantInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None


class FaultNotification(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    condominium_id: str | None = None
    created_at: str | None = None
    informant_info: InformantInfo | None = None
    apartment: str | None = None
    fault_description: str | None = None
    street_address: str | None = None
    space: str | None = None
    contact_phone: str | None = None
    contact_name: str | None = None
    additional_information: str | None = None
    completed_at: str | None = None


class FileRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id", default="")
    alt: str | None = None
    url: str | None = None
    type: str | None = None
    size: int | None = None
    completion_date: str | None = Field(None, alias="completionDate")
    parent_id: str | None = Field(None, alias="parentId")
    collection_name: str | None = Field(None, alias="collectionName")


RENOVATION_TYPE_MAP: dict[str, str] = {
    "Ilmalämpöpumpun asennus": "heatPumpInstallation",
    "Keittiöremontti": "kitchenRenovation",
    "Lattiamateriaalin vaihtaminen": "floorSurfaces",
    "Parveke- tai terassilasitus": "balconyGlazingInstallation",
    "Parvekelasitus": "balconyGlazingInstallation",
}


class YAMLEntityRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="Id")
    logical_name: str = Field(alias="LogicalName")
    name: str = Field(alias="Name")


class YAMLLabelValue(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    label: str = Field(alias="Label")
    value: int = Field(alias="Value")


class YAMLTypeLabelValue(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    label: str = Field(alias="Label")
    value: int = Field(alias="Value")


class YAMLExecutorType(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    label: str = Field(alias="Label")
    value: int = Field(alias="Value")


class YAMLRenovationType(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="Id")
    organization_name: str | None = Field(default=None, alias="OrganizationName")
    business_id: str | None = Field(default=None, alias="BusinessId")
    description: str | None = Field(default=None, alias="Description")
    type: YAMLTypeLabelValue | None = Field(default=None, alias="Type")
    executor_type: YAMLExecutorType | None = Field(default=None, alias="ExecutorType")
    email: str | None = Field(default=None, alias="Email")
    mobile_phone: str | None = Field(default=None, alias="MobilePhone")
    first_name: str | None = Field(default=None, alias="FirstName")
    last_name: str | None = Field(default=None, alias="LastName")
    full_name: str | None = Field(default=None, alias="FullName")
    birthday: str | None = Field(default=None, alias="Birthday")
    foreign_registration_number: str | None = Field(default=None, alias="ForeignRegistrationNumber")


class YAMLCase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    title: str = Field(alias="Title")
    created_on: str = Field(alias="CreatedOn")
    modified_on: str | None = Field(default=None, alias="ModifiedOn")
    description: str | None = Field(default=None, alias="Description")
    public_description: str | None = Field(default=None, alias="PublicDescription")
    contact_person: YAMLEntityRef | None = Field(default=None, alias="ContactPerson")
    space: YAMLEntityRef | None = Field(default=None, alias="Space")
    building_address: str | None = Field(default=None, alias="BuildingAddress")
    building: YAMLEntityRef | None = Field(default=None, alias="Building")
    cooperative: YAMLEntityRef | None = Field(default=None, alias="Cooperative")
    renovation_types: list[YAMLRenovationType] | None = Field(default=None, alias="RenovationTypes")
    estimated_timing: str | None = Field(default=None, alias="EstimatedTiming")
    state: YAMLLabelValue | None = Field(default=None, alias="State")
    status: YAMLLabelValue | None = Field(default=None, alias="Status")
    project_status: YAMLLabelValue | None = Field(default=None, alias="ProjectStatus")
    request_type: YAMLLabelValue | None = Field(default=None, alias="RequestType")
    case_level1: YAMLLabelValue | None = Field(default=None, alias="CaseLevel1")
    case_level2: YAMLLabelValue | None = Field(default=None, alias="CaseLevel2")
    case_level3: YAMLLabelValue | None = Field(default=None, alias="CaseLevel3")
    has_files: bool = Field(default=False, alias="HasFiles")
    id: str = Field(alias="Id")
    conclusion_date: str | None = Field(default=None, alias="ConclusionDate")
    resolution_description: str | None = Field(default=None, alias="ResolutionDescription")
    priority: YAMLLabelValue | None = Field(default=None, alias="Priority")
    supervisor: Any = Field(default=None, alias="Supervisor")
    description_of_terms: str | None = Field(default=None, alias="DescriptionOfTerms")

    @property
    def is_renovation(self) -> bool:
        return self.request_type is not None and self.request_type.label == "Huoneistomuutosilmoitus"

    def _parse_estimated_timing(self) -> tuple[str | None, str | None]:
        if not self.estimated_timing:
            return None, None
        match = re.match(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})", self.estimated_timing)
        if not match:
            return None, None
        start_str, end_str = match.group(1), match.group(2)
        start_dt = datetime.datetime.strptime(start_str, "%d.%m.%Y")
        end_dt = datetime.datetime.strptime(end_str, "%d.%m.%Y")
        start_epoch_ms = str(int(start_dt.timestamp() * 1000))
        end_epoch_ms = str(int(end_dt.timestamp() * 1000))
        return start_epoch_ms, end_epoch_ms

    def _map_chosen_jobs(self) -> dict[str, bool]:
        jobs: dict[str, bool] = {}
        if not self.renovation_types:
            return jobs
        for rt in self.renovation_types:
            label = rt.type.label if rt.type else None
            field_name = RENOVATION_TYPE_MAP.get(label, "otherChanges") if label else "otherChanges"
            jobs[field_name] = True
        return jobs

    def _job_summary(self) -> str:
        if not self.renovation_types:
            return "Muutostyö"
        labels = [rt.type.label for rt in self.renovation_types if rt.type]
        if not labels:
            return "Muutostyö"
        return ", ".join(labels)

    def to_renovation_input(self, condo_id: str) -> dict:
        start_date, end_date = self._parse_estimated_timing()
        chosen_jobs = self._map_chosen_jobs()
        space_name = self.space.name if self.space else ""
        apartment_address = " ".join(filter(None, [self.building_address, space_name]))
        informant: dict | None = None
        if self.contact_person:
            informant = {
                "_id": str(uuid.uuid4()),
                "name": self.contact_person.name,
                "phone": None,
                "email": None,
            }
        contractors = []
        for rt in (self.renovation_types or []):
            contact: dict | None = None
            if rt.first_name or rt.last_name or rt.email or rt.mobile_phone:
                contact = {
                    "_id": str(uuid.uuid4()),
                    "name": " ".join(filter(None, [rt.first_name, rt.last_name])) or None,
                    "phone": rt.mobile_phone,
                    "email": rt.email,
                }
            contractors.append({
                "id": str(uuid.uuid4()),
                "companyName": rt.organization_name,
                "companyBusinessId": rt.business_id,
                "contact": contact,
            })
        job_title = self._job_summary()
        if space_name:
            job_title = f"{job_title} {space_name}"
        collateral = {
            "authorized_to_submit_renovation_work": True,
            "understand_contractor_liability": True,
            "info_provided_is_accurate": True,
            "accept_modification_terms": True,
            "aware_of_processing_after_payment": True,
        }
        return {
            "condominiumId": condo_id,
            "type": "shareholderRenovationWork",
            "status": "UPCOMING",
            "startDate": start_date,
            "endDate": end_date,
            "title": job_title,
            "shareholderRenovationWork": {
                "apartmentAddress": apartment_address,
                "informant": informant,
                "informantIsApartmentOwner": True,
                "workDescription": self.public_description,
                "contractors": contractors,
                "chosenJobs": chosen_jobs,
                "collateral": collateral,
            },
        }

    def to_fault_input(self) -> dict:
        contact_name = self.contact_person.name if self.contact_person else None
        space_name = self.space.name if self.space else None
        return {
            "faultDescription": self.description,
            "space": space_name,
            "apartment": space_name,
            "streetAddress": self.building_address,
            "contactName": contact_name,
        }
