# Architecture — MVP ("Encontrei"), run-1

## 1. Product, principals, resources
Campus lost-and-found web app (README.md:9). Single Python stdlib process (`ThreadingHTTPServer`, app.py:1396) with SQLite (`data/encontrei.sqlite3`, app.py:29) and a single-page frontend (index.html).

Principals:
- **Anonymous**: health/config/catalog, item search and detail (hidden items excluded, app.py:749-755, 790), `/uploads/*` (no auth, app.py:708-720), register, resend-verification, verify-email, login, logout.
- **Estudante** (verified user): create items (app.py:1173), claim others' found items by answering a private question (app.py:972-992), edit/delete own items, decide claims on own non-guard items, chat after approval, report items/users, own notifications.
- **Moderador**: moderation queues/log, guard-point items, decide any claim, confirm returns, decide reports (auto-suspension after 3 upheld).
- **Administrador**: catalog/domain/guard-point CRUD, user list (all emails), role/status changes (app.py:1331-1352), delete any item.
- **System**: maintenance thread and per-request `maintenance()` (app.py:556-598, 673).

Protected resources: account identity (institutional email), item ownership/return (verification answer is the key control), private claim chats, moderation outcomes (hide/suspend), uploaded photos, user emails (admin only).

## 2. Comparable baseline
Only source-grounded comparison is the replaced design (Laravel/Sanctum/React/MySQL, docs/ADRs/ADR-001..003). No external product baseline; omitted for calibration.

## 3. Stack, deployment, offline limits
Python 3.10+ stdlib only; no dependencies, lockfiles, CI or packaging. Bound to 127.0.0.1:8000 constant (app.py:31). Sessions = in-memory bearer tokens (12 h, app.py:35, 951) in browser `localStorage` (index.html:22,33). Optional SMTP from `ENCONTREI_SMTP_*` env (app.py:445-497).
Offline test suite `python -m unittest -v test_app.py` (31 tests, temp DB, ephemeral loopback port). **This host has no OS sandbox** (no WSL/Docker/bwrap; Windows Job Objects not packaged with network deny/read-only mounts) **and no no-follow promotion** (Node/Python lack O_NOFOLLOW/dir_fd on Windows). Therefore no target-controlled code runs in this run; any decisive runtime fact becomes `needs_validation`. Running `app.py`/`executar.bat` is prohibited (writes repo DB, opens browser); SMTP env must stay unset.

## 4. Entry surfaces and key paths
- HTTP routes in `Handler.do_GET/POST/PATCH/DELETE` (app.py:683, 899, 1234, 1366); body via `body_json` (24 MB cap, no Content-Type check, app.py:626-638).
- Account lifecycle: register → `verification_url` returned in response (app.py:923-926) → GET `/api/verify-email` (state-changing GET, app.py:688-698); resend returns a fresh link for any pending account (app.py:927-938).
- Claim lifecycle: question (792-797) → answer compare (983, distinct 400, no attempt limit) → decision (993-1018) → messages (839-849, 1152-1164) → returned (1030-1043).
- Moderation: item reports auto-hide at 3 distinct reporters (1052-1057); upheld reports suspend (1090-1095, 1107-1115).
- Photos: create_item validation (1183-1199) vs PATCH path with weaker checks and write-before-validate (1262-1271); served unauthenticated (708-720).
- Seed/startup: `init_db` seeds fixed-password accounts incl. admin (330-341) and resets them to Ativo/verified on every start (342-343).
- Frontend: all rendering via template strings into `innerHTML` with `esc()` (index.html:23); unescaped interpolations are numeric ids, dates (`formatDate`), `retention_days`.

## 5. Trust boundaries and strongest control
| Boundary | Strongest source-visible control |
|---|---|
| Anonymous → account | Domain allowlist (app.py:912-915); mailbox ownership NOT enforced (link returned in-band) |
| Credential → session | PBKDF2 + compare_digest; rate limit per IP+email (941-944) |
| Session → user/role | `current_user` re-reads row, requires Ativo+verified (640-658); `require_moderator/admin` (660-666) |
| Claimant → item ownership | normalized answer equality (983); no attempt accounting |
| Owner/staff → claim/resolve/return | inline owner/role checks (1001-1002, 1024, 1036-1037) |
| Participant → chat | owner/claimant + Aprovada (846-847, 1159-1160) |
| Users → moderation outcome | 3 distinct reporters auto-hide (1053) |
| Uploader → filesystem | mime allowlist, base64, size, magic bytes, random names; basename check on serve (709-711) |
| API data → DOM | `esc()` for strings |
| Restart → account state | seed reset overrides suspension for seed accounts (343) |

Deployment-dependent: actual network exposure, TLS/proxy, SMTP configuration, multi-process, host ACLs.

## 6. Starting paths
`app.py` (all server logic), `index.html` (client), `test_app.py` (what is/isn't tested), `executar.bat`, `.gitignore`, `docs/api/api-local.md`.

## 7. Prior coverage
No prior ledger or findings exist; this is the first run. A manual report in `docs/seguranca/` is not a ledger and is not used as evidence or as an exemplar.

## 8. Companion selection
- **WEB-PROTOCOL-AND-AUTH.md**: selected — custom HTTP server with bearer sessions, email-verification-based account creation (recovery/linking-like flow), session lifecycle.
- **CLIENT-SIDE.md**: selected — SPA rendering untrusted API data via `innerHTML`, bearer token in `localStorage`, framable pages.
- **RESOURCE-EXHAUSTION-AND-AVAILABILITY.md**: selected — unauthenticated 24 MB bodies, unbounded thread-per-connection, unbounded in-memory dicts, upload disk writes.
- Excluded: MEMORY-SAFETY (pure Python), AI-AND-LLM (no model), SUPPLY-CHAIN (no deps/CI/release), CLOUD (no IaC/containers), PROTOCOLS-RPC (HTTP/JSON only, no brokers/webhooks), DATA-ISOLATION (single-tenant; owner scoping covered by Access control units), DESKTOP-MOBILE (no native/IPC surface beyond loopback HTTP).
