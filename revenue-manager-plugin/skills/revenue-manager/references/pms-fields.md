# PMS field reference (platform-specific parsing)

> Reference for the revenue-manager skill. Loaded on demand from SKILL.md; not part of the runbook that loads on every run.

Every supported PMS has a named calendar **write** tool — resolve it from Step 0 detection at execute time (Step 8), never default to Hospitable.

| PMS | Bookings source | Calendar read | Calendar write tool |
|---|---|---|---|
| Hostaway | `reservations` | `/listings/{id}/calendar` | `hostaway_update_calendar` (or the detected `hostaway_*` calendar mutation) |
| Guesty Pro | `reservations` | calendar endpoint | `guesty_update_calendar` (detected `guesty_*` mutation) |
| Hostfully | `leads` | calendar endpoint | detected `hostfully_*` calendar mutation |
| Hospitable | transactions for history (see below) | `hospitable_get_property_calendar` | `hospitable_update_property_calendar` |
| OwnerRez | `bookings` | calendar endpoint | detected `ownerrez_*` calendar mutation |
| Lodgify | `reservations/bookings` | calendar endpoint | detected `lodgify_*` calendar/rate mutation |
| Uplisting | reservations | calendar endpoint | detected `uplisting_*` calendar mutation |
| Smoobu | reservations (apartments) | rates endpoint | detected `smoobu_*` rates mutation |

If the detected PMS exposes no calendar-write tool, push via the pricing-tool MCP instead (PriceLabs pushes to the PMS) and say so at the approval gate.

### Hostaway
- Properties → `listings` · Bookings → `reservations`
- Reservation fields: `id`, `arrivalDate`, `departureDate`, `totalPrice`, `channelName`, `status`
- Calendar: `/listings/{id}/calendar` → `date`, `status`, `price`, `minimumStay`

### Guesty Pro
- Reservation fields: `_id`, `checkIn`, `checkOut`, `money.fareAccommodation`, `source`, `status`
- Calendar: `date`, `status`, `price`, `minNights`

### Hostfully
- Bookings called "leads" (Hostfully terminology)
- Requires `agencyUid` on every call

### Hospitable
- Calendar **read** (GROUND TRUTH for listed price): `hospitable_get_property_calendar` → `data.days[]` with `date`, `min_stay`, `status.reason` (`RESERVED`/`AVAILABLE`), `price.amount`. **`price.amount` is in cents — divide by 100.**
- Calendar **write**: `hospitable_update_property_calendar` → `price` is a plain **nightly price in dollars** (NOT cents). **Read in cents, write in dollars — convert before push** and pre-push assert the value is within min/max in native dollars (Step 8).
- **History:** `hospitable_list_reservations` returns ONLY upcoming/active reservations. For past/completed bookings, realized ADR, YoY/STLY, and channel-mix history, use `hospitable_list_transactions` (and/or `pricelabs_list_reservations`).
- PMS name inside PriceLabs is `smartbnb`
- Tools: `hospitable_get_property_calendar`, `hospitable_list_reservations` (forward/active only), `hospitable_list_transactions` (history), `hospitable_list_reviews`, `hospitable_update_property_calendar`

### OwnerRez
- Bookings → `bookings` (fields: `id`, `arrival`, `departure`, `total`, `channel`, `status`)
- Requires `User-Agent` header on every request

### Lodgify
- Bookings → `reservations/bookings` · fields: `id`, `arrival`, `departure`, `total_amount`, `source`, `status`

### Uplisting
- Auth: `Authorization: Basic <base64(api_key)>`

### Smoobu
- Properties called "apartments" · Auth header is `Api-Key` (exact case)
