# Calendar-aware publication alarms

PR #1 deliberately retains weekday Fargate starts even on NYSE holidays and
short sessions. The watchdog independently verifies each intended occurrence
using the same `app.session.assess_slot` calendar and the existing Terraform
cron expressions. It runs once daily at 15:20 Pacific, two hours after the
last current generation slot, including weekends. Existing generation
schedules, S3 claims, provider calls/retry limits and close-data polling are
unchanged. It uses the same image but a separate command, read-only Logs task
role, no S3 permissions and no paid-provider secrets. `enable_cloudwatch_alarms`
controls the watchdog too.

The old per-slot alarm addresses, names and notification actions are retained.
They now consume a per-occurrence 0/1 result instead of a rolling success count.
The original success and calendar-skip metrics remain for dashboards. A
separate heartbeat alarm detects absent daily checks (26 hourly periods,
allowing DST and a small delivery margin); missing result metrics alone are
not treated as success or used to infer holidays. The old
`missing_slot_alarm_period_seconds` variable is deprecated and retained for
existing tfvars compatibility. The immediate run-error alarm is unchanged.

| Status | Per-slot alarm |
|---|---|
| `published`, `expected_calendar_skip`, `weekend_no_schedule` | 0 |
| `missed_execution` (including weekday holiday tasks that never log) | 1 |
| `failed_publication` (started but no manifest success, including duplicate claim without success) | 1 |
| `missing_calendar_skip` (wrong/missing expected skip evidence) | 1 |
| `unexpected_publication` (publication on a calendar-ineligible occurrence) | 1 |

Inspect `publication watchdog result` JSON logs for slot, session date, status
and expected skip. Each result is evaluated in a one-hour CloudWatch period;
this is a notification signal, not a persistent incident ledger. CloudWatch
may retain sparse datapoints in its evaluation range. If errors occur in a
run that eventually publishes, `RunFailures` still reports them separately.

## Rollout / verification (no generation required)

1. Apply this patch to the post-PR-1 source. Run `python -m unittest tests.test_publication_watchdog tests.test_market_schedule` with the pinned
   requirements installed. Run `terraform -chdir=infra fmt -check`,
   `terraform -chdir=infra init -backend=false` and
   `terraform -chdir=infra validate`. Review a plan with the existing tfvars.
2. Build/push the normal application image containing both the watchdog module
   and the new `scheduled_at` log context before applying the infrastructure
   change. Use an explicit fresh image tag for both task definitions. Coordinate
   rollout before the first generation slot of a full audit day: old worker
   logs lack the occurrence timestamp and cannot satisfy the new check. If
   applying midday, the first check may report missing evidence from old tasks.
3. Review the plan for unchanged generation schedule times, claim IAM and
   generation task settings apart from the intended image revision. Only the
   watchdog adds a daily Fargate task, a public IP during its short run, a
   read-only log scan and four custom metrics/one additional alarm. This is
   incremental AWS cost; it does not call market data or image providers.
4. On the first completed audit day, check all three result logs and the
   heartbeat. The new heartbeat alarm can start in ALARM before its first
   datapoint; do not disable missing-data detection to silence it. Existing
   notification actions should be verified in the plan. No manual generation
   run is necessary.

The daily cutoff is intentional: an occurrence not proven published by 15:20
Pacific is reported for investigation; later completion is not a retroactive
success. Query or calendar failures fail the watchdog and leave the heartbeat
absent. The watchdog never retries generation or modifies claims. This is
log-based monitoring, not an independent S3 integrity audit.

## Local release review — November 24, 2026

Prepared on `codex/calendar-publication-alarm-release` from current master
`8fad966`. The original Library patch was 29,302 bytes with SHA-256
`3e00a2868c4e511ebe0420c8ee99284484af63723e42500b2d416b53f1abdf23`.
The original `git apply --check` failed only on `infra/variables.tf`: its hunk
assumed the monitoring variables started on line 1 of a shortened file.
All other hunks passed `git apply --check --exclude=infra/variables.tf` and
were applied unchanged. The two variable-description edits were applied
manually; variable names, defaults and values were preserved.

Verification completed:

- All 73 regression tests pass on host Python 3.13 and in the ARM64 Python 3.12
  container. Both use the repository's actual `pandas_market_calendars==5.4.0`
  and `replicate==1.0.7`, without an alternate calendar adapter. Other
  dependencies retain the ranges in `requirements.txt`; they are not fully
  locked. The host dependency snapshot is in
  `/tmp/market-river-alarm-release-dependencies.txt`.
- Additional tests exercise `app.main.main([])` with Scheduler environment
  variables and feed its serialized log records into
  `app.publication_watchdog.main()`. Market data, publication, and provider
  boundaries use local fakes. Thanksgiving skips all three slots; November 27
  publishes open/close and skips midday. Weekend, genuine miss, uncertain
  provider failure, duplicate paid claim, stale close data, query failure, and
  late-heartbeat cases are covered.
- The local image `market-river-generator:calendar-alarm-review-20261124`
  built successfully. Image ID:
  `sha256:10c8e2418443af73724175990f45bc908505514c8b858b23c18b65ef0dc05ad8`.
  The container suite ran with networking disabled. A separate invocation of
  `python -m app.publication_watchdog` in that image, also with networking
  disabled, correctly audited a past weekend without issuing a current-day
  heartbeat.
- `terraform -chdir=infra validate`, `terraform -chdir=infra fmt -check`, and
  `git diff --check` pass. Existing ignored local `terraform.tfvars` alignment
  was normalized without changing any values; its original copy is in
  `/tmp/market-river-alarm-original.tfvars`.
- Generation cron expressions, timezone, scheduled-time token, pipeline and
  session gates, claim IAM and create-only writes, and provider code and
  submission/retry protections have no changes from master.

After AWS reauthentication, a refreshed read-only plan was generated using
the existing deployment tfvars and the explicit prospective image tag
`calendar-alarm-review-20261124`. Temporary profile credentials were passed
only to the Terraform process. The plan, which does not require the tag to
exist in ECR, is saved at
`/tmp/market-river-calendar-alarm-20261124.tfplan`; its text is at
`/tmp/market-river-calendar-alarm-plan-20261124.txt`, and resource-level
verification is at
`/tmp/market-river-calendar-alarm-plan-review-20261124.txt`.

The plan proposes **12 additions, 7 updates and 1 removal**. Eleven additions
are the watchdog task/schedule, two roles and their policies, four metric
filters and one heartbeat alarm. The remaining addition and the removal are
the expected replacement of the worker task definition. Updates change the
three publication alarms, the three existing schedules' task-definition
references, and the scheduler's task-definition policy reference. Worker
container settings are unchanged except the image, apart from empty-list
serialization normalization. Generation times, timezone, schedule input and
timestamp token, network, claims, provider secrets, public reads/CORS,
immediate run-failure alarm and ECR retention are preserved.

Five refresh-only differences were reviewed: the three calendar-skip metric
filters normalize null dimensions to empty maps, and the parent task and
scheduler IAM role snapshots catch up with their separately managed inline
policies. In particular, the live paid-claim permission is present. All five
resources have no proposed action; no source changes were made to conceal
these observations. Existing alarm action and recovery-action lists are
empty and remain empty: alarm state changes currently send no notifications.

Read-only live checks confirm the existing schedules are enabled and target
worker revision 7 with image tag `calendar-e1cedd8e37fa`, digest
`sha256:08c91216be877e164f15d6c3365734cab4670e611b4a7c3d22d0691551540508`.
The prospective tag is absent from ECR, as expected at this stage. Publish
and verify the exact tested image under that tag before any future apply.
The worker and watchdog both reference that same prospective tag.

## Rollout and rollback considerations from the plan

- The worker revision is replaced in delete/create order: revision 7 is
  deregistered before its replacement is registered. Update outside all
  generation windows and allow time for schedule/policy updates to finish.
  Do not apply a plan whose image has not been published and verified first.
- Current live publication logs were confirmed to lack `scheduled_at`.
  Prefer activating before 06:45 Pacific on November 25, then verify the
  first full day's check at 15:20 Pacific. A partial day's older evidence
  cannot satisfy this watchdog. Its new heartbeat alarm may initially breach
  before the first daily completion. Do not suppress missing-data protection
  just to hide this transition.
- Retain the prior image digest throughout the rollback window; the existing
  ECR policy keeps only three images. The old worker revision will be
  inactive after replacement, so rollback should re-register the previous
  image through Terraform and update schedule references, rather than merely
  pointing Scheduler at the deregistered revision. Coordinate that rollback
  with reverting/disabling the new watchdog in Terraform: old worker logs
  alone cannot satisfy it. Review a fresh rollback plan before applying.
- Regenerate and review the release plan immediately before an authorized
  rollout, especially if deployment inputs, infrastructure, source, tag, or
  image digest change. The saved preflight plan is evidence, not authorization
  to deploy later without reviewing intervening changes.

Live execution under the new watchdog role, its Scheduler token substitution,
CloudWatch metric/alarm behavior, prospective deployed image availability,
and first-day production evidence have not been verified. These require a
separately authorized rollout followed by read-only checks. Reading logs
with the deployment profile does not prove runtime authorization for the new
watchdog role.

This stage made no GitHub or ECR pushes, no Terraform apply, no AWS workload
invocations, and no paid generation calls.

## Authorized production rollout — November 24, 2026

The separately authorized rollout proceeded after 16:29 Pacific, outside the
generation and watchdog windows, with no running ECS tasks. The tested ARM64
image was published under the unique tag
`calendar-alarm-20261124-10c8e2418443`. Its ECR manifest configuration digest
matches the tested local image ID. Published image digest:
`sha256:f15d527c51d3d3b150cf0aaf98b12a1a9e5680bb23d4bf2201d57b7bbf294cc2`.

The ignored local deployment tfvars now records that explicit release tag.
A fresh live plan matched every resource change in the reviewed preflight
exactly after substituting only the release image tag. Applying that saved
plan succeeded: **12 added, 7 changed, 1 destroyed**, with the destruction
being replacement of worker revision 7. Worker revision 8 and watchdog
revision 1 now reference the published release image.

Read-only verification confirmed:

- All three generation schedules are enabled, target worker revision 8,
  and retain their original times, timezone and exact Scheduler input.
- The daily 15:20 Pacific watchdog schedule targets its dedicated revision 1.
  The watchdog task has Logs-only runtime permissions and no injected provider
  secrets. Its task/schedule and all four new metric filters match the plan.
- The three per-slot alarms use the new calendar-aware metrics. The separate
  26-hour heartbeat alarm and immediate run-failure alarm match their intended
  definitions. Notification action lists remain empty.
- Public latest/recent feeds, a linked image and prompt metadata return
  HTTPS 200 with CORS `*`, and their sampled contents are byte-for-byte
  unchanged from the pre-apply baseline. No frontend changes are required.

At verification, the existing run-failure and three per-slot alarms were OK;
the new heartbeat alarm was INSUFFICIENT_DATA. That initial state may become
ALARM before the first completion, as documented above. No worker, watchdog
or paid generation was manually invoked, and no GitHub push or merge occurred.

The remaining runtime checks are the naturally scheduled November 25
publications beginning at 06:45 Pacific and the first watchdog at 15:20:
confirm revision 8's pulled image digest and `scheduled_at` log context, then
the watchdog's role access, resolved timestamp, three correct slot results
and completion heartbeat. November 26 should produce three verified holiday
skips; November 27 should require open/close publication and a midday skip.
These live runtime behaviors cannot be confirmed before those scheduled
executions without the manual workload invocations expressly excluded from
this rollout.

Rollback retains image tag `calendar-e1cedd8e37fa`, digest
`sha256:08c91216be877e164f15d6c3365734cab4670e611b4a7c3d22d0691551540508`.
Its continued presence in ECR was verified after deployment. The previous
image manifest, task definition, tfvars, Terraform state, exact release plan,
apply log and read-only verification records are saved locally under
`/tmp/market-river-calendar-alarm-rollout-20261124/`. Use the coordinated
Terraform rollback described above; simply targeting inactive revision 7
will not restore service. Account for the existing three-image retention
policy before any subsequent image publications.
