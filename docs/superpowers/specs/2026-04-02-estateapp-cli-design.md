# Raksa -- Design Spec

A publishable Python CLI tool for interacting with housing company management systems. Currently supports EstateApp (app.estateapp.com) as a backend. The primary use case is importing historical renovation notifications and fault reports from a hive-structured YAML directory into EstateApp's GraphQL API.

## Architecture

### Package layout

```
raksa/
  src/
    raksa/
      __init__.py
      client.py
      models.py
      cli.py
      commands/
        __init__.py
        renovations.py
        faults.py
        auth.py
  tests/
  pyproject.toml
  .env                    # gitignored, user config
```

Installed command name: `raksa`.

### Dependencies

- `httpx` -- HTTP client for GraphQL requests
- `pydantic` -- data validation and models
- `typer` -- CLI framework
- `pyyaml` -- YAML parsing for import
- `python-dotenv` -- .env file support

## Authentication

EstateApp is a Meteor 3.4 app with Apollo GraphQL. The GraphQL endpoint is `https://app.estateapp.com/graphql`. Authentication uses the raw Meteor login token in the `authorization` header (not Bearer).

### Token resolution order

1. `.env` file in working directory (`RAKSA_TOKEN`)
2. `RAKSA_TOKEN` environment variable
3. `~/.config/raksa/token.json` (JSON with `loginToken`, `userId` keys)

### Token setup

`raksa auth setup` prompts the user to paste the JSON blob from browser console (instructions provided). Saves to `~/.config/raksa/token.json`.

Browser console snippet to obtain token:
```js
JSON.stringify({
  loginToken: localStorage.getItem('Meteor.loginToken'),
  userId: localStorage.getItem('Meteor.userId')
})
```

### .env format

```
RAKSA_TOKEN=<raw login token string>
RAKSA_CONDO_ID=<condominium document id>
```

When `RAKSA_CONDO_ID` is set, `--condo-id` becomes optional on all commands.

## Client (`client.py`)

Thin wrapper around `httpx` for EstateApp's GraphQL API.

```python
class EstateAppClient:
    def __init__(self, token: str, base_url: str = "https://app.estateapp.com")
    
    # Renovations
    def list_renovations(self, condo_id: str) -> list[ShareholderRenovation]
    def get_renovation(self, gig_id: str) -> ShareholderRenovation
    def create_renovation(self, input: CreateRenovationInput) -> str  # returns gig ID
    def update_renovation(self, gig_id: str, input: UpdateRenovationInput) -> str

    # Faults
    def list_faults(self, condo_id: str) -> list[FaultNotification]
    def get_fault(self, fault_id: str) -> FaultNotification
    def create_fault(self, condo_id: str, input: FaultNotificationInput) -> str
```

- All methods return Pydantic models, not raw dicts.
- Default timeout: 60 seconds (the API can be slow).
- GraphQL errors raise a typed `EstateAppError` exception.

### GraphQL operations used

**Renovations:**
- `query getCondominiumShareholderRenovationGigs($condominiumId: ID!)` -- list
- `query getShareholderRenovationGigById($gigId: ID!)` -- get by ID
- `mutation createShareholderRenovationGig($gigInput: RequestAndQueryInput!, $companyKey: String, $formIsCompanySpecific: Boolean, $managingCompanyId: String)` -- create
- `mutation updateShareholderRenovationGig(...)` -- update

**Faults:**
- `query faultNotificationsOfCodominiums($condominiumId: ID!)` -- list
- `query faultNotificationById($faultNotificationId: ID!)` -- get by ID
- `mutation editFaultNotification($faultNotificationId: ID, $condominiumId: ID!, $tempFileParentId: ID, $faultNotificationInput: FaultNotificationInput, $isCompanySpecific: Boolean)` -- create (null ID) or update

### Key create renovation input structure

The `createShareholderRenovationGig` mutation takes a `RequestAndQueryInput` with these relevant fields:

```
gigInput:
  condominiumId: ID
  type: "shareholderRenovationWork"
  status: "UPCOMING"
  startDate: String (epoch ms)
  endDate: String (epoch ms)
  title: String
  description: String
  shareholderRenovationWork:
    apartmentAddress: String
    informant: { _id, name, phone, email }
    shareholder: { _id, name, phone, email }
    contractors: [{ _id, companyName, companyBusinessId, contact: { _id, name, phone, email } }]
    informantIsApartmentOwner: Boolean
    workDescription: String
    hazardousSubstanceSurveysDone: Boolean
    renovationRequiresFireWork: Boolean
    chosenJobs:
      heatPumpInstallation: Boolean
      kitchenRenovation: Boolean
      bathroomRenovation: Boolean
      saunaRenovation: Boolean
      toiletRenovation: Boolean
      floorSurfaces: Boolean
      balconyGlazingInstallation: Boolean
      # ...24 boolean fields total
    collateral:
      authorizedToSubmitRenovationWork: Boolean
      understandContractorLiability: Boolean
      infoProvidedIsAccurate: Boolean
      acceptModificationTerms: Boolean
      awareOfProcessingAfterPayment: Boolean
    formSize: "comprehensive" | "short"
```

## Models (`models.py`)

### EstateApp output models (API responses)

- `ShareholderRenovation` -- full gig with nested types
- `ChosenJobs` -- 24 boolean fields
- `Contact` -- _id, name, phone, email
- `Contractor` -- _id, companyName, companyBusinessId, contact
- `WorkPerformer` -- performer (contractor/itself/both), steps
- `Collateral` -- 5 boolean acknowledgement fields
- `FaultNotification` -- fault report with informant, description, apartment

### EstateApp input models (for create/update)

- `CreateRenovationInput` -- mirrors RequestAndQueryInput relevant fields
- `ShareholderRenovationWorkInput` -- nested renovation details
- `ChosenJobsInput`, `ContactInput`, `ContractorInput`, `CollateralInput`, `WorkPerformerInput`
- `FaultNotificationInput` -- fault create/update fields

### Source data model (YAML import)

`YAMLCase` represents the hive YAML structure from the premis system:

```python
class YAMLCase(BaseModel):
    Title: str
    CreatedOn: str
    ModifiedOn: str | None
    Description: str | None
    PublicDescription: str | None
    ContactPerson: EntityRef | None
    Space: EntityRef | None
    BuildingAddress: str | None
    Cooperative: EntityRef | None
    RenovationTypes: list[RenovationType] | None
    EstimatedTiming: str | None
    State: LabelValue | None
    Status: LabelValue | None
    RequestType: LabelValue | None
    CaseLevel1: LabelValue | None
    CaseLevel2: LabelValue | None
    HasFiles: bool
    # supporting types: EntityRef, LabelValue, RenovationType
```

With methods:
- `to_renovation_input(condo_id: str) -> CreateRenovationInput` -- maps repair cases to EstateApp renovation input
- `to_fault_input() -> FaultNotificationInput` -- maps common cases to EstateApp fault input

### Field mapping: YAML renovation -> EstateApp

| YAML field | EstateApp field |
|---|---|
| `Space.Name` (e.g. "G18") | `premiseName` |
| `BuildingAddress` + `Space.Name` | `apartmentAddress` |
| `ContactPerson.Name` | `informant.name` |
| `PublicDescription` | `workDescription` |
| `EstimatedTiming` (parsed) | `startDate`, `endDate` |
| `CreatedOn` | used for ordering/reference |
| `RenovationTypes[].OrganizationName` | `contractors[].companyName` |
| `RenovationTypes[].BusinessId` | `contractors[].companyBusinessId` |
| `RenovationTypes[].Type.Label` | `chosenJobs` boolean flags |
| `RenovationTypes[].Description` | appended to `workDescription` |

### Renovation type label -> chosenJobs mapping

| YAML `Type.Label` | `chosenJobs` field |
|---|---|
| Ilmalampopumpun asennus | `heatPumpInstallation` |
| Lampo-, vesi- tai ilmastointityo | `otherChanges` (HVAC work is too broad; description carries the detail) |
| Sahkotyo | `otherChanges` (electrical work doesn't have a single match; description carries the detail) |
| Keittiöremontti | `kitchenRenovation` |
| Lattiamateriaalin vaihtaminen | `floorSurfaces` |
| Parveke- tai terassilasitus / Parvekelasitus | `balconyGlazingInstallation` |
| Muu muutostyo | `otherChanges` |

### Field mapping: YAML common case -> EstateApp fault

| YAML field | EstateApp field |
|---|---|
| `Description` | `faultDescription` |
| `Space.Name` | `space` / `apartment` |
| `BuildingAddress` | `streetAddress` |
| `ContactPerson.Name` | `contactName` |
| `CreatedOn` | reference date |

## CLI (`cli.py` + `commands/`)

Framework: `typer` with subcommand groups.

### Commands

```
raksa auth setup
    Interactive setup -- prompts for browser console JSON, saves token.

raksa renovations list [--condo-id ID]
    Lists all shareholder renovation gigs for the condominium.

raksa renovations get <gig-id>
    Shows details of a specific renovation gig.

raksa renovations import <yaml-dir> [--condo-id ID] [--dry-run] [--submit]
    Imports renovation cases from hive YAML directory.
    Default: dry-run (prints what would be submitted).
    --submit: actually sends to the API.
    Expects directory structure: year=*/house=*/*.yaml

raksa faults list [--condo-id ID]
    Lists all fault notifications for the condominium.

raksa faults get <fault-id>
    Shows details of a specific fault notification.

raksa faults import <yaml-dir> [--condo-id ID] [--dry-run] [--submit]
    Imports fault cases from hive YAML directory.
    Same structure expectations as renovations.
```

### Import behavior

1. Walk the hive directory tree (`year=*/house=*/*.yaml`, skip `*_chat.yaml`)
2. Parse each YAML file into a `YAMLCase` Pydantic model
3. Filter by `RequestType.Label` -- "Huoneistomuutosilmoitus" for renovations, others for faults
4. Transform to EstateApp input model via `to_renovation_input()` / `to_fault_input()`
5. **Dry-run (default):** print a summary table of what would be submitted -- apartment, date, work type, description preview
6. **Submit (`--submit`):** call the API for each case, print success/failure per case with the YAML filename

### Error handling

- Auth failures: clear message pointing to `raksa auth setup`
- API timeouts: retry once, then report failure for that case
- Validation errors: skip the case, log which file failed and why
- Partial failures: continue with remaining cases, print summary at end

## Configuration

### .env file (project-level)

```
RAKSA_TOKEN=5iCyGEkszZ...
RAKSA_CONDO_ID=kJXwXieRhQjFgRSQ9
RAKSA_BASE_URL=https://app.estateapp.com  # optional, for testing
```

### ~/.config/raksa/token.json (user-level)

```json
{
  "loginToken": "5iCyGEkszZ...",
  "userId": "8HpaupNX5Zbo3ihYv"
}
```

## Out of scope (for now)

- File/attachment upload (some cases have `HasFiles: true`)
- Chat message import (`*_chat.yaml` files)
- Creating condominiums or managing users
- Batch import via `shareholderRenovationBatchImport` endpoint
- Token refresh (Meteor tokens are long-lived; current one expires 2026-04-28)
- Premis export (future: could add `raksa premis export` commands)
