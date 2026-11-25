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
| OTP Delivery | Gmail SMTP via `fastapi-mail` (free, App Password auth) |
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
_id, email, password_hash, name, roles[] (admin/data_entry/installation/documents), is_active, created_at
```

### Roles & access (RBAC)
- Defined in `backend/app/core/permissions.py`: roles map to permissions; a user's permissions are the union of their roles. No roles = pending (welcome page only).
- **admin**: everything + Users page. **data_entry**: create customers, list/view/edit only ones they created (`created_by`). **installation**: installations page, steps + payments. **documents**: all customers, edit, generate/print/upload/send/download.
- Every endpoint uses `Depends(require(P.SOMETHING))`. `backend/tests/test_permissions.py` fails if any `/api` route lacks one (except the public allowlist). Run: `python -m unittest discover -s tests` from `backend/`.
- Customer visibility is enforced in the Mongo query via `customer_scope()`; out-of-scope ids return 404. Responses are trimmed per role (`customer_to_out`).
- Frontend reads `permissions` from `/auth/me` (`utils/access.js`) only to show/hide UI. Pending users get a standalone `/welcome` page with no Layout/Navbar.
- CSRF: the auth cookie is `SameSite=None`, so `main.py` rejects POST/PUT/PATCH/DELETE whose `Origin` isn't in `settings.allowed_origins`. Add any new frontend domain to `FRONTEND_URL`/`allowed_origins` or its writes will 403.
- User search text is `re.escape`d before Mongo `$regex`.

### Customer (typed fields + metadata)
Defined in `backend/app/models/customer.py` — every value is stored with a real type so
MongoDB can sort, filter and calculate on it. Never store numbers or dates as free text.
```
_id, CONSUMER_NAME, CONSUMER_ADDRESS, CONSUMER_EMAIL,
CONSUMER_PHONE (10 digits), CONSUMER_AADHAR (12 digits), CONSUMER_NO (no spaces, unique index),
DEALER_NAME, INVERTER_MAKE, PANEL_COMPANY      — must be in core/catalog.py
SYSTEM_COST, AGREEMENT_SYSTEM_COST             — whole rupees (int)
SOLAR_CAPACITY, SANCTIONED_CAPACITY, INVERTER_CAPACITY — kW (float); inverter capacity from catalog
PANEL_WATT (int, from catalog), NO_OF_PANEL (int)
CONSUMER_APP_DATE, SUBSIDY_APP_DATE, METER_TESTING_DATE — "YYYY-MM-DD", validated
CONSUMER_APP_NO, SUBSIDY_APP_NO (subsidy portal application; only on the Customer
  Details sheet — documents use CONSUMER_APP_NO/DATE), INSTALLATION_CITY,
INSTALLATION_DISTRICT, DISCOM_REGISTERED_OFFICE, METER_RECEIPT_NO,
GENERATION_METER_MAKE, GENERATION_METER_NO     — text
INVERTER_SR_NO, PANEL_SR_NO                    — comma-separated text ("A1, A2, A3")
Derived by the server on every save (never sent by the client):
  TOTAL_PANEL_CAPACITY (W = watt × panels), INVERTER_GUARANTEE / PANEL_GUARANTEE (years, from catalog),
  INSTALLATION_DATE (from the Inverter / Solar Panel checklist steps)
installation_steps[], received_payments[] (each {amount: int rupees, date: "YYYY-MM-DD"}),
doc_status (none/generating/complete), signing_status (none/sent/signed),
signing_token, signing_token_expiry, r2_prefix, created_by, created_at, updated_at
```
- Blank values are stored as `null`, never `""`.
- AGREEMENT_SYSTEM_COST is documents/admin only and is the amount printed on documents;
  SYSTEM_COST is the real price for payments and must never appear in a template.
- Payment status / paid % are **not stored**: `payment_info()` (Python) and
  `PAYMENT_EXPRESSIONS` (MongoDB pipeline) in `models/installation.py` compute them from
  SYSTEM_COST + received_payments; a test checks the two agree.
- `core/catalog.py` is the only list of dealers, makes (+warranty), panel watts and inverter
  capacities. The frontend reads it from `GET /api/catalog` (`useCatalog()` in `api/catalog.js`).
- Validation errors come back as one readable sentence in `detail` (handler in `main.py`).

### SigningSubmission
```
_id, customer_id, token, otp, otp_verified, signature_image, photos[],
submitted_at, ip_address
```

---

## API Routes

### Auth
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET  /api/auth/me`                — includes roles + permissions
- `POST /api/auth/register`          — public signup, creates a pending user (no roles)

### Users (admin only)
- `GET /api/users`                   — list users + available roles
- `PUT /api/users/{id}`              — set `roles[]` and/or `is_active`

### Catalog
- `GET /api/catalog`                 — dealers, makes, panel watts, inverter capacities

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
| Meter_testing_letter | Meter Testing Letter.docx |
| DCR | DCR.docx |

Placeholder format in templates: `${FIELD_NAME}$`

How values print is decided only in `backend/app/services/formatting.py` (used by document
generation and the Customer Details sheet): dates DD-MM-YYYY, money `1,50,000`, kW/watts as
plain numbers (`3.3` — the templates carry the unit text), guarantees `10 YEAR`.

---

## Key Conventions

- All API responses follow `{ success: bool, data: ..., message: str }` format
- JWT tokens stored in httpOnly cookies (not localStorage)
- Generated docs folder: `generated_docs/{mongo_id}_{sanitized_consumer_name}/`
- Signing links: `/sign/{unique_token}` — token expires in 72 hours
- OTP: 6-digit, valid for 10 minutes
- Frontend uses `#1a3a2a` as primary accent color (matching existing signing page)
- All dates stored as ISO strings in MongoDB, formatted DD-MM-YYYY in documents

---

## Environment Variables

Backend `.env`:
```
MONGODB_URI=mongodb+srv://...
JWT_SECRET=your_secret_key
JWT_EXPIRE_HOURS=24
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your_16_char_app_password   # Gmail > Security > 2-Step > App Passwords
FROM_EMAIL=your@gmail.com
BASE_URL=http://localhost:8000
FRONTEND_URL=http://localhost:5173
```

Frontend `.env`:
```
VITE_API_URL=http://localhost:8000
```

---

## Development Notes

- PDF conversion uses LibreOffice headless (`libreoffice --headless --convert-to pdf`) — works on Windows and Linux.
- Generated files stored in Cloudflare R2 (S3-compatible). Never commit customer data.
- Templates in `DOCS/` are committed to the repo (no customer data in them).
- MongoDB Atlas free tier (M0) supports up to 512 MB — sufficient for metadata. Files stored in R2, not MongoDB.
- Deployment: Frontend → Vercel, Backend → Render or Oracle Cloud (TBD), DB → MongoDB Atlas.
