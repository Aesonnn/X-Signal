from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd
import requests


API_BASE = "https://api.x.com/2"
IDS_CSV_PATH = "ids.csv"
POSTS_PER_USER = 10


def _build_date_to_today_range() -> Dict[str, str]:
    now_utc = datetime.now(timezone.utc)
    start_utc = datetime(now_utc.year, 2, 19, 0, 0, 0, tzinfo=timezone.utc)
    if now_utc < start_utc:
        start_utc = datetime(now_utc.year - 1, 2, 19, 0, 0, 0, tzinfo=timezone.utc)

    return {
        "start_time": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_time": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _get_bearer_token(env_path: str = ".env") -> str:
    """Read bearer token directly from a .env file."""
    env_values: Dict[str, str] = {}

    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip().removeprefix("export ").strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    env_values[key] = value
    except FileNotFoundError as exc:
        raise RuntimeError(f"{env_path} file was not found.") from exc

    token = env_values.get("X_BEARER_TOKEN")
    if not token:
        raise RuntimeError(
            f"Missing bearer token in {env_path}. Set X_BEARER_TOKEN in your .env file."
        )
    return token

def _load_targets(csv_path: str = IDS_CSV_PATH) -> List[Dict[str, str]]:
    targets_df = pd.read_csv(csv_path)
    targets_df.columns = [column.strip() for column in targets_df.columns]

    required_columns = {"id", "name", "Spectrum"}
    missing_columns = required_columns.difference(set(targets_df.columns))
    if missing_columns:
        raise RuntimeError(
            f"Missing required columns in {csv_path}: {sorted(missing_columns)}"
        )

    targets_df = targets_df[["id", "name", "Spectrum"]].dropna(subset=["id"])
    targets_df["id"] = targets_df["id"].astype(str).str.strip()
    targets_df["name"] = targets_df["name"].astype(str).str.strip()
    targets_df["Spectrum"] = targets_df["Spectrum"].astype(str).str.strip()

    return targets_df.to_dict(orient="records")


def _fetch_recent_posts_for_user_id(
    user_id: str,
    bearer_token: str,
    max_results: int = POSTS_PER_USER,
) -> List[Dict[str, Any]]:
    headers = {"Authorization": f"Bearer {bearer_token}"}
    safe_max_results = max(5, min(100, max_results))

    url = f"{API_BASE}/users/{user_id}/tweets"
    params = {
        "max_results": safe_max_results,
        "exclude": "replies,retweets",
        "tweet.fields": "id,text,author_id,public_metrics,created_at",
        **_build_date_to_today_range(),
    }
    response = requests.get(url, headers=headers, params=params, timeout=20)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Failed fetching tweets for user id '{user_id}': {response.status_code} {response.text}"
        )
    payload = response.json()
    return payload.get("data", [])


def main() -> None:
    token = _get_bearer_token()
    targets = _load_targets(IDS_CSV_PATH)

    all_posts: List[Dict[str, Any]] = []
    for target in targets:
        user_id = target["id"]
        posts = _fetch_recent_posts_for_user_id(user_id, token, POSTS_PER_USER)
        for post in posts:
            all_posts.append(
                {
                    "id": post.get("id"),
                    "text": post.get("text"),
                    "author_id": post.get("author_id"),
                    "public_metrics": post.get("public_metrics"),
                    "created_at": post.get("created_at"),
                    "name": target.get("name"),
                    "spectrum": target.get("Spectrum"),
                }
            )

    if not all_posts:
        raise RuntimeError("No posts were returned for the ids listed in ids.csv.")

    df = pd.DataFrame(all_posts)

    print(f"Retrieved {len(df)} posts total from {len(targets)} users listed in {IDS_CSV_PATH}.")
    print(df)

    df.to_csv("recent_posts_19-2102.csv", index=False)
    print("Saved data to recent_posts_19-2102.csv")


if __name__ == "__main__":
    main()


