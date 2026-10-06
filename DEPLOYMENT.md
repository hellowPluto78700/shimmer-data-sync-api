# Independent backend deployment

Baseline: `e638cfb068bc88e2bc3edd6fd7bf5aabfc0be335`; branch: `aws-clone-deploy`.
The deployed resource names and live contract results are recorded in
[CORE_VALIDATION.md](CORE_VALIDATION.md), with subsequent aggregator/scheduler
evidence in [AGGREGATOR_VALIDATION.md](AGGREGATOR_VALIDATION.md).
Only the backend is in scope. The API routes, request/response models and decoder
are retained. Application changes are the Linux import correction from
`shimmerCaliberate` to `shimmerCalibrate` and regional SigV4 S3 client configuration
in `main.py` to prevent redirects of presigned uploads to the new bucket, plus
recognizing completed backfill dates when device names contain underscores.
The last correction scans filename components for the existing date instead of
assuming it is always the second component; output names and response contracts
remain unchanged. Regression coverage is in `tests/test_backfill_dates.py`.

## Runtime and dependencies

The SAM stack uses Python 3.12, x86_64, and `main.handler` (`Mangum(app)`).
`requirements.txt` contains `fastapi`, `mangum`, `pydantic`, `python-dotenv`,
`python-multipart`, `boto3`, and `urllib3`. The first six support `main.py`
(multipart is needed for `File`/`UploadFile` routes). Boto3 also supplies the
compatible botocore dependency used directly by the API and aggregator.
The scheduler directly imports urllib3. `shimmerCalibrate.py` imports only the
standard library. No runtime module imports `shimmer_wrapper.py`, the comparison
scripts, or plotting utilities, so NumPy, SciPy and Matplotlib are unnecessary.
Versions are unpinned; rebuilds resolve current dependencies. Record the resolved
versions during release validation if repeating the identical package is needed.

## Resources and constraints

`template.yaml` defines a private S3 bucket with generated name, public access
blocked, AES256 encryption, versioning, HTTPS-only bucket policy, and retention on
deletion/replacement. It stores raw uploads, `decode/`, `combinedbyDay/`, ZIP
downloads and `daily-aggregated/` debugging output.

Four DynamoDB tables use generated names and on-demand billing, with retention
on deletion/replacement. Never change keys on a deployed populated table without
a separate migration plan.

| Environment variable | Partition key (String) | Evidence / confidence |
| --- | --- | --- |
| `DDB_TABLE` | `device` | Explicit `get_item(Key={"device": device})` in `main.py:719`, `delete_item` at 816, and mapping writes at 765/795. No sort key is possible for these single-key accesses. |
| `DDB_FILE_TABLE` | `full_file_name` (authorized inference) | Upload metadata includes it at `main.py:272` and writes at 297. `parse_decode_filename` includes it at 1372 and decode writes at 1548. Reads are paginated scans at 375, 1119, 1426, 2049 and `daily_aggregator_handler.py:127`. One metadata record per raw file; consistent file identity throughout runtime code. |
| `DDB_STATE_TABLE` | `id` | Explicit `get_item(Key={"id": "last_processed_date"})` at `daily_aggregator_handler.py:36`; matching state write at 48. No sort key. |
| `DDB_OUTPUT_TABLE` | `combined_s3_key` | Existing summary at `daily_aggregator_handler.py:454` stores the generated device/date/shimmer output key. Live three-group test proved `date` overwrites summaries; the S3 identity distinguishes each group without changing summary fields. |

Source line references above use the pre-S3-configuration baseline layout;
the current `main.py` line numbers move by five lines after the client fix.

The original file-table definition was not recovered after searching all local
branches/history with `git log --all -S` for `DecodedFileMeta`, `DDB_FILE_TABLE`,
`full_file_name`, and `DDB_OUTPUT_TABLE`, and searching historical paths and code
for CloudFormation/SAM/Terraform/CDK, `create_table`, `KeySchema` and
`AttributeDefinitions`. Available branches are `main`, `aws-clone-deploy`, and
`origin/main`; there are no tags or infrastructure definitions in available
history. Commit `50066f9` introduced file metadata writes; `118d118` introduced
aggregation, but neither records a table schema. The user authorized
`full_file_name` String as the file-table partition key if unrecoverable.
There is no sort key or index needed by current code.

The output-table key is now `combined_s3_key` (String), no sort key. A live
same-date test produced three distinct combined files but only one row under
the old `date` key. Changing the generated-name table's key requires replacement;
`UpdateReplacePolicy: Retain` preserves the old table and its row. Rerunning the
manual aggregator repopulates all summaries in the new table from existing
decoded data. No core bucket, metadata/mapping table or API is replaced.
No indexes are required by the current scans. No data is copied from
the old account.

The main Lambda has only the new bucket's list/read/write permissions (including
multipart abort for `upload_fileobj`) and table-specific operations used by code.
The existing optional `tags` upload-URL parameter also requires
`s3:PutObjectTagging`. SAM supplies CloudWatch logging permissions.
The main Lambda runs the existing manual aggregator routes. A scheduler Lambda
calls only this stack's backfill API and has logging permissions only. No separate
direct-aggregator Lambda is needed. The recurring schedule starts disabled for
manual validation and is enabled only afterward through `SchedulerState`.

API Gateway is an HTTP API with `$default` stage and root plus catch-all proxy
routes. Mangum/FastAPI handle all endpoint routing, including existing trailing
slashes. Authentication and application CORS behavior are retained. HTTP API
requests have a 30-second integration limit even though Lambda is configured
for 900 seconds; long decoding/backfill requests may time out while processing
continues. Memory (1024 MB for processing) and timeout are
initial clone settings, not recovered production configuration or load-tested
capacity. Local smoke checks are not smartphone/dashboard contract acceptance.

## Environment

The main function receives `S3_BUCKET`, `DDB_TABLE`, `DDB_FILE_TABLE`,
`DDB_STATE_TABLE`, `DDB_OUTPUT_TABLE`, and `OUTPUT_S3_PREFIX=combinedbyDay/`.
All resource names come from this stack. The scheduler receives `API_BASE_URL`
from the same HTTP API reference as this stack's `ApiBaseUrl` output.
These are all application environment variables found in the runtime source.
AWS SDK credentials/region variables are supplied by Lambda; locally select the
existing SSO profile and `AWS_DEFAULT_REGION=us-east-2`. `load_dotenv()` remains
unchanged. Never package a local `.env` or credentials in the deployment.

## Scheduler

`daily_aggregatore_scheduler.lambda_handler` calls
`${API_BASE_URL}/daily-aggregator/backfill/`, trimming a trailing slash.
There is no old-production URL fallback. Missing `API_BASE_URL` fails without
sending a request. Existing POST body `{"limit": 5}`, headers, 30-second connect
timeout, 900-second read timeout and response/error handling are retained.

The user confirmed daily at 11:45 PM `America/New_York` for the clone. SAM's
`ScheduleV2` creates EventBridge Scheduler schedule
`${AWS::StackName}-daily-backfill` with `cron(45 23 * * ? *)`, this timezone,
and no flexible window. Scheduler handles daylight-saving transitions. This is
an EventBridge Scheduler schedule, not a legacy UTC-only EventBridge rule.
The schedule targets only the new scheduler Lambda. SAM generates a target role
with invocation permission scoped to that Lambda. `SchedulerState` defaults to
`DISABLED`; enable only after live manual aggregation and scheduler validation
using `--parameter-overrides SchedulerState=ENABLED` on the normal SAM deploy.

## Validate and deploy

The existing local profile is `shimmer-admin`; use it explicitly because there
are no default credentials in this shell. Do not configure another account.

```bash
aws sts get-caller-identity --profile shimmer-admin --region us-east-2
python3.12 -m venv /tmp/shimmer-clone-validation-venv
/tmp/shimmer-clone-validation-venv/bin/python -m pip install -r requirements.txt
AWS_PROFILE=shimmer-admin AWS_DEFAULT_REGION=us-east-2 /tmp/shimmer-clone-validation-venv/bin/python -c 'import main; print(main.handler)'
sam validate --region us-east-2
sam validate --lint --region us-east-2
PATH=/tmp/shimmer-clone-validation-venv/bin:$PATH sam build
aws sts get-caller-identity --profile shimmer-admin --region us-east-2
```

After validation, first verify that
`shimmer-server-clone` does not exist in the selected account/region. Inspect
any existing stack rather than updating unrelated resources. From this backend
directory, the noninteractive deployment command is:

```bash
sam deploy --template-file .aws-sam/build/template.yaml --stack-name shimmer-server-clone --profile shimmer-admin --region us-east-2 --resolve-s3 --capabilities CAPABILITY_IAM --no-confirm-changeset --no-fail-on-empty-changeset
```

For subsequent deployments of this validated clone with recurrence enabled,
append `--parameter-overrides SchedulerState=ENABLED`. Explicitly use `DISABLED`
when validating a new scheduler configuration before allowing recurrence.

This creates SAM packaging infrastructure as well as the backend stack; no
physical resource names or old-account identifiers are hardcoded.
Outputs include `ApiBaseUrl`, `ApiGatewayId`, the bucket name, all four table names,
the main/scheduler Lambda names and the schedule name. Retrieve them with:

```bash
aws cloudformation describe-stacks --stack-name shimmer-server-clone --profile shimmer-admin --region us-east-2 --query 'Stacks[0].Outputs'
```

Do not update frontend/Android API URLs until the new backend passes contract
tests. Do not commit local environments, `.aws-sam/` or Python caches.

## Preparation validation evidence

- Python 3.12 `import main; print(main.handler)` passed with the existing SSO
  profile and `us-east-2`.
- Dependency installation and `pip check` passed.
- `sam validate`, `sam validate --lint`, and final CORE `sam build` passed.
- An isolated `python -I -S` import using only the built artifact and standard
  library resolved `main.handler` and all production packages; `main.py` and
  `shimmerCalibrate.py` are present, and no `.env` is packaged.
- OpenAPI and registered routes match baseline `e638cfb`; only the import typo,
  S3 client configuration and completed-backfill-date parsing change. Decoder
  and aggregator source are byte-for-byte unchanged.
- A representative HTTP API v2 proxy event reached the unchanged filename parser.
- Scheduler checks matched baseline POST body/headers/timeouts and response/error
  branches; absent URL sends no request. No old API hostname remains in source.
- Real binary fixture `test_files/000` recovered from historical commit `b19efb0`
  decoded locally to 30,240 timestamp samples. It was recovered outside the
  repository, not added to the Lambda package.
- AWS identity verified as target account `837873138796`; existing profile region
  is `us-east-2`. The target stack was confirmed absent before creation.

SAM linting and manual IAM/storage review are not a formal cfn-guard compliance
certification; cfn-guard and its Python binding are not installed.

## Deployment defect found during live validation

The first live presigned PUT returned HTTP 307 `TemporaryRedirect`: the global
`bucket.s3.amazonaws.com` host directed the client to
`bucket.s3.us-east-2.amazonaws.com`. This is a blocker for clients that use the
returned upload URL directly. `main.py` now uses
`Config(signature_version="s3v4", s3={"addressing_style": "virtual"})` on its
existing S3 client. Region and credentials still come from the existing SDK
environment. This signs against the regional hostname without altering paths,
HTTP methods, payloads, response keys or presigned expiry. It follows the
[Boto3 presigned URL guidance](https://docs.aws.amazon.com/boto3/latest/guide/s3-presigned-urls.html).
