# СПОТ Albums Implementation Plan

**Goal:** Working local public site and simple SMM album editor.
**Architecture:** Buildless frontend; same-origin Python API, SQLite and private media files.
**Tech Stack:** Python standard library, Pillow, vanilla HTML/CSS/JS.
**Spec:** docs/album-site-design.md

## Constraints
- Reuse existing footage and supplied transparent logo; black/red brand.
- Hero → events → albums → location. No portal effects.
- Durable server storage, private drafts, real original downloads.
- Local first; no account or hosting deployment until hosting is resolved.
- No Git repository exists; keep original page in /private/tmp/spot-before-albums.html.

## Review focus
- Draft photo URLs must not leak media, even when an ID is known.
- Interrupted uploads must remain recoverable and not publish automatically.
- Corrupted / huge images and invalid covers must not break an album.
- Session/CSRF expiry during upload must preserve completed photos.
- Qtickets outages must retain prior data and show its update date.

## Tasks
- [x] 1. Write and run failing integration tests for albums/auth/media and Qtickets parser.
- [x] 2. Implement store.py, qtickets.py and server.py; run all server tests.
- [x] 3. Replace index.html; implement styles.css and app.js with responsive video hero,
  dynamic events, albums, accessible dialog, viewer and original downloads.
- [x] 4. Implement admin.html/admin.css/admin.js: first-run setup/login, album fields,
  upload progress, cover choice, publish/unpublish and editing existing albums.
- [x] 5. Launch local API server, verify end-to-end upload/publish/download in browser,
  responsive layouts and reduced motion; obtain one independent code review.
- [x] 6. Document launch, deployment needs and Qtickets limitations; open the public
  site and provide the SMM editor address.

## Verification ledger
- Server unit/integration tests initially failed on missing implementations; then 10/10 passed.
- Real HTTP catalogue loaded 6 future SPOT events, including catalogue pagination.
- Browser flow passed: 3 uploads, cover choice, draft/publication, gallery, keyboard,
  original/ZIP downloads, reduced motion and public/editor responsive widths.
- Independent review identified upload-session recovery, reduced-motion manual pause,
  and first-load calendar polling issues. All fixed; browser-recovery.js passes all three.
- User clarified unlimited photo count. Removed the 500-photo cap; test crossing 500
  failed before removal and passed with 501 stored records afterward.
- Decision: local build and user-managed hosting, as confirmed by the user; no external
  deployment attempted. Original page preserved in /private/tmp/spot-before-albums.html.

- Final verification: 11/11 server tests pass; browser-flow and browser-recovery pass.

- Follow-ups complete: server-only credential JSON with username/hash and rotation invalidation; 16 tests pass.
- Typography: local Golos Text / Oswald, 48–52px buttons, Instagram restored, 2GIS destination.
- Four browser scenarios pass: auth, responsive typography/links, recovery, full album flow.

- Footer redesigned with solid/outline poster lettering, open social rows and a small closing logo; route points to the SPOT listing
  70000001110675808. Browser layout passes at seven widths (320–1440px);
  desktop/mobile footer screenshots reviewed. Opening video remains the only video.

- Posters: preserve full proportions, select the largest published signed CDN
  variant instead of 360px thumbnails. Fight poster verified at 1080×1080;
  18 server tests plus poster and responsive browser checks pass.
