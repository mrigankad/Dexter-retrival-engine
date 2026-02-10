# Implementation Notes & Fixes

## 1. Document Ingestion Pipeline Fixes
**Issue:** The ingestion worker (`ingest_worker.py`) processed documents but did not report status back to the database or UI.
**Fix:** 
- Updated `ingest_worker.py` to:
  - Connect to PostgreSQL.
  - Update `Document` status to `processing` on start.
  - Update `Document` status to `completed` + `chunks_count` on success.
  - Update `Document` status to `failed` + `error_message` on failure.
- Updated `api/ingestion_routes.py` to:
  - Create `Document` record with `pending` status.
  - Push job to Redis queue instead of using `BackgroundTasks` (ensuring worker picks it up).

## 2. API Endpoints
**Issue:** Frontend expected `/documents` endpoint to list documents, but it wasn't implemented (placeholder).
**Fix:**
- Implemented `GET /documents` in `ingestion_routes.py` with pagination and sorting.
- Implemented `GET /documents/{document_id}` to fetch single document status.
- Added `GET /ingest/files/{document_id}` to serve raw file content.

## 3. Frontend Compatibility
**Issue:** Frontend expects to display document status and list.
**Verification:**
- `DocumentsPage.tsx` polls for document status updates.
- `documentService.ts` calls the correct endpoints.
- `vite.config.ts` correctly proxies `/api` requests to backend in development.
- `nginx.conf` correctly handles `/api` proxy in production.

## 4. Next Steps
- **UI Enhancement:** Implement "View Source" functionality in `SourcePanel` using the new file serving endpoint.
- **Testing:** Verify end-to-end flow with a real file upload.
- **Deployment:** Ensure `redis` service is running and accessible by both API and Worker containers.
