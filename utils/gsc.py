from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta


def get_gsc_client(service_account_info: dict):
    scopes = ["https://www.googleapis.com/auth/webmasters.readonly"]
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    return build("searchconsole", "v1", credentials=creds)


def get_top_queries_for_url(client, site_url: str, page_url: str, top_n: int = 10) -> list:
    """
    Returns top N queries for a given page URL sorted by impressions.
    Each item: { query, impressions, clicks, ctr, position }

    Common silent failure: site_url must match the GSC property format exactly.
    sc-domain:example.com for domain properties, https://example.com/ for URL prefix.
    """
    end_date = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=90)).strftime("%Y-%m-%d")

    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": ["query"],
        "dimensionFilterGroups": [{
            "filters": [{
                "dimension": "page",
                "operator": "equals",
                "expression": page_url
            }]
        }],
        "rowLimit": top_n,
        "orderBy": [{"fieldName": "impressions", "sortOrder": "DESCENDING"}]
    }

    try:
        response = client.searchanalytics().query(siteUrl=site_url, body=body).execute()
        rows = response.get("rows", [])
        return [
            {
                "query": row["keys"][0],
                "impressions": row.get("impressions", 0),
                "clicks": row.get("clicks", 0),
                "ctr": row.get("ctr", 0),
                "position": round(row.get("position", 99), 1),
                "source": "gsc"
            }
            for row in rows
        ]
    except Exception as e:
        return []
