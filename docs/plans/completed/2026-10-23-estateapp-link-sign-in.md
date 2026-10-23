# Sign in to EstateApp through Huoneistotieto

## Design

### Scope

- Get a fresh EstateApp login token without a browser, with the Huoneistotieto email and password.
- Use the same chain as the "EstateApp" link on the Huoneistotieto board page:
  1. `POST https://api.huoneistotieto.fi/api/TokenAuth/Authenticate` with `userNameOrEmailAddress` and `password`
     returns a Huoneistotieto token that lasts 24 hours.
  2. `GET https://api.huoneistotieto.fi/api/services/app/Yhtio/GetAlykasPTSUrl?officeId=…&condominiumId=…` returns
     `https://app.estateapp.com/link-sign-in/<encryptedData>?source=…`.
  3. The EstateApp GraphQL query `signInWithLink(encryptedData, source)` returns `{ token, userId }`, and needs no login.
- Use it in the `meters` commands, which the daily Zaptec sync runs.

### Out of scope

- The `renovations` and `faults` commands. Nobody runs them on a schedule.
- An official EstateApp API key. The EstateApp developer has the request.

### Decisions

- **Sign in at the start of every `meters` command when `RAKSA_HT_EMAIL` and `RAKSA_HT_PASSWORD` are set.** The daily
  sync then never meets an expired token, and it needs no stored token.
  Rejected: sign in only after EstateApp rejects the stored token. That needs a token store and a retry, and the sync
  runs once a day.
- **Without those variables, nothing changes.** The commands read `RAKSA_TOKEN` or `token.json` as before.
- **Reuse the existing Huoneistotieto variables** `RAKSA_HT_OFFICE_ID` and `RAKSA_HT_CONDOMINIUM_ID` for the link request.

### Reuse

- The `HuoneistotietoClient` module for the Huoneistotieto calls, and `EstateAppClient._gql` for the GraphQL query.

### Risks and rollout

- **Unofficial endpoints.** Either company can change them. The sync then fails and emails its owner.
- **One new EstateApp token a day.** Each stays valid for 90 days, so about 90 are live at a time on the account.
- **The account's password in GitHub secrets.** The account has board access to the building's finances. A service
  account limited to meter readings is the better long-term choice.
- Rollout: push raksa. Then move the sync from the server container to a scheduled workflow in apollo-office.

## Tasks

### Task 1: Link sign-in

- **Goal:** the `meters` commands sign in to EstateApp on their own when the Huoneistotieto login is set.
- **Acceptance criteria:**
  - The chain sends the email and password, asks for the link with the office and condominium IDs, and passes the
    decoded path after `/link-sign-in/` as `encryptedData` and the `source` query value.
  - The `meters` commands use the token the chain returns when `RAKSA_HT_EMAIL` and `RAKSA_HT_PASSWORD` are set.
- **Tests:** `test_sign_in_through_huoneistotieto_returns_the_estateapp_token` fails if a step sends the wrong fields,
  takes the wrong part of the link, or returns the wrong token.
- **Model:** Opus.
- **Constraints:** no behavior change when `RAKSA_HT_EMAIL` is unset.
