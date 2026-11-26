# CLAUDE.md — Solar Document Automation Platform

## Project Overview

A full-stack web application to manage solar installation customers, auto-generate regulatory documents (DOCX + PDF), and collect customer signatures/photos through a dedicated signing portal.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite + Tailwind CSS |
| Backend | FastAPI (Python 3.11+) |
| Database | MongoDB Atlas (cloud, free tier) |
| Auth | JWT (python-jose + bcrypt) |
| Doc Generation | python-docx + LibreOffice headless (cross-platform PDF) |
| Email (codes, signing links) | Brevo transactional API (`services/mailer.py`) |
| File Storage | Cloudflare R2 (10 GB free, S3-compatible) |
| Signing Page | Existing HTML page (UI/signing-page.html) integrated into frontend routing |

---

## Project Structure

```
/
├── frontend/               # React + Vite app
│   ├── src/
│   │   ├── pages/          # Login, Dashboard, CustomerList, SigningPage
│   │   ├── components/     # Navbar, CustomerModal, CustomerTable, etc.
│   │   ├── api/            # Axios client and API calls
│   │   ├── context/        # Auth context
│   │   └── utils/
│   └── index.html
│
├── backend/                # FastAPI app
│   ├── app/
│   │   ├── main.py
│   │   ├── core/           # config, security, database connection
│   │   ├── routers/        # auth, customers, documents, signing
│   │   ├── models/         # Pydantic models + MongoDB schemas
│   │   └── services/       # doc_generation, otp, email, pdf_annotate
│   ├── DOCS/               # DOCX templates (moved from root)
│   ├── generated_docs/     # Output folder (gitignored)
│   └── requirements.txt
│
├── UI/                     # Existing signing page HTML
│   └── signing-page.html
│
└── CLAUDE.md
```

---

## Database Models

### User
```
_id, email (lower-case, unique), username (lower-case, unique; a-z 0-9 . _ -, 3-30, starts
with a letter, never contains "@"), password_hash, name,
roles[] (admin/data_entry/installation/documents), is_active, email_verified, email_verified_at,
token_version (int; in every JWT as "ver"), password_changed_at, created_at, updated_at
```

### Authentication (`routers/auth.py`)
- **No account exists until its email is proven.** `POST /auth/register` stores a pending
  sign-up in `auth_codes` and emails a 6-digit code; `POST /auth/register/verify` creates the
  user only if the code is right. Forgot password and email change use the same code mechanism.
- `auth_codes`: one live code per (purpose, subject), only an HMAC of the code is stored,
  10-minute code, 5 wrong guesses then it's discarded, 60s resend cool-down, TTL-indexed.
- Login takes `identifier` (email or username; anything containing "@" is an email).
- `auth_attempts` (TTL-indexed) holds rate-limit counters (`core/rate_limit.py`): 10 failed
  logins per account / 15 min, 50 per IP, 5 code emails per address / hour, 20 per IP.
  Client IP: Render appends the last X-Forwarded-For entry; with the frontend's `/api` proxy (Pages Function) in
  front, the client is `TRUSTED_PROXY_HOPS` (default 1) entries before it (0 = no proxy).
- Bumping `token_version` signs out every device (password reset/change, "log out everywhere").
  `get_current_user` rejects tokens whose `ver` doesn't match.
- bcrypt always runs off the event loop (`hash_password_async` / `verify_password_async`), and
  unknown users are checked against a dummy hash so timing doesn't reveal accounts.
- Forgot password answers the same whether or not the account exists.
- Accounts from before usernames existed must pick one (blocking screen); unverified emails get
  a banner linking to `/account`. Startup lower-cases stored emails (`_migrate_user_emails`).
- Emergency reset on the server: `python scripts/reset_password.py <email-or-username> [--make-admin]`.
- Without `BREVO_API_KEY` and with a localhost `FRONTEND_URL`, emails (with codes) are printed
  to the console instead of sent. `EMAIL_DNS_CHECK=false` disables the domain check.
- Every rejected `/api/auth/*` request logs its reason (`auth POST … -> 400: <message>`), and a
  failed email logs Brevo's own error text. Check email setup with
  `python scripts/send_test_email.py you@example.com` (prints Brevo's error if it fails).
- Auth tests: `backend/tests/test_auth.py`.

### Roles & access (RBAC)
- Defined in `backend/app/core/permissions.py`: roles map to permissions; a user's permissions are the union of their roles. No roles = pending (welcome page only).
- **admin**: everything + Users page + "Dealers & Equipment" lists (`catalog:manage`) + the Inventory card on the Installations page (`inventory:manage`). **data_entry**: create customers, list/view/edit only ones they created (`created_by`). **installation**: installations page, steps + payments (no inventory). **documents**: all customers, edit, generate/print/upload/send/download.
- Every endpoint uses `Depends(require(P.SOMETHING))`. `backend/tests/test_permissions.py` fails if any `/api` route lacks one (except the public allowlist). Run: `python -m unittest discover -s tests` from `backend/`.
- Customer visibility is enforced in the Mongo query via `customer_scope()`; out-of-scope ids return 404. Responses are trimmed per role (`customer_to_out`).
- Frontend reads `permissions` from `/auth/me` (`utils/access.js`) only to show/hide UI. Pending users get a standalone `/welcome` page with no Layout/Navbar.
- **The browser only talks to the frontend's own domain.** The frontend is on Cloudflare
  Pages; the Pages Function `frontend/functions/api/[[path]].js` forwards `/api/*` to Render
  (`https://autofill-blgf.onrender.com`, or the `BACKEND_URL` Pages variable) and
  `public/_routes.json` limits functions to `/api/*` (`vite.config.js` does the same in dev), and `api/client.js` always uses
  `/api`. That keeps the auth cookie first-party — Safari and incognito drop third-party
  cookies, which caused a login loop. Never point the app at the Render domain again; if the
  backend URL changes, set `BACKEND_URL` in the Pages project (or update the default in the function). (The public signing page `frontend/public/signing.html`
  uses tokens, not cookies, and still calls Render directly.)
- CSRF: the auth cookie is `SameSite=None`, so `main.py` rejects POST/PUT/PATCH/DELETE whose `Origin` isn't in `settings.allowed_origins`. Add any new frontend domain to `FRONTEND_URL`/`allowed_origins` or its writes will 403.
- User search text is `re.escape`d before Mongo `$regex`.

### CatalogItem (`catalog_items` — admin-managed customer-form dropdowns)
```
_id, type (dealer/inverter_make/inverter_capacity/panel_company/panel_watt), value, key (lower-cased value; unique per type),
warranty (makes only, e.g. "10 YEAR"), active, created_by, created_at, updated_at
```
- Seeded on startup when a list is empty (`seed_catalog` in `core/database.py`; defaults in `models/catalog.py`).
- Customers store a make/dealer's *text* (and capacity/watt as numbers matched through the item's text), so items are never renamed/deleted — only hidden (`active: false`). The form always keeps a customer's current value as an option.
- The server checks every customer choice field against active items (`services/catalog_rules.py`); a customer may keep a value that was later hidden.
- Values are normalised (`"7 kW"`, `"550"`) because inventory groups stock by exact text.
- Frontend reads them via `useCatalog()` (`context/CatalogContext.jsx`); there are no hard-coded option lists.

### Customer (typed fields + metadata)
Defined in `backend/app/models/customer.py` — every value is stored with a real type so
MongoDB can sort, filter and calculate on it. Never store numbers or dates as free text.
```
_id, CONSUMER_NAME, CONSUMER_ADDRESS, CONSUMER_EMAIL,
CONSUMER_PHONE (10 digits), CONSUMER_AADHAR (12 digits), CONSUMER_NO (no spaces, unique index),
DEALER_NAME, INVERTER_MAKE, PANEL_COMPANY      — active catalog item (exact text)
SYSTEM_COST, AGREEMENT_SYSTEM_COST             — whole rupees (int)
SOLAR_CAPACITY, SANCTIONED_CAPACITY, INVERTER_CAPACITY — kW (float); inverter capacity must be in the catalog
PANEL_WATT (int, must be in the catalog), NO_OF_PANEL (int)
CONSUMER_APP_DATE, SUBSIDY_APP_DATE            — "YYYY-MM-DD", validated
CONSUMER_APP_NO, SUBSIDY_APP_NO (subsidy portal application; only on the Customer
  Details sheet — documents use CONSUMER_APP_NO/DATE), INSTALLATION_CITY,
INSTALLATION_DISTRICT, DISCOM_REGISTERED_OFFICE — text
INVERTER_SR_NO, PANEL_SR_NO                    — comma-separated text ("A1, A2, A3")
Derived by the server on every save (never sent by the client):
  TOTAL_PANEL_CAPACITY (W = watt × panels), INVERTER_GUARANTEE / PANEL_GUARANTEE (years, from the make's catalog warranty),
  INSTALLATION_DATE (from the Inverter / Solar Panel checklist steps)
installation_steps[], received_payments[] (each {amount: int rupees, date: "YYYY-MM-DD"}),
doc_status (none/generating/complete), signing_status (none/sent/signed),
signing_token, signing_token_expiry, r2_prefix, created_by, created_at, updated_at
```
- Blank values are stored as `null`, never `""`.
- Meter details (testing date, receipt no., generation meter make/no.) are no longer collected —
  the Meter Testing Letter was retired. Old customers may still carry those keys; nothing reads them.
- Inventory (`models/inventory.py`) tracks only solar panels and inverters.
- AGREEMENT_SYSTEM_COST is documents/admin only and is the amount printed on documents;
  SYSTEM_COST is the real price for payments and must never appear in a template.
- Payment status / paid % are **not stored**: `payment_info()` (Python) and
  `PAYMENT_EXPRESSIONS` (MongoDB pipeline) in `models/installation.py` compute them from
  SYSTEM_COST + received_payments; a test checks the two agree.
- Validation errors come back as one readable sentence in `detail` (handler in `main.py`).

### SigningSubmission
```
_id, customer_id, token, otp, otp_verified, signature_image, photos[],
submitted_at, ip_address
```

---

## API Routes

### Auth
- `POST /api/auth/login`             — `{identifier, password}` (email or username)
- `POST /api/auth/logout`
- `POST /api/auth/logout-all`        — sign out every device
- `GET  /api/auth/me`                — includes username, email_verified, roles + permissions
- `POST /api/auth/register`          — step 1: emails a code; creates nothing
- `POST /api/auth/register/verify`   — step 2: `{email, code}` → creates the user (no roles)
- `POST /api/auth/forgot-password`   — `{identifier}`; always the same answer
- `POST /api/auth/reset-password`    — `{identifier, code, password}`
- `POST /api/auth/change-password`   — logged in; `{current_password, new_password}`
- `PUT  /api/auth/me/username`
- `POST /api/auth/me/email`          — `{email, password}`: emails a code (new or current address)
- `POST /api/auth/me/email/confirm`  — `{code}`: sets the email + marks it verified

### Users (admin only)
- `GET /api/users`                   — list users + available roles
- `PUT /api/users/{id}`              — set `roles[]`, `is_active`, `email` (→ unverified), `username`

### Catalog (dealer & equipment dropdowns)
- `GET  /api/catalog`                — all lists (incl. hidden items, flagged); any customer-form/installations user
- `POST /api/catalog`                — add `{type, value, warranty?}` (admin)
- `PUT  /api/catalog/{id}`           — change `warranty` / `active` (admin)

### Customers
- `GET    /api/customers`         — list with search + pagination + `sort`
  (newest/oldest/name/app_date_desc/app_date_asc/cost_desc/cost_asc/capacity_desc)
- `POST   /api/customers`         — create new customer
- `GET    /api/customers/{id}`    — get one
- `PUT    /api/customers/{id}`    — update
- `DELETE /api/customers/{id}`    — delete

### Documents
- `POST /api/documents/generate/{customer_id}`  — trigger doc generation
- `GET  /api/documents/status/{customer_id}`    — check status
- `GET  /api/documents/download/{customer_id}`  — zip download all docs

### Signing
- `POST /api/signing/send-link/{customer_id}`   — generate token + send email
- `GET  /api/signing/verify/{token}`            — load signing page data
- `POST /api/signing/send-otp/{token}`          — send OTP to customer phone
- `POST /api/signing/verify-otp/{token}`        — verify OTP
- `POST /api/signing/submit/{token}`            — submit signature + photos
- `GET  /api/signing/status/{customer_id}`      — check signing status

---

## Document Templates

Location: `backend/DOCS/`

| Key | File |
|-----|------|
| Annexure_1 | TEMPELATE_Annexure.docx |
| Aadhar | Aadhar.docx |
| WCR | WCR.docx |
| Annexure_3 | Annexure-3-Net-Metering.docx |
| NP_Agreement | np_agreement.docx |
| DCR | DCR.docx |

Placeholder format in templates: `${FIELD_NAME}$`

How values print is decided only in `backend/app/services/formatting.py` (used by document
generation and the Customer Details sheet): dates DD-MM-YYYY, money `1,50,000`, kW/watts as
plain numbers (`3.3` — the templates carry the unit text), guarantees `10 YEAR`.

---

## Key Conventions

- All API responses follow `{ success: bool, data: ..., message: str }` format
- JWT tokens stored in httpOnly first-party cookies (not localStorage), via the `/api` proxy
- Generated docs folder: `generated_docs/{mongo_id}_{sanitized_consumer_name}/`
- Signing links: `/sign/{unique_token}` — token expires in 72 hours
- OTP / account codes: 6-digit, valid for 10 minutes
- Frontend uses `#1a3a2a` as primary accent color (matching existing signing page)
- All dates stored as ISO strings in MongoDB, formatted DD-MM-YYYY in documents

---

## Environment Variables

Backend `.env`:
```
MONGODB_URI=mongodb+srv://...
JWT_SECRET=your_secret_key        # 32+ random chars: python -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_EXPIRE_HOURS=24
BREVO_API_KEY=xkeysib-...          # Brevo > SMTP & API > API keys
FROM_EMAIL=you@yourdomain.com      # must be a verified sender in Brevo
FROM_NAME=Solar Docs Platform
BASE_URL=http://localhost:8000
FRONTEND_URL=http://localhost:5173
```

Frontend: no env vars needed (`VITE_API_URL` is no longer read — `/api` is proxied).

---

## Development Notes

- Back up / wipe / restore customer data with `backend/scripts/customer_data.py`
  (`export [--with-files]`, `delete --backup DIR`, `import --backup DIR [--dry-run]`).
  Backups go to `backend/backups/` (gitignored — they contain customer data). Import
  converts old free-text values to the typed format.
- PDF conversion uses LibreOffice headless (`libreoffice --headless --convert-to pdf`) — works on Windows and Linux.
- Generated files stored in Cloudflare R2 (S3-compatible). Never commit customer data.
- Templates in `DOCS/` are committed to the repo (no customer data in them).
- MongoDB Atlas free tier (M0) supports up to 512 MB — sufficient for metadata. Files stored in R2, not MongoDB.
- Deployment: Frontend → Cloudflare Pages (+ one Pages Function for `/api`), Backend → Render web service, DB → MongoDB Atlas.
