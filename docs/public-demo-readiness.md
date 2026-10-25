# Public demo deployment readiness

Prepared on 24 October and updated on 25 October 2026. All changes remain local. No app, volume, deployment,
commit, push, or teammate message was created. No live TinyFish or LLM call was
executed in this readiness task. Bookings remain simulated.

## What the public URL actually serves

Inspected `https://demo-booking-tau.vercel.app` using unauthenticated HTTP.
The audit was captured at 21:58 IST on 24 October 2026 in the ignored local file
`test-results/public-deployment-audit.json`.

| Path | Actual response | SHA-256 of response bytes |
| --- | --- | --- |
| `/index.html` | 200, static HTML | `69bb28e5d3417dd45ef77b53e1d497f0619dc4f63e862e70f1732ffa4789da6a` |
| `/checkout.html` | 200, unprotected static checkout | `9d71f53c57453cc5d89ee964e9ba270539ff4bebf3f593defd97f2c0524b7517` |
| `/confirmation.html` | 200, legacy URL-generated confirmation | `1d034e50d3eebf83e208927ffa857a6cb7f7a9fb1c2376a565c3d5fb8f0cccd1` |
| `/app.js` | 200 | `02d301bab9d85769fddcd38bc1f08e6c81ce916afe7366aa1140e160ef739eeb` |
| `/styles.css` | 200 | `424ecfce4bae69019b218c0ffbac21ffd37f53e31718908d2a8337b63db561f4` |
| `/checkout.js`, `/health`, `/openapi.json`, `/api/catalog`, `GET /stage`, `/version`, `/deployment.json` | 404 | No protected backend/version exposed at these paths |

All five asset bodies match repository commit
`74565878dc9237f7e43143685705e72cb67b46e4` after BOM/newline normalization.
This establishes content equivalence, not the Vercel deployment's Git metadata.
No public backend version can be identified at this origin: the API routes are
absent. No separate backend URL was configured/discovered in the repo.

Before preparation, the repo had no `vercel.json`, `.vercel/project.json`,
Dockerfile, Fly config or other deployment manifest. Vercel CLI 54.9.1 is
installed. Before the 25 October device login there was no `VERCEL_TOKEN` or
`NOW_TOKEN` environment override, no file credential, and the CLI reported no
usable saved credential. The failure was therefore local saved-auth state, not
an environment override. The official OAuth device login completed without
printing a token or credential value.

Authenticated read-only inspection verified account `pragunaggarwal36-2286`
and its only returned team/scope, ID `pragunaggarwal36-2286s-projects` (display
name `pragunaggarwal36-2286's projects`). That scope contains only `med-reach`,
`js-unboxed`, and `v0-modern-portfolio-website`. It does **not** contain the
target deployment: inspecting `demo-booking-tau.vercel.app` in that scope
returned "can't find the deployment". The repository remains unlinked
(`.vercel/project.json` is absent). The public alias and its static bytes are
observed, but its owning Vercel team, project ID, deployment ID, build settings,
Git integration, and the authority to update the alias are still unverified.
The hostname was not used to guess a project name. Do not link or deploy until
the alias owner grants this account access or performs the cutover.

## Prepared architecture and files

The existing Vercel URL proxies **all** application/UI routes to one Fly backend.
That backend serves the existing UI and owns the SQLite authority. Vercel serves
only a release descriptor itself. UI HTML/JS/CSS were not redesigned or changed
by this readiness task.

- `Dockerfile`, `.dockerignore`, `requirements-deploy.txt`: Python 3.13 app,
  pinned locally verified runtime dependencies, explicit source/UI copies, one
  Uvicorn worker. No `.env`, keys, Git metadata, local DB or recordings enter the
  image. Browser/agent execution tools are unnecessary in the public container.
- `deploy/fly.toml.template`: one always-running machine in the selected region,
  HTTPS, `/data` volume, `/data/workflow.db`, one-worker image, health check with
  an explicitly allowed Host header, and immediate deployment. No rolling
  parallel instances or independent SQLite replicas are intended.
- `scripts/prepare_deployment.py`: generates ignored `deploy/generated/fly.toml`,
  `deploy/generated/release.json`, and `.vercel/output/`. It creates no remote
  resources. The prebuilt Vercel output contains only a descriptor and full-path
  external proxy routes, with cache disabled. It refuses stale unrelated output
  rather than uploading old checkout assets or a serverless Python function.
- `app/config.py`: exact configured public/backend hostnames; no wildcard host
  match. Durable mode refuses an unmounted DB directory or Vercel Functions.
  `/stage` and `/tasks/{id}/run` are disabled on the public backend by default.
  No TinyFish/OpenAI key is required on that backend; keep operator keys local.
- `app/main.py`, `app/store.py`, `app/release.py`: no-store responses, `/version`,
  content-derived frontend/backend/release identities, a persisted SQLite
  `storage_id`, and a fresh process `instance_id`. Existing task/cart/approval/
  order semantics are preserved. Metadata is added non-destructively to existing
  DBs. The request checker receives the explicitly configured exact host set;
  `guard/request_check.py` remains deterministic, without environment/network I/O.
- `app/readiness.py`, `scripts/verify_public.py`, `app/tinyfish_client.py`:
  read-only checks require a protected checkout, healthy checker/database,
  mounted durable mode, matching proxy/backend release, exact served UI hashes,
  expected public origin and rejection of a nonexistent order. TinyFish always
  uses strict public checks; `--allow-local` is restricted to loopback and is
  never an agent-client bypass.
- `guard/contract_parser.py`: fixed raw Responses API parsing to read
  `output[].content[]` text, skip reasoning, reject refusal/incomplete output,
  and validate strict integer-money contracts. The existing `gpt-4.1-mini`
  default is preserved. One request, 10-second HTTP timeout, 1,000 output tokens.
  Failures remain `source: fallback`; successful API drafts use `source: parsed`.
- `scripts/llm_smoke.py`: separate explicit `--live` opt-in; no booking calls.
  Exit 0 means a validated API-parsed draft. Exit 1 means missing key/fallback;
  exit 2 means not opted in. It never calls a fallback a successful API parse.

Prepared ignored artifacts now use the exact proposed name
`agentguard-pragun-demo.fly.dev` and region `sin`. Public DNS did not resolve that
hostname on 25 October, but that is not an authoritative Fly name-availability
check: no Fly login or app reservation occurred. No backend at that name is
claimed. `fly apps create` must confirm and reserve it during a later authorized
provisioning; if unavailable, stop, choose a new explicit name, regenerate all
artifacts, and re-record the expected release/backend origin before continuing.

## Required deployment configuration

| Setting | Prepared value |
| --- | --- |
| Public origin | `https://demo-booking-tau.vercel.app` |
| Proposed Fly app/backend | `agentguard-pragun-demo` / `agentguard-pragun-demo.fly.dev` (not reserved) |
| Proposed region | `sin` (Singapore; not provisioned and account capacity not checked) |
| `AGENTGUARD_DEPLOYMENT_MODE` | `durable` |
| `AGENTGUARD_DB` | `/data/workflow.db` |
| `AGENTGUARD_VOLUME_PATH` | `/data`, must actually be mounted |
| Volume name | `agentguard_data`, one 1GB volume in the machine's region |
| `AGENTGUARD_ENABLE_AGENT_RUNS` | `false` |
| Machine | One `shared-cpu-1x`, 1 shared CPU, 512MB RAM, always running |
| Application worker | One Uvicorn worker; image command includes `--workers 1` |
| Keys on public backend | None required; do not upload the local `.env` |
| Operator-local keys | `TINYFISH_API_KEY`; separately `OPENAI_API_KEY` for opt-in parser smoke |

### Estimated Fly charges before provisioning

This is a pay-as-you-go estimate, not a quote or verified account invoice. Fly's
current pricing page gives a 1.269230769 Singapore multiplier. One continuously
running `shared-cpu-1x` with 512MB is approximately **US$4.69 per 30-day
month** (US$2.194128 base 256MB CPU/RAM preset + 256MB additional RAM at one
quarter of US$6.003072/GB-month, then the Singapore multiplier). The proposed
1GB volume is **US$0.15/month**, for an expected fixed subtotal of about
**US$4.84 per 30 days**, or about **US$5.00 in a 31-day month**. Machine billing
is per second and volume billing is hourly, so partial months vary.

Additional usage/assumptions:

- Singapore public-internet egress is US$0.04/GB; inbound transfer is free.
- Shared IPv4 and IPv6 are free. A dedicated IPv4 is not proposed.
- Snapshot storage is US$0.08/GB-month with the first 10GB per organization
  currently free. Seven-day retention is configured, but snapshots are not HA,
  point-in-time database consistency, or a tested restore plan. Cost can become
  nonzero if the organization-wide free snapshot allowance is already consumed.
- The first ten single-hostname certificates per organization are currently
  free. No paid support, reservation block, managed database, or static egress
  IP is proposed.
- Existing Vercel plan limits and any incremental proxy bandwidth charge cannot
  be checked until the alias-owning team is identified. No Vercel plan change is
  proposed.

Sources: [Fly resource pricing](https://fly.io/docs/about/pricing/),
[Fly public pricing and regional selector](https://fly.io/pricing/), and
[Fly regions](https://fly.io/docs/reference/regions/). Prices and capacity can
change; check them again in the authenticated Fly organization immediately
before provisioning.

Approval tokens, current carts, tasks and immutable orders all live in this same
database, not browser memory or per-instance temporary storage. URLs still
restore selections; the server ID/version/hash is the authority. A fresh browser
can recheck the persisted cart; an existing unconsumed approval survives a
backend restart. New public storage starts empty; local demo IDs/records are not
silently copied into it. Existing local data is preserved.

## Verified locally; limits

**333 combined tests passed after the origin/main integration**, including the
real Chromium, proxy, deployment, intent-gap, page-scan and scenario suites. The
full command was `python -m pytest -q -p no:cacheprovider --basetemp
test-results\pytest-integration-merge`. The ignored in-repository temporary root
avoided an unrelated Windows user-temp ACL problem.

- Generated proxy routes were exercised against a real HTTP backend. The actual
  Confirm button created a server snapshot through that proxy. Direct arbitrary
  confirmation-page navigation stayed unconfirmed.
- A real backend process was stopped/restarted between separate browser
  contexts. Cart content and approval persisted, `storage_id` stayed the same,
  `instance_id` changed, confirmation was idempotent, and the order remained
  readable after a second restart.
- Mount refusal is unit tested (the unit-test positive is mocked), and the later
  Linux container smoke used an actual bind mount recognized at `/data`. Neither
  the Windows process test nor the container bind mount is a Fly-volume test.
- Readiness rejects mixed release/UI/proxy versions, ephemeral storage, missing
  checker, missing receipt signer and unidentified DB storage. Public-host near
  misses are rejected.
- Raw API parser/refusal/fallback handling was tested with mocked HTTP only.
  Running the LLM smoke without `--live` returned `not_run`, without a call.
- The new read-only public preflight was actually run against the current URL.
  It returned `ready: false` because checkout is unprotected. No live agent ran.
- `pip check` passed; diff whitespace checks passed. One upstream
  Starlette/TestClient/httpx deprecation warning remains.

### Actual Linux container evidence (25 October 2026)

Docker Engine 29.1.3 was installed only inside the existing Ubuntu 24.04 WSL2
distribution. The repository `Dockerfile` built successfully as Linux/amd64
image `agentguard-readiness:local` (retained local image ID begins
`sha256:f1ea47dd8a89`; approximately 48.6MB). No Docker Desktop installation was
needed. The image configuration and live process table both showed exactly:

```text
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 1
```

After integration, the same Dockerfile was rebuilt as
`agentguard-integration:local` (local image ID begins `9bc33ea54208`). A bounded
startup smoke reported `protected-v2`, durable storage, `db_ok` and a configured
receipt signer; the process table again showed the exact single-worker command
above. The bind mount created exactly `/data/workflow.db`, not a filename with a
literal backslash. Only that new smoke container and its new temporary mount
directory were removed; the image was retained. The historical two-restart
persistence evidence below was not rerun inside this rebuilt image; equivalent
process-restart persistence remains covered by the passing deployment/browser
suite.

The image was run in durable mode with a real bind mount at `/data` and
`AGENTGUARD_DB=/data/workflow.db`. The retained host-side WSL evidence directory
contains only `workflow.db`; there is no filename containing a backslash. The
`/data/workflow\.db` spelling seen in pasted/Markdown-formatted command text was
escaping only. `Dockerfile`, the Fly template, generated Fly config, application
settings, deployment tests and this runbook all use exactly `/data/workflow.db`.

Observed results from the two restart checks:

- `/health` reported `db_ok`, durable SQLite, protected confirmation and the
  expected release; `/version` reported `protected-v2`.
- `storage_id` stayed stable and `instance_id` changed on each container restart.
- The current cart and its server approval survived the first restart. Reusing
  the approval returned the same simulated `order_id`, and that order survived
  the second restart.
- A made-up order ID returned HTTP 404. Direct confirmation-page navigation did
  not create an order.
- The retained database has two orders because the smoke workflow was executed
  twice. They belong to two different approvals; the maximum is one order per
  approval and there are zero duplicate-approval order groups. This is the
  database-level evidence for confirmation idempotency, not a claim that the
  entire test database contains only one historical order.

All readiness containers were stopped and removed, and the temporary WSL
keepalive ended. The image and `/var/lib/agentguard-smoke-20261024/workflow.db`
were intentionally preserved. No global Docker prune or unrelated WSL process
termination was performed.

Genuine limits/blockers:

1. Vercel authentication now works, but the authenticated account/team does not
   own or expose the target alias. The owning project/team/deployment ID, Git
   auto-deploy behavior and plan limits remain blocked on owner access. Ensure a
   later Git deployment cannot replace the proxy with the old static checkout.
2. A Fly account/organization, authoritative app-name check, region capacity,
   volume and machine have not been verified or provisioned. The Linux image is
   locally built and tested, but Fly CLI/cloud config validation and remote image
   execution have not occurred. Singapore is proposed, not guaranteed available.
3. SQLite cannot supply consistent shared authority from ephemeral Vercel
   Functions or independently scaled volumes. This plan deliberately stays at
   one persistent machine/volume. Scaling out needs a shared transactional DB
   or deliberately engineered replication. A single volume has hardware-failure
   and downtime limits; snapshots are not high availability.
4. One Machine plus one local volume is a single failure/maintenance domain.
   Fly volume snapshots are not application replication or tested recovery;
   there is no automatic failover. The demo can be unavailable during Machine,
   host, region, volume, or deployment incidents.
5. Public verification must pass after the real deployment, including actual
   restart/record checks. No Fly/Vercel deployment, live TinyFish or live LLM
   success is claimed. This remains a public simulated demo, not a production
   authenticated/payment service.

## Exact PowerShell commands

These deployment/resource-changing commands are prepared for a **later explicitly
authorized deployment**. They were not executed. Run in the repo root and stop
on any nonzero native-command exit code. Do not commit/push just to deploy.

The current Vercel login is valid for `pragunaggarwal36-2286`, but that account
cannot see the target deployment. The alias owner must either grant this account
access to the existing project/team or perform the Vercel steps. After access is
granted, verify identity before any linking. If the owner instead logs in on this
machine, use a separate global-config directory so the current credential is not
overwritten. No token is printed or passed on the command line:

```powershell
# Preferred: owner grants the current account access, then:
vercel.cmd whoami
vercel.cmd teams list
$VercelTeam = "<verified-alias-owning-team-id-or-slug>"
$VercelProject = "<verified-existing-project-id-or-name>"
vercel.cmd inspect https://demo-booking-tau.vercel.app --scope $VercelTeam --format=json
if ($LASTEXITCODE -ne 0) { throw "Target deployment is not visible; stop" }
vercel.cmd project inspect $VercelProject --scope $VercelTeam
if ($LASTEXITCODE -ne 0) { throw "Existing project identity is not verified; stop" }

# Alternative only when the owner chooses to log in locally:
$OwnerVercelConfig = Join-Path $env:TEMP "agentguard-vercel-owner"
vercel.cmd login --global-config $OwnerVercelConfig
vercel.cmd inspect https://demo-booking-tau.vercel.app --global-config $OwnerVercelConfig --scope $VercelTeam --format=json
```

Record the deployment ID, project ID/name, team ID/slug, production alias and Git
settings returned by the owner scope. Confirm the project already owns
`demo-booking-tau.vercel.app`; do not guess or create a replacement project.

Install/login to Fly only during the later authorized provisioning session, then
confirm organization access, current Singapore capacity and pricing. The exact
proposal is fixed below; the name is not reserved yet:

```powershell
iwr https://fly.io/install.ps1 -useb | iex
$env:Path = "$env:USERPROFILE\.fly\bin;$env:Path"
fly auth login
fly orgs list
fly platform regions
$FlyApp = "agentguard-pragun-demo"
$FlyRegion = "sin"
$FlyVolume = "agentguard_data"
$FlyOrg = "<verified-fly-organization-slug>"
.\.venv\Scripts\python.exe scripts/prepare_deployment.py --app $FlyApp --region $FlyRegion
if ($LASTEXITCODE -ne 0) { throw "Preparation failed" }
$Release = (Get-Content .\deploy\generated\release.json -Raw | ConvertFrom-Json).release_id
fly config validate --config .\deploy\generated\fly.toml
if ($LASTEXITCODE -ne 0) { throw "Fly configuration is invalid; stop" }
```

Provision and deploy the one durable backend (later, after authorization):

```powershell
fly apps create $FlyApp --org $FlyOrg
if ($LASTEXITCODE -ne 0) { throw "Proposed Fly name unavailable or app creation failed; stop and regenerate for any new name" }
fly volumes create $FlyVolume --app $FlyApp --region $FlyRegion --size 1 --snapshot-retention 7 --yes
if ($LASTEXITCODE -ne 0) { throw "Volume creation failed" }
$ReceiptBytes = [byte[]]::new(32)
[Security.Cryptography.RandomNumberGenerator]::Fill($ReceiptBytes)
$env:AGENTGUARD_RECEIPT_KEY = [Convert]::ToBase64String($ReceiptBytes)
"RECEIPT_KEY=$env:AGENTGUARD_RECEIPT_KEY" | fly secrets import --app $FlyApp
$ReceiptSecretExit = $LASTEXITCODE
Remove-Item Env:AGENTGUARD_RECEIPT_KEY
if ($ReceiptSecretExit -ne 0) { throw "Receipt secret configuration failed" }
fly ips allocate-v6 --app $FlyApp
fly ips allocate-v4 --shared --app $FlyApp
fly deploy . --config .\deploy\generated\fly.toml --app $FlyApp --dockerfile Dockerfile --ha=false --remote-only
if ($LASTEXITCODE -ne 0) { throw "Backend deployment failed; do not change Vercel" }
fly scale count 1 --app $FlyApp
fly machine list --app $FlyApp
fly volumes list --app $FlyApp
.\.venv\Scripts\python.exe scripts/verify_public.py --base-url "https://$FlyApp.fly.dev" --backend-only --expected-release $Release
if ($LASTEXITCODE -ne 0) { throw "Backend not ready; do not change Vercel" }
```

### Backend behavior and actual Fly restart verification

Before changing Vercel, the following runs directly against the Fly backend and
creates **one simulated order**, with explicit review of the fixed demo contract.
It calls no LLM/TinyFish. The approval stays in a local variable and is not
printed. Use a fresh PowerShell session for a subsequent independent check of
`/api/orders/{id}` if desired.

```powershell
$Public = "https://$FlyApp.fly.dev"
function Post-Json($Path, $Body) {
  Invoke-RestMethod -Method Post -Uri "$Public$Path" -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 12)
}
$Contract = @{
  route = @{from="Ludhiana";to="Delhi"}; date="2026-10-25"; quantity=1
  max_total=1000; allow_extras=$false; source="fallback"
  requirements=@{refundable=$null;seat_confirmed=$null;baggage=$null}
}
$Task = Post-Json "/tasks" @{sentence="I reviewed this fixed simulated demo contract";draft_contract=$Contract}
$Answers = @{}
foreach ($Question in $Task.questions) { $Answers[$Question.key] = "don't care" }
$null = Post-Json "/tasks/$($Task.task_id)/answers" @{answers=$Answers}
$null = Post-Json "/tasks/$($Task.task_id)/confirm" @{}
$Cart = Post-Json "/api/carts" @{scenario="s1";ticket="t1";passengers=1}
$Approval = Post-Json "/api/carts/$($Cart.cart_id)/check" @{task_id=$Task.task_id;cart=$Cart.cart}
if ($Approval.decision.result -ne "allow") { throw "No approval" }
$Before = Invoke-RestMethod "$Public/health"
fly apps restart --app $FlyApp
if ($LASTEXITCODE -ne 0) { throw "Restart failed" }
$After = $null
for ($Attempt=0; $Attempt -lt 15; $Attempt++) {
  try { $After = Invoke-RestMethod "$Public/health" -TimeoutSec 5; if ($After.db_ok) { break } } catch {}
  Start-Sleep -Seconds 1
}
if (-not $After.db_ok) { throw "Backend did not recover" }
if ($Before.storage.storage_id -ne $After.storage.storage_id) { throw "Authoritative storage changed" }
if ($Before.instance_id -eq $After.instance_id) { throw "Restart was not observed" }
$Current = Invoke-RestMethod "$Public/api/carts/$($Cart.cart_id)"
if ($Current.version -ne $Approval.version) { throw "Cart changed" }
$OrderItems = @($Cart.cart.items | ForEach-Object { @{id=$_.id;price=$_.price} })
$Body = @{task_id=$Task.task_id;approval=$Approval.approval;order_request=@{
  cart_id=$Cart.cart_id;items=$OrderItems;total=$Cart.cart.total;fields=@{}
}}
$Order = Post-Json "/api/carts/$($Cart.cart_id)/confirm" $Body
$Again = Post-Json "/api/carts/$($Cart.cart_id)/confirm" $Body
if ($Order.order_id -ne $Again.order_id) { throw "Duplicate order" }
Invoke-RestMethod "$Public/api/orders/$($Order.order_id)"
Start-Process "$Public/confirmation.html?order_id=$($Order.order_id)"
```

Also open `$Public/confirmation.html?ticket=t1&total=1000` in a separate browser
context: it must show **No confirmed order**. Exercise the existing checkout
review/check/Confirm UI as usual; it uses relative protected same-origin API
paths. Direct-backend `/version` and `/health` identify the served source and
storage; after Vercel cutover, `/deployment.json` adds the proxy expectation.
The release and storage identities are operational evidence, not receipts. Once
`RECEIPT_KEY` is configured, each task additionally exposes a signed receipt at
`/tasks/{id}/receipt` and verifies its hash chain at
`/tasks/{id}/receipt/verify`. Rotating or losing the key prevents old receipt
signatures from being reproduced, so retain it as a Fly secret and outside Git.

Only after the direct-backend readiness and restart checks pass, confirm exactly
one Machine in `sin` and its one attached 1GB volume, then cut over Vercel. Link
only the identity-verified existing project and deploy **only the prepared
prebuilt proxy**. The local link file is ignored. Do not run these commands with
the currently visible personal scope unless it has first been granted access to
the target project:

```powershell
vercel.cmd link --yes --team $VercelTeam --project $VercelProject
if ($LASTEXITCODE -ne 0) { throw "Existing project link failed" }
vercel.cmd deploy --prebuilt --prod --yes --scope $VercelTeam --project $VercelProject
if ($LASTEXITCODE -ne 0) { throw "Vercel proxy deployment failed" }
vercel.cmd inspect https://demo-booking-tau.vercel.app --scope $VercelTeam --format=json
.\.venv\Scripts\python.exe scripts/verify_public.py --expected-release $Release
if ($LASTEXITCODE -ne 0) { throw "Public preflight failed; do not run TinyFish" }
```

Do not run `vercel build` over the root Python repository: the existing SQLite
authority must not become a serverless function. The generated prebuilt output
ships no root source, secrets, local DB or old static UI. Re-run the generator
after any source/UI/lockfile edit; its expected release must match the Fly build.

### One bounded TinyFish staging command, prepared only

Keep the existing key in the operator's local `.env`. Run this command **only
after** the deployed public version passes preflight. The client checks preflight
again, requires the expected release, and permits one 120-second agent run with
no extraction retry. It stages only; it never approves or confirms an order:

```powershell
.\.venv\Scripts\python.exe scripts/verify_public.py --expected-release $Release
if ($LASTEXITCODE -ne 0) { throw "Public deployment not ready" }
.\.venv\Scripts\python.exe scripts/stage_once.py https://demo-booking-tau.vercel.app/index.html?scenario=s2 --mode live --scenario s2 --review-demo --expected-release $Release
```

This live command was not executed. A live agent may choose different valid
contents; report actual extracted data, not a forced scenario expectation.

### Separate opt-in LLM parser smoke

Use `OPENAI_API_KEY` only locally. Preserve `GUARD_LLM_MODEL` if already set;
otherwise the existing default is `gpt-4.1-mini`.

```powershell
.\.venv\Scripts\python.exe scripts/llm_smoke.py
# No API call; exit 2 and status not_run.
.\.venv\Scripts\python.exe scripts/llm_smoke.py --live
# Explicitly opts into one API call; run only when you want that test.
```

`api_parsed_draft` / `source: parsed` / exit 0 means an actual API response was
parsed and validated. `fallback_demo_contract` / `source: fallback` / exit 1 is
not API success. Refusal, incomplete output, invalid JSON/money and HTTP failure
all remain fallback. Neither result authorizes a booking. No live LLM test was
executed here; protocol tests are mocks.

### Local checks used for this preparation

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_application.py tests/test_tinyfish_client.py tests/test_models_v2.py tests/test_request_check.py tests/test_contract_parser_http.py tests/test_deployment.py tests/test_deployment_browser.py -p no:cacheprovider
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Sources: [Vercel Build Output routing](https://vercel.com/docs/build-output-api/configuration),
[Vercel rewrite caching](https://vercel.com/docs/routing/rewrites),
[Vercel SQLite limitation](https://vercel.com/kb/guide/is-sqlite-supported-in-vercel),
[Fly volume behavior](https://fly.io/docs/volumes/overview/),
[Fly deploy flags](https://fly.io/docs/flyctl/deploy/),
[OpenAI raw response text layout](https://developers.openai.com/api/docs/guides/text).
