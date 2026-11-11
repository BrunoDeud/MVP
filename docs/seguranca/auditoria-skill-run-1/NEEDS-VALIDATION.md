# NEEDS-VALIDATION — MVP run-1

Pistas fundamentadas no código cuja validação decisiva está bloqueada. **Sem severidade**: nenhuma é uma vulnerabilidade confirmada. Ordem = prioridade sugerida para validação. Conteúdo dos registros copiado de `findings.json` (em inglês, como produzido pelos verificadores).


## NV01. Email verification token returned in API response lets anyone activate an account for an institutional address they do not control

- **Fingerprint:** `app.py:register-resend-verification-url-returned-in-response`

POST /api/register and POST /api/resend-verification put the one-time activation link (verification_url, which carries the secret token) in the JSON response sent to the unauthenticated caller, whether or not SMTP delivery succeeded. Anyone who can reach the API can register any address on an active allowlisted institutional domain, activate it through GET /api/verify-email without access to that mailbox, and then log in as that institutional identity. Because email is unique (case-insensitive), the real mailbox owner then gets 409 when trying to register. Resend has the same problem for accounts that are not Ativo: knowing only the email, a caller gets a fresh token, which also replaces the token that was emailed; that token activates a Pendente account, though the caller does not learn its password. Verify requires status Pendente, so Suspenso accounts cannot be reactivated this way. Real-world reach depends on who can reach port 8000: the bind host is the constant 127.0.0.1, so without a proxy or port-forward only local users can.

**Causa alegada:** The register and resend handlers build the verification link and always include it in send_json (app.py:926, 938) instead of sending it only to the mailbox. The domain allowlist (app.py:912-915) checks only the email's domain, not that the caller controls the mailbox. The documented local-mode-only behaviour, and the frontend's choice to show the link only when verification_email_sent is false, are not enforced on the server.

**Trace:**

1. `entrypoint` — `app.py:904` (Handler.do_POST /api/register): Unauthenticated JSON body with attacker-chosen name, email and password (with matching password_confirmation)
2. `propagation` — `app.py:914` (Handler.do_POST /api/register): Allowlist check matches the email's domain exactly against active institutional_domains; it does not prove mailbox control
3. `propagation` — `app.py:918` (Handler.do_POST /api/register): Secret verification token generated with secrets.token_urlsafe(32), expiring in 24 h, and stored on the new Pendente account (lines 919-921)
4. `propagation` — `app.py:926` (Handler.do_POST /api/register): verification_url containing the token is returned to the requester in the 201 response, even when send_email returned True
5. `propagation` — `app.py:938` (Handler.do_POST /api/resend-verification): Freshly minted token (lines 933-934) for any non-Ativo account looked up by email alone is returned in the response
6. `sink` — `app.py:696` (Handler.do_GET /api/verify-email): Any holder of a valid, unexpired token for a Pendente account sets status='Ativo' and email_verified=1, which activates the account

**Evidências:**

- `app.py:926` — send_json includes 'verification_url': link whatever the value of the delivered flag
- `app.py:938` — Resend response includes 'verification_url': link for an account selected only by email; the only refusal is for accounts already Ativo (line 932)
- `app.py:949` — Login is refused only while email_verified is 0 or status is Pendente, so a token-activated account can log in
- `app.py:654` — current_user accepts sessions for Ativo and verified rows, so the activated identity has full Estudante access
- `app.py:31` — HOST is the constant 127.0.0.1, so reach beyond local users depends on a proxy or port-forward that the source does not show
- `docs/api/api-local.md:19` — Docs say register returns verification_url in local mode, but the code returns it in every mode
- `test_app.py:127` — Existing test activates an account using only the token parsed from the register response's verification_url

**Bloqueios:**

- No OS-enforced sandbox on this host, so the bounded local request sequence (register with SMTP stubbed so delivered is True, GET verify-email with the returned token, then login) cannot be executed in this run, and no artifact can be promoted
- Network exposure depends on deployment: HOST is the constant 127.0.0.1 (app.py:31), so whether anyone other than local users can reach the API (reverse proxy, port-forward, or a changed HOST) is not visible in source, and that decides real-world reach and likelihood

**Validação local (sandbox):** In an OS-enforced sandbox with no network, a temporary DB and a loopback-only ephemeral port, use the test_app.py fixture server. (1) With SMTP env unset, POST /api/register for dummy address probe1@campus.edu.br and assert 201 with verification_url. (2) Stub app.send_email to return True and repeat with probe2@campus.edu.br; assert verification_email_sent is true and verification_url is still present. (3) GET the returned URL and expect 200; then POST /api/login with that password and expect 200 with a token. (4) Register probe3@campus.edu.br, then from a separate client POST /api/resend-verification with only that email; assert the returned URL activates it (GET 200) and the original token now returns 400. Regression test for the fix: neither response contains verification_url or the token unless an explicit dev-only flag is set.

**Verificação pelo responsável (sem tráfego de auditoria):** Owner confirms whether any running instance exposes port 8000 beyond the local machine (reverse proxy, port forwarding, or a modified HOST) and whether ENCONTREI_SMTP_HOST/FROM are configured there; no audit traffic is sent to any deployment.

## NV02. Unlimited guessing of a found item's private verification answer

- **Fingerprint:** `app.py:claims:verification-answer-unlimited-attempts`

Any logged-in verified, active student who does not own a found item ('Achado', status 'Aberto' or 'No ponto de guarda') can fetch its verification question (GET /api/items/{id}/verification-question) and resubmit POST /api/items/{id}/claims as often as they like. A wrong answer returns a distinct 400 ('Resposta não confere...') and changes nothing: no counter, delay, lockout or notification. Both stored and submitted answers go through norm() (trim, collapse whitespace, casefold), and answers are free text of up to 250 characters, often a single word such as a colour or brand, so guessing them is practical. A correct guess inserts a 'Pendente' claim and notifies the owner (and moderators for guard-point items) exactly as a genuine claim would. This weakens the ownership proof the claim workflow depends on, although a human decider still has to approve the claim before hand-over.

**Causa alegada:** The ownership-proof comparison at app.py:983 (norm(item['verification_answer']) != response) has no per-claimant or per-item attempt accounting, and the mismatch path raises an explicit 400 without recording anything. The only throttle in the server is LOGIN_ATTEMPTS, applied solely to /api/login (app.py:941-944).

**Trace:**

1. `entrypoint` — `app.py:792` (Handler.do_GET /api/items/{id}/verification-question): An authenticated non-owner (current_user requires an active, verified account) receives the verification question for a found item with status Aberto or No ponto de guarda (lines 793-797).
2. `propagation` — `app.py:974` (Handler.do_POST /api/items/{id}/claims): The session user is resolved with current_user() and the submitted answer is normalized with norm().
3. `propagation` — `app.py:983` (Handler.do_POST /api/items/{id}/claims): The normalized stored and submitted answers are compared. A mismatch raises APIError(400) with no state written and no counter or lockout, so the request can be repeated without limit.
4. `sink` — `app.py:986` (Handler.do_POST /api/items/{id}/claims): On a match a Pendente claim is inserted (lines 986-987). The owner is notified (line 990), and moderators too for guard-point items (line 991).

**Evidências:**

- `app.py:983` — A mismatch raises APIError(400, 'Resposta não confere. Confira os detalhes e tente novamente.') with no state change and no attempt accounting.
- `app.py:47` — norm() strips, collapses whitespace and casefolds, which removes case and spacing from the guess space.
- `app.py:1182` — The stored answer is norm()-ed free text. The only constraints are that it is non-empty and at most 250 characters (line 1186), so no minimum entropy is enforced.
- `app.py:802` — The owner/staff claim listing returns id, status, created_at, routed_to_moderation and claimant_name, but not the submitted answer or any count of failed attempts.
- `app.py:942` — LOGIN_ATTEMPTS throttling (8 per minute per IP+email) is the only rate limit in app.py and applies only to /api/login.

**Bloqueios:**

- No OS-enforced sandbox on this host (no network deny, read-only mounts or resource limits), so app.py and test_app.py cannot be executed. Source shows no attempt limit, but it cannot be observed locally that repeated wrong answers keep returning 400 without throttling until a correct guess returns 201.

**Validação local (sandbox):** In an approved sandbox (network denied, temporary SQLite DB, scratch-only writes, short wall-clock limit), start the server with test_app.py's fixture pattern on an ephemeral loopback port. Log in as a seeded verified student who does not own seeded found item 1. GET /api/items/1/verification-question and expect 200 with a question. Send 20 POST /api/items/1/claims requests with JSON {"answer":"<wrong word N>"}, then one with the seeded correct answer. The candidate is vulnerable if every wrong attempt returns 400 'Resposta não confere', none returns 429 or a lockout, the final request returns 201 with a claim_id, and GET /api/items/1/claims as the owner shows a Pendente claim with no indication of the failed attempts. Regression after a fix: attempts beyond N per claimant and item return 429 and are recorded.

## NV03. A moderator can suspend an Administrador through the report-based auto-suspension path, skipping the admin-only status control

- **Fingerprint:** `app.py:report-upheld-auto-suspension-no-target-role-guard`

Only an admin can change an account's status directly: PATCH /api/admin/users/{id}/status calls require_admin (app.py:1333). The RN18 auto-suspension in POST /api/profile-reports/{id}/decision (app.py:1097-1116) and POST /api/reports/{id}/decision (app.py:1071-1096) needs only require_moderator, which accepts Moderador or Administrador (app.py:660-662). Both routes set users.status='Suspenso' and drop the target's in-memory tokens without checking the target's role. They also let a moderator decide reports that the same moderator filed. A Moderador plus two other verified accounts can each file a profile report against an Administrador (POST /api/users/{id}/reports, app.py:1059-1070, which has no role check on the target). When the moderator marks all three 'Procedente', the admin is suspended, and current_user then rejects the admin with 403 (app.py:654-656). Only another admin can reverse this, or the startup seed reset if the target is a seed account (app.py:343).

**Causa alegada:** The suspension side effect in the moderator-gated report-decision routes writes users.status='Suspenso' directly, with no check on the target's role and no check that the deciding moderator did not file the report. This gives a second path, behind a weaker permission (require_moderator), to a state change that the dedicated route restricts to require_admin.

**Trace:**

1. `entrypoint` — `app.py:1059` (Handler.do_POST /api/users/{id}/reports): Any authenticated Ativo+verified user, the moderator included, files a profile report against any user id. Only self-reporting is blocked (1062), and the target's role is not checked.
2. `propagation` — `app.py:1099` (Handler.do_POST /api/profile-reports/{id}/decision): Only current_user + require_moderator are enforced. There is no check that report.reporter_id differs from the deciding moderator.
3. `propagation` — `app.py:1111` (Handler.do_POST /api/profile-reports/{id}/decision): The count + item_count >= 3 threshold is evaluated without considering the target's role.
4. `sink` — `app.py:1112` (Handler.do_POST /api/profile-reports/{id}/decision): UPDATE users SET status='Suspenso' on the target, which can be an Administrador. Lines 1113-1114 then remove its tokens.

**Evidências:**

- `app.py:1333` — The direct status-change route requires require_admin.
- `app.py:1345` — The admin route blocks an admin from suspending their own account, which shows intent to protect admin access.
- `app.py:660` — require_moderator accepts both Moderador and Administrador, so the decision routes are open to moderators.
- `app.py:654` — current_user rejects any non-Ativo account with 403, so the suspended admin is locked out.
- `app.py:1092` — Variant: the item-report decision path suspends the item owner after 3 upheld reports, also with no role check.
- `app.py:243` — UNIQUE(target_user_id, reporter_id) means 3 distinct reporters are needed: the moderator plus two other verified accounts.
- `app.py:343` — Only seed accounts are reset to Ativo on restart. Any other admin stays suspended until another admin intervenes.
- `docs/requisitos/regras-de-negocios.md:22` — RN18 says only 'Usuário' with 3 upheld reports is suspended. It does not say whether staff are exempt.
- `docs/api/api-local.md:105` — Documents status changes as an Administrador-only operation.

**Bloqueios:**

- No OS-enforced sandbox on this host, so target code may not be executed to observe the suspension end to end.
- Product intent is unconfirmed: neither the source nor the docs say whether Moderador/Administrador accounts are exempt from RN18 auto-suspension, or whether a moderator may decide reports they filed. The owner must confirm that moderators should not be able to suspend administrators.

**Validação local (sandbox):** In an approved sandbox with a temporary DB (test_app.py-style fixture, loopback ephemeral port, SMTP env unset): log in as the seed moderator. Register and verify two new students on an allowlisted domain. Each of the three POSTs /api/users/{admin_id}/reports with a 5+ character reason. As the moderator, POST /api/profile-reports/{id}/decision with decision 'Procedente' and a note on all three reports. Expected: the admin's existing token gets 401 from GET /api/me, a fresh admin login gets 403 ('Conta inativa ou suspensa'), and users.status for the admin is 'Suspenso' in the temp DB.

**Verificação pelo responsável (sem tráfego de auditoria):** The owner confirms whether moderators may suspend Moderador or Administrador accounts through upheld reports (and decide reports they filed themselves), or whether RN18 should apply only to Estudante targets and suspending staff should stay admin-only.

## NV04. Return confirmation moves a moderation-hidden item to the public Resolvido state

- **Fingerprint:** `app.py:claim-transitions:item-status-unchecked`

POST /api/claims/{id}/returned sets the linked item to Resolvido without checking the item's current status. If an owner's found item is hidden by moderation (moderator decision 'Ocultar anúncio', app.py:1082, or auto-hide after 3 distinct reporters, app.py:1053-1054) while a claim already exists (claims can only be created while the item is Aberto or No ponto de guarda, app.py:979), /decision (app.py:999-1012) still approves a Pendente claim because it never looks at the item status, and /returned (app.py:1034-1040) checks only owner-or-staff and claim status Aprovada before overwriting items.status with Resolvido. Resolvido items are open to anonymous callers: GET /api/items?status=Resolvido lists them (app.py:751-754) and GET /api/items/{id} is restricted only for Oculto (app.py:790), so the hidden content is published again. The owner can supply the claimant with a second account of their own. Undoing this takes a fresh report and a moderator re-hide; neither the owner nor an admin can delete the item once claims or reports exist (app.py:1375-1377). For guard-point items /decision and /returned require a moderator (app.py:1001, 1037), so an owner can abuse this only on non-guard items.

**Causa alegada:** The claim lifecycle routes trust claim state alone and never re-check the parent item's state. /returned (app.py:1038-1040) unconditionally writes items.status='Resolvido' even though it selects item_status at app.py:1034. /decision (app.py:999-1012) approves Pendente claims on items in any status, Oculto included. The sibling /resolve route requires Aberto or No ponto de guarda (app.py:1025).

**Trace:**

1. `entrypoint` — `app.py:1030` (Handler.do_POST /api/claims/{id}/returned): An authenticated owner of a non-guard found item calls /returned for an approved claim on that item.
2. `propagation` — `app.py:1036` (Handler.do_POST /api/claims/{id}/returned): Only owner-or-staff (1036), the guard-point moderator requirement (1037) and claim status Aprovada (1038) are checked. item_status is selected at 1034 but never checked.
3. `propagation` — `app.py:1040` (Handler.do_POST /api/claims/{id}/returned): An unconditional UPDATE sets the item's status to Resolvido, replacing Oculto.
4. `sink` — `app.py:751` (Handler.do_GET /api/items search): status=Resolvido items are listed to anonymous callers (only Oculto requires a moderator at 752-753). The detail view at 790 hides only Oculto.

**Evidências:**

- `app.py:1040` — UPDATE items SET status='Resolvido' with no status precondition.
- `app.py:1082` — The moderator decision 'Ocultar anúncio' sets Oculto without cancelling or touching existing claims.
- `app.py:1054` — The 3-reporter auto-hide sets Oculto without touching existing claims.
- `app.py:1003` — /decision checks only that the claim is Pendente; it never checks item status.
- `app.py:979` — Claim creation requires item status Aberto or No ponto de guarda, so the claim must exist before the item is hidden.
- `app.py:790` — Detail access is restricted only for Oculto.
- `app.py:1025` — /resolve requires Aberto or No ponto de guarda; /returned is the weaker sibling path to Resolvido.
- `app.py:1377` — Deletion is refused once claims or reports exist, even for an administrator.

**Bloqueios:**

- No OS-enforced sandbox exists on this host (no WSL, Docker or bwrap, and no network-deny with read-only mounts). Executing app.py or test_app.py is prohibited in this run, so the end-to-end transition from Oculto to anonymously visible Resolvido via /returned cannot be observed locally.

**Validação local (sandbox):** Run in an approved sandbox with a temp DB and no network. 1) Student A creates a non-guard Achado item with a verification question. 2) Student B posts the correct answer to /api/items/{id}/claims, creating a Pendente claim. 3) A moderator hides the item: report it as student C, then POST /api/reports/{rid}/decision with 'Ocultar anúncio'; confirm anonymous GET /api/items/{id} returns 404. 4) A POSTs /api/claims/{cid}/decision with Aprovada, then /api/claims/{cid}/returned. Vulnerable if both return 200, anonymous GET /api/items/{id} then returns 200 with status Resolvido, and the item appears in anonymous GET /api/items?status=Resolvido. Regression after the fix: /decision (approval) and /returned return 409 while the item is Oculto.

## NV05. Item reports can hide a resolved, expired or guarded item, and a moderator's dismissal then reopens it as Aberto

- **Fingerprint:** `app.py:item-report-dismissal-restores-aberto-ignoring-prior-status`

POST /api/items/{id}/reports loads the item through item_row, which has no status filter, so verified users who do not own an item can report it whatever its status: Resolvido, Expirado or No ponto de guarda. When three distinct reporters have pending reports, the handler sets status='Oculto' and does not store the earlier status. The moderator then has two choices, and both cause harm. 'Ocultar anúncio' keeps the item hidden and records an upheld report against the owner, which counts toward automatic suspension (lines 1089-1092). 'Manter anúncio' on every pending report sets the item to 'Aberto' whatever its status was before. A resolved or expired item reopened this way shows up again in the default public search (contrary to RN16) and gets a fresh updated_at, so the 60-day expiry restarts. If the item is an Achado with no approved claim, it accepts new claims again (line 979). A guard-point item leaves 'No ponto de guarda', so guard-retention expiry (line 584, RN11) stops applying to it, and no API path puts it back into that status. The owner or a moderator can re-resolve the item through /resolve, which partly limits the damage. Impact is limited to the integrity of the item lifecycle and listing visibility. The attack needs three verified non-owner accounts plus the moderator's dismissal.

**Causa alegada:** The item-report handler accepts reports for items in any status and, at the 3-reporter threshold, overwrites status with 'Oculto' without saving the previous status. The report-dismissal path restores a hard-coded 'Aberto' instead of the status the item had before it was hidden.

**Trace:**

1. `entrypoint` — `app.py:1044` (Handler.do_POST /api/items/{id}/reports): Route for item reports. Line 1046 requires an authenticated, active, verified user through current_user.
2. `propagation` — `app.py:1048` (Handler.do_POST /api/items/{id}/reports): item_row loads the item without a status condition. The only checks are the owner self-report check (1049) and the per-reporter UNIQUE check (1050-1051).
3. `propagation` — `app.py:1054` (Handler.do_POST /api/items/{id}/reports): When 3 or more distinct reporters are pending (1052-1053), the item status is overwritten with 'Oculto'. The previous status is not recorded anywhere.
4. `propagation` — `app.py:1083` (Handler.do_POST /api/reports/{id}/decision): When a moderator chooses 'Manter anúncio' and item_status is 'Oculto', the handler counts the item's remaining pending reports (1084).
5. `sink` — `app.py:1085` (Handler.do_POST /api/reports/{id}/decision): With no pending reports left, the handler runs UPDATE items SET status='Aberto' regardless of the status before the auto-hide.

**Evidências:**

- `app.py:670` — item_row only raises 404 for a missing row and does not restrict status.
- `app.py:1053` — The auto-hide threshold COUNT(DISTINCT reporter_id) >= 3 has no condition on item status.
- `app.py:1085` — The restored status is hard-coded to 'Aberto'.
- `app.py:1090` — The alternative decision, 'Ocultar anúncio', counts the report as upheld against the owner toward suspension at 3 (1091-1092), so the moderator cannot keep the original status without penalizing the owner.
- `app.py:750` — The default public search (status Aberto) lists items whose status is 'Aberto' or 'No ponto de guarda', so a reopened item becomes publicly listed.
- `app.py:979` — Claims are accepted for Achado items in 'Aberto', which a reopened item now is, unless an approved claim exists (980-981).
- `app.py:584` — Guard-retention maintenance selects only items in 'No ponto de guarda', so a reopened guard item escapes retention expiry.
- `app.py:573` — The 60-day expiry is keyed on updated_at, which the restore at 1085 refreshes.
- `docs/requisitos/regras-de-negocios.md:20` — RN16: resolved or expired items must not appear in public searches.
- `docs/requisitos/regras-de-negocios.md:18` — RN14: auto-hide only 'until moderator review', which implies the review should not change the item's lifecycle status.

**Bloqueios:**

- No OS-enforced sandbox on this host (no network-deny, read-only mounts or resource limits) and no no-follow artifact promotion, so app.py/test_app.py cannot be executed to observe the Resolvido/No ponto de guarda -> Oculto -> Aberto transition. Source analysis alone shows the path, but the observed result needed for confirmed is unavailable in this run.

**Validação local (sandbox):** In an approved sandbox, using the test_app.py temp-DB and loopback-port pattern with SMTP env unset: (1) Seed one owner, three verified non-owner students and one moderator. (2) The owner creates an Achado item with a photo and a verification question, then calls POST /api/items/{id}/resolve; assert GET /api/items/{id} returns status 'Resolvido'. (3) Each student calls POST /api/items/{id}/reports with {"reason":"teste de denuncia"}. (4) Assert the item status is 'Oculto'. (5) The moderator calls POST /api/reports/{rid}/decision with {"decision":"Manter anúncio","note":"sem fundamento"} for all three report ids. (6) Assert GET /api/items/{id} returns status 'Aberto', the item appears in GET /api/items, and POST /api/items/{id}/claims with the correct answer from a fourth student returns 201. (7) Repeat with a moderator-created guard item and expect the final status 'Aberto' instead of 'No ponto de guarda'. Use only temp files and dummy accounts.

## NV06. Seed accounts with published passwords are force-reactivated on every start, undoing suspensions

- **Fingerprint:** `app.py:init_db:seed-accounts-reactivated-on-start`

init_db seeds four fixed-password accounts, one of them an Administrador (admin@campus.edu.br / Admin@12345). The passwords are published in README.md and in the login UI (index.html:31). When a seed email already exists, init_db runs UPDATE users SET status='Ativo', email_verified=1 for it on every start. An admin suspension (PATCH /api/admin/users/{id}/status) or an automatic suspension after three upheld item or profile reports is therefore silently reverted at the next restart. The code has no password-change route and never updates password_hash outside insert, so suspension is the only in-app control that can disable these publicly known credentials, and it does not survive a restart. Exposure is limited by the loopback-only bind (app.py:31).

**Causa alegada:** The else-branch of the seed loop in init_db overwrites status and email_verified for seed accounts that already exist, when it should only insert accounts that are missing. As a result the moderation outcome stored in users.status does not persist across restarts for accounts whose credentials are public.

**Trace:**

1. `entrypoint` — `app.py:1394` (main): main() calls init_db() unconditionally on every server start.
2. `propagation` — `app.py:336` (init_db seed loop): Iterates the four fixed seed users (lines 330-335), including admin@campus.edu.br with Admin@12345 and lucas@campus.edu.br with Lucas@12345.
3. `sink` — `app.py:343` (init_db seed loop else-branch): For an existing seed email, UPDATE users SET status='Ativo',email_verified=1 WHERE email=? overwrites any 'Suspenso' previously written at line 1092, 1112 or 1346.

**Evidências:**

- `app.py:343` — Unconditional reactivation and re-verification of existing seed accounts on every init_db run.
- `app.py:1346` — An admin suspension writes users.status='Suspenso' and drops in-memory tokens. The value is persisted, but line 343 reverts it on restart.
- `app.py:1092` — Automatic suspension after three upheld item reports writes the same users.status column.
- `app.py:1112` — Automatic suspension after three upheld profile and item reports writes the same users.status column.
- `app.py:950` — Login rejects only when status != 'Ativo'. After the reset, the published seed password logs in again (password check at 948). password_hash is written only at inserts (340, 920), so no route changes it.
- `README.md:128` — Publishes the Administrador seed credentials admin@campus.edu.br / Admin@12345 (other seed accounts at lines 123-127).

**Bloqueios:**

- No OS-enforced sandbox is available on this host (no network deny, read-only mounts or resource limits), so init_db and the HTTP server cannot be executed to observe a suspended seed account return to Ativo and log in after a restart.

**Validação local (sandbox):** In an approved sandbox with a temp DB path and SMTP env unset: (1) call init_db(). (2) Set users.status='Suspenso' for lucas@campus.edu.br, either directly in the temp DB or as admin via PATCH /api/admin/users/{lucas_id}/status with {"status":"Suspenso"}. (3) Confirm that POST /api/login as lucas@campus.edu.br / Lucas@12345 returns 403. (4) Call init_db() again (simulating a restart). (5) Read users.status for lucas@campus.edu.br and POST /api/login again. Vulnerable: status is 'Ativo' and login returns 200 with a token. Fixed: status stays 'Suspenso' and login returns 403.

## NV07. Loopback API accepts any Host header, so a DNS-rebinding page can drive it with the published seed admin credentials

- **Fingerprint:** `app.py:Handler:missing-host-validation-dns-rebinding-loopback-api`

The server's only access boundary is its bind to 127.0.0.1:8000 (app.py:31, 1396). No handler reads or checks the Host or Origin header; the only header-related policy code is do_OPTIONS (676-681). If the operator visits a hostile web page while the demo is running, that page could rebind its hostname to 127.0.0.1 on port 8000 and become same-origin with the local API. It could then POST /api/login with admin@campus.edu.br / Admin@12345 (seeded with that fixed password and forced back to Ativo/verified on every start at 342-343; published in README.md:128 and as a one-click login button in index.html:31), read the bearer token from the JSON response (951-952), and call admin routes such as GET /api/admin/users, which returns every account's email (887-890), and PATCH /api/admin/users/{id}/role|status (1331-1352) against the operator's local database. The attacker's origin cannot read the operator's own token in localStorage; the impact relies on the public seed credentials and on anonymous routes. Whether the attack works depends on browser resolver and Private Network Access protections, which the source cannot show.

**Causa alegada:** The Handler dispatches every request no matter what Host or Origin header it carries; there is no allowlist such as 127.0.0.1:8000 or localhost:8000. The loopback bind is treated as enough isolation even though the seeded administrator credentials are public and the account is reactivated on every start.

**Trace:**

1. `entrypoint` — `app.py:1396` (main): ThreadingHTTPServer bound to (HOST, PORT) = ('127.0.0.1', 8000); any local browser context, including a rebound attacker hostname that resolves to 127.0.0.1, can reach it.
2. `propagation` — `app.py:899` (Handler.do_POST): Dispatches on urlparse(self.path).path only. No Host or Origin header is read, and body_json (626-638) parses the body without checking Content-Type.
3. `propagation` — `app.py:951` (Handler.do_POST /api/login): Valid credentials mint a 12-hour bearer token, returned in the JSON body at 952, which a same-origin page can read.
4. `propagation` — `app.py:333` (init_db): Seeds the administrator admin@campus.edu.br with the fixed password Admin@12345. On later starts, 342-343 force status='Ativo' and email_verified=1.
5. `sink` — `app.py:889` (Handler.do_GET /api/admin/users): After current_user and require_admin (888), returns id, name, email, role, status, email_verified and created_at for every user. The admin role and status changes are at 1331-1352.

**Evidências:**

- `app.py:31` — HOST, PORT = "127.0.0.1", 8000; the loopback bind is the only network boundary.
- `app.py:676` — do_OPTIONS sends Allow and Access-Control-Allow-Methods/Headers only. No handler reads Host or Origin anywhere in app.py; the only Host-related code is HOST, used to build links.
- `app.py:330` — Seed user list with fixed plaintext passwords, including Administrador (333).
- `index.html:31` — The login modal shows a one-click button that calls fillLogin('admin@campus.edu.br','Admin@12345').
- `README.md:128` — README publishes the Administrador credentials admin@campus.edu.br / Admin@12345.

**Bloqueios:**

- Decisive browser behavior cannot be seen in the source: whether current browsers' DNS-rebinding resolver protections and Private Network Access / Local Network Access enforcement on public-to-loopback requests stop a rebound public origin from completing same-origin fetches to 127.0.0.1:8000.
- No OS-enforced sandbox is available on this host, so the target server cannot be started locally to observe how it handles a foreign Host header. Source review alone already shows it never checks Host.

**Validação local (sandbox):** In an approved sandbox, run the server against a temporary database on an ephemeral loopback port with SMTP environment variables unset. Send POST /api/login with the header 'Host: rebind.example:PORT', Content-Type text/plain, and body {"email":"admin@campus.edu.br","password":"Admin@12345"}. Then send GET /api/admin/users with 'Authorization: Bearer <token>' and the same foreign Host. Vulnerable result: 200 with a token, then 200 with the user list. Expected result after a fix that rejects any Host outside {127.0.0.1:PORT, localhost:PORT}: 400 or 421 for both requests.

**Verificação pelo responsável (sem tráfego de auditoria):** The owner checks this in the browsers used for the demo, against a dummy instance with a temporary database and a local DNS-rebinding harness (no third-party service): whether a page loaded from a public-looking origin, whose hostname then rebinds to 127.0.0.1:8000, can complete a same-origin fetch to /api/login and read the response, or whether Private Network Access or the resolver's rebinding protection blocks it.

## NV08. Unauthenticated login requests permanently retain attacker-chosen keys in LOGIN_ATTEMPTS

- **Fingerprint:** `app.py:Handler.do_POST:/api/login:LOGIN_ATTEMPTS-unbounded-key-retention`

POST /api/login builds its rate-limit key from the client IP plus the raw, length-unchecked email field and stores that key in the process-global LOGIN_ATTEMPTS dict before any user lookup or password check; nothing ever removes stale keys. Each request with a new email string (bounded only by the 24 MiB MAX_BODY) adds an entry that stays for the life of the process, so a requester who can reach the server without authenticating can keep growing the memory of the single shared server process, which can degrade or crash it for every user until it restarts. The per-key limit of 8 attempts per 60 s does not apply because every key is new. The only source-visible containment is the hardcoded 127.0.0.1 bind; whether a lower-trust party (another local user or process, or a web page driving simple cross-origin text/plain POSTs, which body_json accepts because it never checks Content-Type) can reach the server in a real deployment is not visible in source.

**Causa alegada:** Login rate-limit state is keyed by unvalidated, unbounded user input: the email is not passed through text_value(..., 6, 190) as it is in register and resend-verification. The dict also has no expiry sweep and no global size bound; old timestamps are filtered only when the same key is looked up again, and maintenance() never touches LOGIN_ATTEMPTS.

**Trace:**

1. `entrypoint` — `app.py:899` (Handler.do_POST): Unauthenticated POST handler; reads the body via body_json at line 902 before any authentication.
2. `propagation` — `app.py:634` (Handler.body_json): Reads and parses up to MAX_BODY (24 MiB) of JSON with no Content-Type check and no per-field length bound.
3. `propagation` — `app.py:940` (Handler.do_POST /api/login): email = str(data.get('email','')).strip().lower() with no length or format validation.
4. `propagation` — `app.py:941` (Handler.do_POST /api/login): Rate-limit key is client_address[0] + ':' + email, so the whole attacker-supplied string becomes part of the key.
5. `sink` — `app.py:944` (Handler.do_POST /api/login): LOGIN_ATTEMPTS[client] = attempts stores the key in a module-global dict before the user lookup at 945 and the password check at 948; the entry is never removed.

**Evidências:**

- `app.py:36` — LOGIN_ATTEMPTS = {} is a process-global dict shared by all request threads.
- `app.py:32` — MAX_BODY = 24 MiB is the only bound on the size of the email field.
- `app.py:906` — Register limits email to 190 characters via text_value (resend-verification does the same at 928); login at 940 does not.
- `app.py:942` — Timestamps older than 60 s are filtered only when the same key is looked up again; the key itself is never deleted.
- `app.py:565` — maintenance() (565-598) expires items and routes claims but never cleans LOGIN_ATTEMPTS.
- `app.py:31` — The server binds to the constant 127.0.0.1:8000, so who can reach it depends on local access or browser-originated requests.
- `app.py:676` — do_OPTIONS sends no Access-Control-Allow-Origin, so preflighted cross-origin requests fail; simple text/plain POSTs are not preflighted and body_json still parses them.

**Bloqueios:**

- No OS-enforced sandbox on this host: target code (app.py) may not be executed, so per-request key retention and memory growth could not be observed locally.
- Reachability depends on the deployment and the browser: HOST is the hardcoded 127.0.0.1. Source does not show whether any deployment rebinds HOST, adds a proxy or port forward, or whether the operator's browser lets a public origin send simple no-cors text/plain POSTs to http://127.0.0.1:8000 (Private Network Access policy).

**Validação local (sandbox):** Inside an approved OS-enforced sandbox with loopback only, an empty environment, a temp ROOT/DB as in test_app.py setUpClass, and a low memory limit such as 256 MiB: start ThreadingHTTPServer(('127.0.0.1', 0), Handler). Send 3 POST /api/login requests, each with a distinct 64 KiB email and a wrong password. Assert each returns 401, len(app.LOGIN_ATTEMPTS) == 3, and every key is longer than 64 KiB. Then patch time.time forward 120 s, send one login for an unrelated short email, and assert the 3 original keys are still present (4 entries total). Stop there; do not stress the server.

**Verificação pelo responsável (sem tráfego de auditoria):** The owner confirms (1) whether the running service is ever reachable beyond loopback (HOST edited, reverse proxy, port forward, shared multi-user host), and (2) whether the browser the operator uses lets a page from a public origin send a no-cors text/plain POST to http://127.0.0.1:8000/api/login, checked with a harmless test page the owner controls.

## NV09. PATCH item photo replacement writes files before validation and never cleans them up on failure

- **Fingerprint:** `app.py:Handler.do_PATCH:/api/items:photo-write-before-validate-orphan-files`

When the owner of an open item PATCHes /api/items/{id} with a photos array, each photo is written to UPLOAD_DIR with a random name as soon as that photo passes its own checks (app.py:1270), before the later photos and the location are validated (catalog_ids at app.py:1272). If a later step fails (an unknown or inactive location, APIError 400 at app.py:409-413; an invalid later photo, APIError 400; or a non-object array element, AttributeError at app.py:1263 which becomes a 500 via app.py:1364), connect() rolls back the DB transaction (app.py:85-87) but the files already written stay on disk unreferenced and nothing removes them: old-photo cleanup (app.py:1275-1280) runs only on success and maintenance() (app.py:565-598) has no uploads sweep. PATCH has no per-user rate limit or storage quota, unlike create_item's limits (app.py:1201-1204), so a verified user owning one open item can repeat a failing PATCH carrying three photos of up to 5 MiB each and leave up to about 15 MiB of orphaned files per request. A failed PATCH does not update updated_at, so the item stays Aberto only until the 60-day expiry (app.py:573). UPLOAD_DIR and the SQLite data directory both sit under ROOT (app.py:27-29), so filling the disk can also affect database writes. The concurrent-PATCH race claimed by the hunter is not established from source and is not part of this record.

**Causa alegada:** Handler.do_PATCH interleaves per-photo validation with disk writes (write_bytes at app.py:1270) and validates catalog/location only afterwards (app.py:1272), with no try/except to remove newly written files when a later check fails, unlike create_item, which validates every photo into 'prepared' before any write (app.py:1188-1199, 1220-1224). Nothing provides garbage collection for unreferenced uploads or a per-user quota on PATCH uploads.

**Trace:**

1. `entrypoint` — `app.py:1236` (Handler.do_PATCH): Parses the path, reads the JSON body (<=24 MiB via body_json) and requires an authenticated active, verified user (current_user).
2. `propagation` — `app.py:1243` (Handler.do_PATCH /api/items/{id}): Owner check (1243) and status=='Aberto' check (1244). Text fields and the category are validated (1245-1253) before photos; location is only length-checked here.
3. `propagation` — `app.py:1262` (Handler.do_PATCH photo loop): Iterates photos_in (list of at most 3, 1257). Each element is validated individually for mime, base64, size and magic bytes (1263-1269).
4. `propagation` — `app.py:1270` (Handler.do_PATCH photo loop): write_bytes of each photo to UPLOAD_DIR inside the loop, before later elements and the location are validated.
5. `propagation` — `app.py:1272` (Handler.do_PATCH): catalog_ids raises APIError 400 for an unregistered or inactive location after the files were written.
6. `sink` — `app.py:85` (connect): The exception rolls back the DB transaction and propagates to the handler (1359-1364). Written files stay unreferenced on disk, and the cleanup at 1275-1280 is skipped.

**Evidências:**

- `app.py:1270` — Random-named file written per photo inside the validation loop.
- `app.py:409` — catalog_ids looks up the location; it raises APIError 400 when the location is missing (411) or inactive (413).
- `app.py:1263` — image.get on a non-dict element raises AttributeError after earlier photos were written; the generic handler returns 500 (1364).
- `app.py:1189` — create_item validates all photos into 'prepared' before any write (sibling control absent in PATCH).
- `app.py:1201` — create_item enforces 10 open / 5 per day; PATCH has no equivalent quota or rate limit.
- `app.py:1275` — Old-photo unlink cleanup runs only after a successful transaction; there is no cleanup of newly written files on failure.
- `app.py:565` — maintenance() expires items and routes claims; it has no sweep of unreferenced files in UPLOAD_DIR.
- `app.py:32` — MAX_BODY 24 MiB and MAX_PHOTO 5 MiB (33) admit three ~5 MiB photos per request.
- `app.py:28` — UPLOAD_DIR = ROOT/uploads and DB_PATH under ROOT/data (27-29), so they are likely on the same volume.

**Bloqueios:**

- No OS-enforced sandbox on this host (no network-deny, read-only mounts or resource limits), so target code may not be executed and orphaned files in UPLOAD_DIR after a failed PATCH could not be observed locally.
- Requires an authenticated, verified active user who owns an open (Aberto) item; how easily such an account can be obtained (in-band verification link) is covered by a separate record.

**Validação local (sandbox):** Inside an approved sandbox (no network, temp copy of the repo so ROOT/UPLOAD_DIR/DB are scratch, small disk quota, wall-clock limit), register and verify a dummy student, then create an open Perdido item with a registered location. Record the file count in UPLOAD_DIR. Send PATCH /api/items/{id} with three minimal valid PNG data URLs and location='local-inexistente'. Assert a 400 response, photos_json unchanged and exactly 3 new files in UPLOAD_DIR. Then send PATCH with photos=[valid PNG, "x"] and assert a 500 response with exactly 1 new unreferenced file. Stop there; do not attempt disk exhaustion.

**Verificação pelo responsável (sem tráfego de auditoria):** Owner checks whether the deployed uploads directory shares a filesystem volume with data/encontrei.sqlite3, and whether any external disk quota, per-user upload limit or periodic cleanup of unreferenced uploads exists. Observe only configuration; send no audit traffic.
