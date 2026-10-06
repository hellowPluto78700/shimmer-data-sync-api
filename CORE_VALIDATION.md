# Deployed CORE backend validation

Verified on 2026-10-06 in AWS account `837873138796`, region `us-east-2`, using
the existing `shimmer-admin` SSO profile. No credentials or account settings were
changed. Baseline: `e638cfb068bc88e2bc3edd6fd7bf5aabfc0be335`.
Preparation commit: `3d4edaebbcda07964724d9ae5d089d30acf279da`.
Deployed application fix commit: `ce3f5a1` (regional S3 presigned URLs).

## Deployed resources

| Resource | Actual deployed value |
| --- | --- |
| Stack | `shimmer-server-clone` |
| Final stack status | `UPDATE_COMPLETE` (initial deployment `CREATE_COMPLETE`) |
| API base URL | https://wwr1eh4vg9.execute-api.us-east-2.amazonaws.com |
| HTTP API ID | `wwr1eh4vg9` |
| Main Lambda | `shimmer-server-clone-MainApiFunction-hNr96vzCphw3` |
| S3 bucket | `shimmer-server-clone-databucket-wn9atsyogh42` |
| Device/patient table | `shimmer-server-clone-DevicePatientTable-1LORG2R27LVF7` |
| File metadata table | `shimmer-server-clone-FileMetadataTable-1FARD0NWRCNXP` |
| Auxiliary aggregator state table | `shimmer-server-clone-AggregatorStateTable-1ENHND3FHU6PQ` |
| Auxiliary aggregator output table | `shimmer-server-clone-AggregatedDataTable-L94O1IH4KDP` |

SAM also created its packaging stack/bucket; the packaging bucket is
`aws-sam-cli-managed-default-samclisourcebucket-wjqdfswmryqc`.
No unrelated application resources were modified or replaced. The defect-fix
change set modified only the clone Lambda and HTTP API, with no replacements.
No separate aggregator Lambda, scheduler Lambda, or EventBridge timer exists
in this CORE template. Existing manual aggregator routes remain unchanged.

Main Lambda configuration was retrieved and verified: Python 3.12,
`main.handler`, and all five resource environment variables match the new stack's
outputs exactly. `OUTPUT_S3_PREFIX` is `combinedbyDay/`. No old server resource
name or old API URL is used. The new bucket's four public-access-block settings
were verified true. Metadata table is ACTIVE with HASH key `full_file_name`
(String), no sort key. Device mapping key is `device`, state key is `id`, and
auxiliary output key `date` remains provisional for future aggregator validation.
See [DEPLOYMENT.md](DEPLOYMENT.md) for history searches and schema evidence.

## Local and deployment checks

| Check | Result |
| --- | --- |
| Runtime dependency installation and `pip check` | PASS |
| `python -c 'import main; print(main.handler)'` | PASS: Mangum instance |
| `sam validate` | PASS |
| `sam validate --lint` | PASS |
| `sam build` | PASS, including after regional S3 fix |
| Built artifact source/dependencies and isolated `main.handler` import | PASS |
| OpenAPI and registered routes compared with baseline | PASS, unchanged |
| Decoder and aggregator source comparison | PASS, unchanged |
| Scheduler request/timeouts and response/error branches | PASS; configurable URL, no old fallback |
| CloudFormation validation events | No validation errors reported |

The dependency manifest contains only `fastapi`, `mangum`, `pydantic`,
`python-dotenv`, `python-multipart`, `boto3`, `urllib3`. No NumPy/SciPy/Matplotlib.
Formal cfn-guard compliance certification was not performed.

## Live API contract results

All API requests below targeted only the new base URL. Presigned URLs were used
as returned, without rewriting their hosts or signatures. Direct AWS checks
targeted only resource names resolved from the clone stack outputs.

| Contract check | Result / evidence |
| --- | --- |
| `GET /openapi.json` | PASS, HTTP 200, existing decode route present |
| Initial `POST /missing-files/` with `["clone_contract_test_1.txt"]` | PASS, response `{"missing_files":["clone_contract_test_1.txt"]}` |
| `GET /generate-upload-url/?filename=clone_contract_test_1.txt` | PASS, HTTP 200 with `upload_url` |
| PUT harmless content via returned URL | PASS, HTTP 200 after regional endpoint fix |
| Direct new-S3 `head-object` | PASS, stored content length matches uploaded bytes |
| Repeat missing-files request | PASS, response `{"missing_files":[]}` |
| PUT mapping for `CLONE_TEST_DEVICE` | PASS, patient `CLONE_CONTRACT_TEST`; string `shimmer1` normalized to list as before |
| GET mapping for `CLONE_TEST_DEVICE` | PASS, matches saved mapping |
| Direct consistent DynamoDB get-item | PASS, new device/patient table contains matching record |
| Real-fixture `POST /decode-and-store/` | PASS, HTTP 200 without error field |
| Direct decoded S3 object verification and JSON download | PASS, nonempty JSON containing 30,240 timestamp samples |
| Direct file-metadata DynamoDB get-item | PASS, filename, recording start/end and decode key all present and consistent with response |
| Optional existing `tags=contract=clone` upload contract | PASS, PUT succeeds and direct S3 tagging check matches |

Real fixture: binary `test_files/000` from historical commit `b19efb0`, 998,176
bytes. Current checkout has no raw binary fixture; this one was recovered into
`/tmp` without adding fixture bytes to the repository or Lambda package.
Uploaded raw key:
`CLONE_TEST_DEVICE__20251006_120000__CLONE_CONTRACT__Shimmer_CLONE-001__000.txt`.
Decoded key:
`decode/CLONE_TEST_DEVICE__20251006_120000__CLONE_CONTRACT__Shimmer_CLONE-001__000_decoded.json`.
Stored timestamps are `2010-10-02T22:43:51.951752+00:00` and
`2010-10-02T22:53:50.596345+00:00`, derived by the unchanged decoder from the old
binary fixture, not from its synthetic upload filename.

Test artifacts are retained in the new bucket and tables: two harmless text
objects, the real-fixture raw/decoded objects, one clone-test mapping and its
decoded-file metadata row. No old-account data/resources were accessed.

## Defect fixed and CloudWatch review

Initial presigned PUT failed with S3 HTTP 307 `TemporaryRedirect` from the global
hostname to the new bucket's regional hostname. The existing S3 client now uses
SigV4 and explicit virtual addressing, following the AWS Python SDK skill and
[Boto3 guidance](https://docs.aws.amazon.com/boto3/latest/guide/s3-presigned-urls.html).
After rebuild and clone-stack redeployment, all upload and decode checks passed.
API routes, body formats, response keys, timeouts and decoder logic were retained.

Reviewed CloudWatch log group:
`/aws/lambda/shimmer-server-clone-MainApiFunction-hNr96vzCphw3`.
Latest test stream:
`2026/10/06/[$LATEST]edfcb1ee582e457aa261562ad09eeebc`.
It contains the tested invocations, including decode request
`e95f46e2-2880-4f23-9f46-b24f316df9e5`, download of 998,176 bytes, and successful
END/REPORT. Decode duration: 4,031.99 ms; max memory observed: 208 MB.
No import errors, IAM failures, missing environment variables, DynamoDB schema
errors, S3 errors, or Mangum/FastAPI exceptions appeared in the reviewed stream.
This is contract evidence, not a load test or physical Android-device test.

## Remaining work (outside this iteration)

- Validate aggregator output identity and manual aggregation; only then plan
  scheduler cadence/timezone. Recurring scheduling remains disabled.
- Frontend API migration and Amplify deployment.
- Android URL migration.
- APK and physical-device testing.

Frontend, Android, Amplify and Cognito were not modified. Stop after this CORE
deployment and contract validation.
