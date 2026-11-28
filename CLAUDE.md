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
- `auth_attempts` (TTL-indexed) holds rate-limit counters (`core/rate_limit.py`): 20 failed
  logins per account / 15 min (no per-IP login limit — shared IPs locked everyone out), 5 code emails per address / hour, 20 per IP.
  A 429 says the real time left ("Please wait 7 minutes") and sends `Retry-After`.
  Client IP: the browser calls Render directly and Render's side appends 2 X-Forwarded-For entries
  (its Cloudflare edge, its load balancer), so the client is `TRUSTED_PROXY_HOPS` (default 2, env
  override) entries from the right. Failed logins log `ip=`/`xff=` plus `auth login failed: wrong password` / `no account with that email|username`.
- **Sign-in is a Bearer token, not a cookie.** Login, `register/verify` and `change-password`
  return `access_token` in the response body; the frontend keeps it in `localStorage`
  (`api/token.js`) and `api/client.js` sends `Authorization: Bearer <token>` on every request
  (and saves any `access_token` in a response). `core/deps.get_current_user` reads only that
  header. No cookies: the frontend (Cloudflare Pages) and the API (Render) are different sites,
  and Safari / incognito / Brave drop cross-site cookies, which caused a login loop. Logout just
  forgets the token on this device; "log out everywhere" bumps `token_version`. A 401 clears the
  stored token. Without a stored token the app doesn't call `/auth/me` at all.
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
- **The browser calls the backend on Render directly** (`VITE_API_URL`, required for production
  builds — `vite.config.js` fails the build without it; in dev it's unset and Vite proxies `/api`).
  There is no proxy: an earlier Cloudflare Pages Function proxy broke waking — Render's edge
  answered requests from Cloudflare's servers with a bare 429 and never started the sleeping
  backend. Render's free plan sleeps after ~15 idle minutes; a direct request from a browser is
  held by Render while it starts and then answered, so nothing is retried or re-sent (and writes
  carry no Idempotency-Key). A request pending over 5s shows a "Waiting for the server…" banner
  (`api/slowRequests.js`, `components/ServerStatus.jsx`); the signing page shows a similar notice.
  Render's health check calls `/health`.
- Only a 401 from `/auth/me` signs someone out (`AuthContext`); any other failure shows a "Can't
  reach the server — Try again" screen. Never add a code path that treats "no response" as
  "signed out" or "wrong password".
- CORS + cross-site guard: the API answers only `settings.allowed_origins` (CORS, no credentials), and `main.py` also rejects POST/PUT/PATCH/DELETE whose `Origin` isn't in that list. Add any new frontend domain to `FRONTEND_URL`/`allowed_origins` or its requests will fail.
- User search text is `re.escape`d before Mongo `$regex`.

### CatalogItem (`catalog_items` — admin-managed customer-form dropdowns)
```
_id, type (dealer/inverter_make/inverter_capacity/panel_company/panel_watt), value, key (lower-cased value; unique per type),
warranty (makes only, e.g. "10 YEAR"), active, created_by, created_at, updated_at
```
- Seeded on startup when a list is empty (`seed_catalog` in `core/database.py`; defaults in `models/catalog.py`).
- Customers store a make/dealer's *text* (and capacity/watt as numbers matched through the item's text), so items are never renamed/deleted — only hidden (`active: false`). The form always keeps a customer's current value as an option.
- The server checks every customer choice field against active items (`services/catalog_rules.py`); a customer may keep its current value unchanged — one later hidden, or one that was never in the list (old data) — since the edit form sends every field back.
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
INVERTER_SR_NO                                 — comma-separated text ("A1, A2, A3"); set on the customer
  form (Solar System) or the Installations page. Panel serial numbers are no longer collected
  (old customers may still carry PANEL_SR_NO; nothing reads it).
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
- `GET  /api/documents/download/{customer_id}/links` — the same bundle as short-lived R2 links
  (`{name, url, stamp_url?}`); the browser downloads them, puts the stamp page in front of the NP
  Agreement (pdf-lib) and zips them (fflate) — `utils/directDownload.js`. The server-built `/zip`
  is only the fallback. Upload previews (`/uploads/{id}/{kind}/link`) and the NP first page
  (`.../np-first-page/link`) open R2 links too. Why: Render bills every byte the API sends out;
  R2 downloads are free. Keep new file downloads on links, never streamed through the API.

### Signing
- `POST /api/signing/send-link/{customer_id}`   — generate token + send email
- `GET  /api/signing/verify/{token}`            — load signing page data
- `POST /api/signing/send-otp/{token}`          — send OTP to customer phone
- `POST /api/signing/verify-otp/{token}`        — verify OTP
- `POST /api/signing/submit/{token}`            — submit signature + photos
- `GET  /api/signing/status/{customer_id}`      — check signing status
- `GET  /api/signing/download/{token}/links`   — signed bundle as R2 links (signing page zips them;
  `/signing/download/{token}` is the fallback). With `R2_PRESIGNED_REVIEW` on, `verify` gives each
  document a `url`, and the stamped NP Agreement `parts` (stamp + agreement links) to join in the page.

---

## Document Templates

(DCR is not generated — the admin uploads the government portal DCR PDF.)

Location: `backend/DOCS/`

| Key | File |
|-----|------|
| Annexure_1 | TEMPELATE_Annexure.docx |
| Aadhar | Aadhar.docx |
| WCR | WCR.docx |
| Annexure_3 | Annexure-3-Net-Metering.docx |
| NP_Agreement | np_agreement.docx |

Placeholder format in templates: `${FIELD_NAME}$`

How values print is decided only in `backend/app/services/formatting.py` (used by document
generation and the Customer Details sheet): dates DD-MM-YYYY, money `1,50,000`, kW/watts as
plain numbers (`3.3` — the templates carry the unit text), guarantees `10 YEAR`.

---

## Key Conventions

- All API responses follow `{ success: bool, data: ..., message: str }` format
- JWT sent as `Authorization: Bearer` from `localStorage` (no cookies — see Authentication)
- Generated docs folder: `generated_docs/{mongo_id}_{sanitized_consumer_name}/`
- Signing links: `/sign/{unique_token}` — token expires in 72 hours
- OTP / account codes: 6-digit, valid for 10 minutes
- Frontend uses `#1a3a2a` as primary accent color (matching existing signing page)
- All dates stored as ISO strings in MongoDB, formatted DD-MM-YYYY in documents
- "Today" defaults use India's day, never the server's UTC day: `core/localtime.local_today()` on
  the server, local date parts (not `toISOString()`) in the browser

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

Frontend (Cloudflare Pages project settings, Production + Preview; build fails without it):
```
VITE_API_URL=https://autofill-blgf.onrender.com
```
Leave it unset locally: `npm run dev` proxies `/api` to the local backend.

---

## Development Notes

- Back up / wipe / restore customer data with `backend/scripts/customer_data.py`
  (`export [--with-files]`, `delete --backup DIR`, `import --backup DIR [--dry-run]`).
  Backups go to `backend/backups/` (gitignored — they contain customer data). Import
  converts old free-text values to the typed format.
- PDF conversion uses LibreOffice headless (`libreoffice --headless --convert-to pdf`) — works on Windows and Linux.
- Generated files stored in Cloudflare R2 (S3-compatible). Never commit customer data.
- Render's free plan includes 5 GB/month of outbound bandwidth for the whole workspace (answers
  to browsers + data the server pushes to R2/MongoDB/Brevo; incoming data is free). Keep bytes off
  Render: `core/compression.py` gzips JSON/text answers only (PDFs and zips pass through), the CORS
  check is cached 2 h (`max_age=7200`), the installation photo is stored at ≤1600 px and Aadhaar
  photos at ≤1000 px. `R2_PRESIGNED_REVIEW=true` (after `python scripts/configure_r2_cors.py`) makes
  the signing page load documents straight from R2. Tests: `backend/tests/test_bandwidth.py`.
- Templates in `DOCS/` are committed to the repo (no customer data in them).
- MongoDB Atlas free tier (M0) supports up to 512 MB — sufficient for metadata. Files stored in R2, not MongoDB.
- Deployment: Frontend → Cloudflare Pages (static, no Functions), Backend → Render web service, DB → MongoDB Atlas.
