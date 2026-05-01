from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pandas as pd
import requests
from xdk import Client


IDS_CSV_PATH = "ids.csv"
POSTS_PER_USER = 20
OUTPUT_CSV_PATH = "recent_posts_2904.csv"


def _build_date_to_today_range() -> Dict[str, str]:
	now_utc = datetime.now(timezone.utc)
	start_utc = datetime(now_utc.year, 4, 29, 0, 0, 0, tzinfo=timezone.utc)
	end_utc = datetime(now_utc.year, 4, 29, 20, 20, 0, tzinfo=timezone.utc)
	if now_utc < start_utc:
		start_utc = datetime(now_utc.year - 1, 4, 29, 0, 0, 0, tzinfo=timezone.utc)

	# search_recent only supports the last 7 days.
	min_supported_start = now_utc - timedelta(days=7)
	if start_utc < min_supported_start:
		start_utc = min_supported_start

	return {
		"start_time": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
		"end_time": end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
	}


def _get_bearer_token(env_path: str = ".env") -> str:
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

	username_column = "username" if "username" in targets_df.columns else "name"
	required_columns = {username_column, "Spectrum"}
	missing_columns = required_columns.difference(set(targets_df.columns))
	if missing_columns:
		raise RuntimeError(
			f"Missing required columns in {csv_path}: {sorted(missing_columns)}"
		)

	targets_df = targets_df[[username_column, "Spectrum"]].dropna(subset=[username_column])
	targets_df["username"] = (
		targets_df[username_column].astype(str).str.strip().str.removeprefix("@")
	)
	targets_df["Spectrum"] = targets_df["Spectrum"].astype(str).str.strip()

	return targets_df[["username", "Spectrum"]].to_dict(orient="records")


def _normalize_post(post: Any) -> Dict[str, Any]:
	if hasattr(post, "model_dump"):
		return post.model_dump()
	if isinstance(post, dict):
		return post
	return {}


def _build_author_query(username: str) -> str:
	normalized = username.strip().removeprefix("@")
	return f"from:{normalized} -is:reply -is:retweet"


def _raise_api_error(exc: requests.exceptions.HTTPError, query: str) -> None:
	response = exc.response
	if response is None:
		raise RuntimeError(f"X API request failed for query '{query}': {exc}") from exc

	body = response.text or "<empty response body>"
	raise RuntimeError(
		"X API request failed\n"
		f"status_code={response.status_code}\n"
		f"url={response.url}\n"
		f"query={query}\n"
		f"response_body={body}"
	) from exc


def _fetch_recent_posts_for_username(client: Client, username: str, max_results: int = POSTS_PER_USER,
) -> List[Dict[str, Any]]:
	safe_max_results = max(10, min(100, max_results))
	date_range = _build_date_to_today_range()
	query = _build_author_query(username)

	collected_posts: List[Dict[str, Any]] = []
	try:
		pages = client.posts.search_recent(
			query=query,
			max_results=safe_max_results,
			tweet_fields=["id", "text", "author_id", "public_metrics", "created_at"],
			start_time=date_range["start_time"],
			end_time=date_range["end_time"],
		)

		for page in pages:
			for raw_post in page.data or []:
				post = _normalize_post(raw_post)
				if not post:
					continue
				collected_posts.append(post)
				if len(collected_posts) >= max_results:
					return collected_posts
	except requests.exceptions.HTTPError as exc:
		_raise_api_error(exc, query)

	return collected_posts


def main() -> None:
	token = _get_bearer_token()
	targets = _load_targets(IDS_CSV_PATH)
	client = Client(bearer_token=token)

	all_posts: List[Dict[str, Any]] = []
	for target in targets:
		username = target["username"]
		posts = _fetch_recent_posts_for_username(client, username, POSTS_PER_USER)
		for post in posts:
			all_posts.append(
				{
					"id": post.get("id"),
					"text": post.get("text"),
					"author_id": post.get("author_id"),
					"public_metrics": post.get("public_metrics"),
					"created_at": post.get("created_at"),
					"name": username,
					"username": username,
					"spectrum": target.get("Spectrum"),
				}
			)

	if not all_posts:
		raise RuntimeError("No posts were returned for the usernames listed in ids.csv.")

	df = pd.DataFrame(all_posts)

	print(f"Retrieved {len(df)} posts total from {len(targets)} users listed in {IDS_CSV_PATH}.")
	print(df)

	df.to_csv(OUTPUT_CSV_PATH, index=False)
	print(f"Saved data to {OUTPUT_CSV_PATH}")


if __name__ == "__main__":
	main()
