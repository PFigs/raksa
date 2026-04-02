from pydantic import BaseModel, ConfigDict, Field


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
