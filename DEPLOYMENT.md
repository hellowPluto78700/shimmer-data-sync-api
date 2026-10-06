# Independent backend deployment

Baseline: `e638cfb068bc88e2bc3edd6fd7bf5aabfc0be335`; branch: `aws-clone-deploy`.
Only the backend is in scope. The API routes, request/response models and decoder
are retained; the application change is the Linux import correction from
`shimmerCaliberate` to `shimmerCalibrate` in `main.py`.

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
| `DDB_OUTPUT_TABLE` | `date` (provisional) | Summary item at `daily_aggregator_handler.py:448` includes date and is written at 457; no keyed reads or documented original schema. |

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

The output-table schema remains provisional and does not gate CORE deployment.
In particular, a `date`-only output
key replaces the summary when another device/shimmer group for the same date is
written. Confirm its intended identity before validating or scheduling aggregation.
No indexes are required by the current scans. No data is copied from
the old account.

The main Lambda has only the new bucket's list/read/write permissions (including
multipart abort for `upload_fileobj`) and table-specific operations used by code.
The existing optional `tags` upload-URL parameter also requires
`s3:PutObjectTagging`. SAM supplies CloudWatch logging permissions.
Only the main Lambda is deployed. State/output tables are auxiliary resources
for unchanged manual routes and cannot run automatically. No separate aggregator
Lambda, scheduler Lambda or EventBridge timer is deployed.

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
All resource names come from this stack. A future scheduler deployment must set
`API_BASE_URL` to this stack's `ApiBaseUrl` output.
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

The CORE stack creates neither a separate aggregator nor a scheduler Lambda,
and no timers. The original cadence is not established by source (README's
example is not infrastructure evidence). Later, after aggregator validation,
confirm cadence/timezone and deploy the scheduler with `API_BASE_URL` set to
`ApiBaseUrl`. Scheduling is outside this deployment iteration.

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

This creates SAM packaging infrastructure as well as the backend stack; no
physical resource names or old-account identifiers are hardcoded.
Outputs include `ApiBaseUrl`, `ApiGatewayId`, the bucket name, all four table names,
and the main Lambda name. Retrieve them with:

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
- OpenAPI and registered routes match baseline `e638cfb` after correcting only
  its import typo. Decoder and aggregator source are byte-for-byte unchanged.
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
