import os
import json
import urllib3


def lambda_handler(event, context):
    print("Lambda function started")

    api_base_url = os.getenv("API_BASE_URL", "").rstrip("/")
    if not api_base_url:
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "API_BASE_URL environment variable not set",
                "message": "Scheduler cannot call the backfill endpoint"
            })
        }

    try:
        http = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=30.0, read=900.0)
        )

        print("Making POST request to backfill endpoint...")

        request_body = json.dumps({"limit": 5})
        endpoint = f"{api_base_url}/daily-aggregator/backfill/"

        print(f"Calling: {endpoint}")

        response = http.request(
            "POST",
            endpoint,
            headers={
                "accept": "application/json",
                "Content-Type": "application/json"
            },
            body=request_body
        )

        response_data = response.data.decode("utf-8")
        print(f"API Response Status: {response.status}")
        print(f"API Response Body: {response_data}")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Successfully called daily aggregator backfill API",
                "api_http_status": response.status,
                "api_response": json.loads(response_data)
            })
        }

    except urllib3.exceptions.ReadTimeoutError:
        print("API Gateway timeout - processing may still be running in background")
        return {
            "statusCode": 202,
            "body": json.dumps({
                "message": "Request accepted - processing in progress",
                "note": (
                    "API Gateway timeout reached, but backfill may still "
                    "be processing. Check S3 combinedbyDay/ folder for results."
                )
            })
        }

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        import traceback
        traceback.print_exc()

        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "message": "Failed to call API"
            })
        }
