# Daily aggregator and scheduler validation

Validated 2026-10-06, continuing CORE commit
`0162e70bef6742f6bb01cf84d5bee057a3e8083b`. AWS identity was verified repeatedly
as account `837873138796`, existing SSO profile `shimmer-admin`, region `us-east-2`.
Frontend, Android, Amplify, Cognito and the old server were not modified or called.

## Resources

| Resource | Deployed value |
| --- | --- |
| Stack | `shimmer-server-clone`, `UPDATE_COMPLETE` |
| API | https://wwr1eh4vg9.execute-api.us-east-2.amazonaws.com |
| Main Lambda | `shimmer-server-clone-MainApiFunction-hNr96vzCphw3` |
| Scheduler Lambda | `shimmer-server-clone-BackfillSchedulerFunction-lsQhaxFSS55L` |
| S3 bucket | `shimmer-server-clone-databucket-wn9atsyogh42` |
| File metadata table | `shimmer-server-clone-FileMetadataTable-1FARD0NWRCNXP` |
| Aggregator state table | `shimmer-server-clone-AggregatorStateTable-1ENHND3FHU6PQ` |
| New summary table | `shimmer-server-clone-AggregatedDataTable-18R2RUULV8JDF` |
| Retained former summary table | `shimmer-server-clone-AggregatedDataTable-L94O1IH4KDP` |
| EventBridge Scheduler schedule | `shimmer-server-clone-daily-backfill`, default group |

All main Lambda resource environment variables were compared against stack
outputs. Scheduler `API_BASE_URL` matches the new API exactly. No old API
hostname remains in runtime source. The core bucket, mapping/file/state tables,
main Lambda and API retained their physical identities.

## Manual aggregator: PASS

Reused the already-decoded real Shimmer fixture from CORE validation. Two
clone-only metadata copies point to that same decoded S3 object, giving three
groups for `2010-10-02`:

- `CLONE_TEST_DEVICE` / `Shimmer_CLONE`
- `CLONE_TEST_DEVICE` / `Shimmer_SECOND`
- `CLONE_AGG_DEVICE_B` / `Shimmer_CLONE`

`POST /daily-aggregator/` with `{"date":"2010-10-02"}` returned HTTP 200 and
three successful groups. The filename/metadata `date` is deliberately different
from `recordedTimestamp`; selection followed the recorded timestamp, not the
filename. Each output contained 605 averaged acceleration samples derived from
30,240 input samples, and 622 nonzero UWB samples. Every acceleration average
was checked against the source JSON within `1e-8`; date, device, shimmer,
file timestamps, output names and counts were verified.

Objects in the NEW bucket:

```text
combinedbyDay/CLONE_TEST_DEVICE_2010-10-02_Shimmer_CLONE_combined.json
combinedbyDay/CLONE_TEST_DEVICE_2010-10-02_Shimmer_SECOND_combined.json
combinedbyDay/CLONE_AGG_DEVICE_B_2010-10-02_Shimmer_CLONE_combined.json
combinedbyDay/CLONE_SCHEDULER_DEVICE_2010-10-03_Shimmer_SCHEDULED_combined.json
```

## Summary schema correction: PASS

Before replacement, three distinct same-date S3 outputs resulted in only one
summary row under the provisional `date` partition key. The existing summary
already contains `combined_s3_key` (`daily_aggregator_handler.py:454`). The new
partition key is therefore `combined_s3_key`, String, with no sort key or index.
No aggregator summary fields, grouping, decoder or output logic were changed.

CloudFormation replaced only this auxiliary table and recorded `DELETE_SKIPPED`
for its old physical table because `UpdateReplacePolicy: Retain` is set. The old
table/data remain recoverable, but it is no longer managed by this stack or used
by the Lambda. No unrelated resource was replaced or deleted. Rerunning manual
aggregation produced three coexisting summary rows for `2010-10-02`, verified
with a consistent scan matching the three S3 keys. Scheduler processing added
the fourth summary for `2010-10-03`.

## Manual scheduler and backfill correction: PASS

Added clone-only metadata `CLONE_AGG_SCHEDULER_NEXT_DAY.txt`, using the same
decoded fixture with controlled next-day metadata timestamps. The scheduler was
invoked manually while the schedule was DISABLED. CloudWatch confirmed:

```text
Calling: https://wwr1eh4vg9.execute-api.us-east-2.amazonaws.com/daily-aggregator/backfill/
API Response Status: 200
```

POST body remains `{"limit":5}`, with the original headers, 30-second connection
and 900-second read timeouts, and response/error handling. It created the
`2010-10-03` combined object shown above, its unique summary row, and state
`{"id":"last_processed_date","date":"2010-10-03"}`. All were verified in
the new bucket/tables.

The first invocation exposed an existing completed-date parser bug: it assumed
the date was the second underscore-delimited filename component. Test device
names contain underscores, so already-completed dates were processed again.
The narrow `main.py` fix scans components for the validated date and stops after
finding it. No API contracts or filename format changed. Two offline regression
tests cover both original simple names and underscore-containing names.

After deploying that fix, another manual scheduler invocation returned HTTP
200 with `processed_dates=2`, both dates recognized, `missing_dates=[]`, and
`processed=[]`. Thus recurrence will not repeatedly process these completed
test dates. Logs contain no import, IAM, DynamoDB schema, S3, missing-env or
FastAPI/Mangum errors for the inspected validation invocations.

## Recurrence

User-confirmed cadence: daily at **11:45 PM America/New_York**. SAM ScheduleV2
uses `cron(45 23 * * ? *)`, `ScheduleExpressionTimezone: America/New_York` and
`FlexibleTimeWindow: OFF`; timezone scheduling follows daylight-saving changes.
See [SAM ScheduleV2 documentation](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-property-function-schedulev2.html).

It is an EventBridge Scheduler schedule, not a legacy EventBridge rule. Only
after manual validation was the stack updated with `SchedulerState=ENABLED`.
Its target is only the new scheduler Lambda. The execution role's inline policy
allows `lambda:InvokeFunction` only for that Lambda ARN in the new account.
Automatic timed execution has not yet been observed; the first scheduled run
is due at 11:45 PM local time. Manual invocation and configuration are verified,
not a claim that a timed run has already occurred.

## Local validation and scope

`import main` resolved the Mangum handler; `sam validate`, `sam validate --lint`,
and `sam build` passed. Both built handlers and production dependencies imported
successfully. OpenAPI and route registrations still match `e638cfb`; decoder
and `daily_aggregator_handler.py` remain byte-for-byte unchanged. Scheduler
request and error-handling behavior matches baseline apart from configurable
URL/fail-closed behavior. Regression tests passed without live AWS calls.

Retained test metadata/objects are synthetic clone-only artifacts. No core
upload/decode/mapping contract rerun was necessary. Existing limits remain:
HTTP API integration timeout, backfill's five-date scheduler limit, and
date-level completion semantics (late uploads on a completed date require manual
aggregation). Large-volume performance and the first timed run are not validated.
No other backend issue was observed within this validation scope. Frontend,
Amplify, Android URL migration, APK/device testing remain separate iterations.
