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

### Customer (all 30 Excel columns + metadata)
```
_id, CONSUMER_NAME, CONSUMER_ADDRESS, CONSUMER_PHONE, CONSUMER_EMAIL,
CONSUMER_AADHAR, CONSUMER_NO, DEALER_NAME, SANCTIONED_CAPACITY, CONSUMER_APP_DATE,
CONSUMER_APP_NO, SOLAR_CAPACITY, INVERTER_MAKE, INVERTER_CAPACITY,
INVERTER_GURANTEE, INVERTER_SR_NO, PANEL_COMPANY, PANEL_WATT,
NO_OF_PANEL, TOTAL_PANEL_CAPACITY, PANEL_SR_NO, CELL_MANUFACTURER,
PANEL_GURANTEE, INSTALLATION_DATE, INSTALLATION_CITY, INSTALLATION_DISTRICT,
DISCOM_REGISTERED_OFFICE, SYSTEM_COST, METER_TESTING_DATE, METER_RECIPT_NO,
GENERATION_METER_MAKE, GENERATION_METER_NO,
AGREEMENT_SYSTEM_COST (documents/admin only; the amount printed on documents —
  SYSTEM_COST is the real price for payments and must never appear in a template),
installation_steps[], received_payments[] (each {amount, date}),
doc_status (none/generating/complete), signing_status (none/sent/signed),
signing_token, signing_token_expiry, docs_folder_path, created_at, updated_at
```

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

### Customers
- `GET    /api/customers`         — list with search + pagination
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

Date fields (formatted as DD-MM-YYYY): `CONSUMER_APP_DATE`, `INSTALLATION_DATE`, `METER_TESTING_DATE`

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
