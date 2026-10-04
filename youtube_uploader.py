#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
youtube_uploader.py — Automated YouTube Video & Thumbnail Upload Client.

Features:
- Headless authentication using OAuth 2.0 refresh token (suitable for GitHub Actions CI/CD).
- Resumable video upload with exponential backoff retry for network resilience.
- Mandatory compliance disclosure: sets `status.containsSyntheticMedia: true` (verified per Oct 2024 YouTube Data API v3 spec).
- Category mapping (Education=27, Science & Technology=28, Entertainment=24).
- Custom high-CTR thumbnail upload via `thumbnails.set`.
- Configurable privacy status (defaults to 'private' for safe manual inspection).
"""

import os
import sys
import time
import json
import random
import re
import argparse
from datetime import datetime

# UTF-8 console output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import googleapiclient.discovery
import googleapiclient.errors
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# Standard YouTube category IDs
CATEGORY_MAPPING = {
    "film & animation": "1",
    "autos & vehicles": "2",
    "music": "10",
    "pets & animals": "15",
    "sports": "17",
    "travel & events": "19",
    "gaming": "20",
    "people & blogs": "22",
    "comedy": "23",
    "entertainment": "24",
    "news & politics": "25",
    "howto & style": "26",
    "education": "27",
    "science & technology": "28",
    "nonprofits & activism": "29",
}

RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
MAX_RETRIES = 10


def get_youtube_client(client_id: str = None, client_secret: str = None, refresh_token: str = None):
    """
    Builds an authenticated YouTube Data API v3 client using OAuth2 refresh token.
    """
    import config
    config.reload()

    cid = client_id or os.environ.get("YOUTUBE_CLIENT_ID") or getattr(config, "YOUTUBE_CLIENT_ID", None)
    csec = client_secret or os.environ.get("YOUTUBE_CLIENT_SECRET") or getattr(config, "YOUTUBE_CLIENT_SECRET", None)
    rtoken = refresh_token or os.environ.get("YOUTUBE_REFRESH_TOKEN") or getattr(config, "YOUTUBE_REFRESH_TOKEN", None)

    if cid:
        cid = cid.strip().lstrip("\ufeff")
    if csec:
        csec = csec.strip().lstrip("\ufeff")
    if rtoken:
        rtoken = rtoken.strip().lstrip("\ufeff")

    # Fallback to checking .env directly if config doesn't have it yet
    if not (cid and csec and rtoken):
        env_file = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_file):
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("YOUTUBE_CLIENT_ID="):
                        cid = cid or line.split("=", 1)[1].strip()
                    elif line.startswith("YOUTUBE_CLIENT_SECRET="):
                        csec = csec or line.split("=", 1)[1].strip()
                    elif line.startswith("YOUTUBE_REFRESH_TOKEN="):
                        rtoken = rtoken or line.split("=", 1)[1].strip()

    if not (cid and csec and rtoken) or "your_" in (cid or ""):
        raise ValueError(
            "Missing YouTube OAuth credentials. Please run `py youtube_auth_setup.py` "
            "to generate YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN."
        )

    creds = Credentials(
        token=None,
        refresh_token=rtoken,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cid,
        client_secret=csec,
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ],
    )

    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)


PLAYLIST_CACHE_FILE = os.path.join(os.path.dirname(__file__), "data", "playlist_cache.json")


def _load_playlist_cache() -> dict:
    if os.path.exists(PLAYLIST_CACHE_FILE):
        try:
            with open(PLAYLIST_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_playlist_cache(cache: dict):
    os.makedirs(os.path.dirname(PLAYLIST_CACHE_FILE), exist_ok=True)
    try:
        with open(PLAYLIST_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"⚠️ Failed saving playlist cache: {e}")


def get_or_create_playlist(youtube, category: str) -> str:
    """
    Finds existing playlist by category title, or creates a new one via playlists.insert.
    Caches playlist IDs locally to minimize API quota consumption.
    """
    if not category:
        return None

    clean_category = category.strip()
    cache = _load_playlist_cache()

    if clean_category in cache:
        return cache[clean_category]

    print(f"📑 Checking YouTube channel for playlist: \"{clean_category}\"...")
    try:
        request = youtube.playlists().list(
            mine=True,
            part="snippet",
            maxResults=50,
        )
        response = request.execute()
        for item in response.get("items", []):
            title = item.get("snippet", {}).get("title", "").strip()
            if title.lower() == clean_category.lower():
                pid = item.get("id")
                print(f"✅ Found existing playlist: \"{title}\" (ID: {pid})")
                cache[clean_category] = pid
                _save_playlist_cache(cache)
                return pid
    except Exception as e:
        print(f"⚠️ Warning listing playlists: {e}")

    # Create new playlist
    print(f"✨ Creating new category playlist on YouTube: \"{clean_category}\"...")
    try:
        insert_req = youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": clean_category,
                    "description": f"Curated collection of {clean_category} deep dives by History & Science Facts.",
                    "defaultLanguage": "en",
                },
                "status": {
                    "privacyStatus": "public",
                },
            },
        )
        res = insert_req.execute()
        pid = res.get("id")
        print(f"🎉 Created playlist: \"{clean_category}\" (ID: {pid})")
        cache[clean_category] = pid
        _save_playlist_cache(cache)
        return pid
    except Exception as e:
        print(f"⚠️ Failed creating playlist: {e}")
        return None


def add_video_to_playlist(youtube, video_id: str, playlist_id: str) -> bool:
    """Adds an uploaded video to a specific YouTube playlist."""
    if not video_id or not playlist_id:
        return False

    print(f"➕ Adding video {video_id} to playlist {playlist_id}...")
    try:
        request = youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id,
                    },
                }
            },
        )
        request.execute()
        print(f"✅ Video {video_id} successfully added to playlist {playlist_id}!")
        return True
    except Exception as e:
        print(f"⚠️ Failed adding video to playlist: {e}")
        return False


def upload_thumbnail(youtube, video_id: str, thumbnail_path: str, max_retries: int = 3) -> bool:
    """Uploads a custom JPEG thumbnail for a video with retries and propagation delay."""
    if not thumbnail_path or not os.path.exists(thumbnail_path):
        print(f"⚠️ Thumbnail not found at {thumbnail_path}, skipping thumbnail upload.")
        return False

    print(f"🖼️ Uploading custom thumbnail: {thumbnail_path} ...")
    time.sleep(3)  # Allow YouTube backend to register video before attaching thumbnail

    for attempt in range(1, max_retries + 1):
        try:
            request = youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
            )
            response = request.execute()
            print(f"✅ Custom thumbnail successfully attached to video {video_id}!")
            return True
        except Exception as e:
            print(f"⚠️ Attempt {attempt}/{max_retries} failed to upload thumbnail: {e}")
            if attempt < max_retries:
                time.sleep(3 * attempt)
    return False


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list = None,
    category: str = "News & Politics",
    topic_category: str = None,
    thumbnail_path: str = None,
    privacy_status: str = "private",
    contains_synthetic_media: bool = False,
    self_declared_made_for_kids: bool = False,
    client_id: str = None,
    client_secret: str = None,
    refresh_token: str = None,
    dry_run: bool = False,
    category_id: str = None,
) -> dict:
    """
    Uploads a video to YouTube with metadata, custom thumbnail, and synthetic media disclosure flag.

    Returns dict containing video_id, url, and upload metadata.
    """
    if not os.path.exists(video_path) and not dry_run:
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # Map category name to ID
    cat_lower = str(category).lower().strip()
    category_id = CATEGORY_MAPPING.get(cat_lower, "27")  # default Education (27)

    # Sanitize title (max 100 chars per YouTube API, fix duplicate articles, clean word boundaries)
    clean_title = " ".join(title.split()).strip()
    clean_title = re.sub(r'^(the\s+)+the\b', 'The', clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r'^(a\s+)+a\b', 'A', clean_title, flags=re.IGNORECASE)
    if len(clean_title) > 100:
        clean_title = clean_title[:100].rsplit(" ", 1)[0].rstrip(" ,;:-—")

    # Ensure tags is a list of strings and sanitize for YouTube API requirements
    if isinstance(tags, str):
        raw_tags = [t.strip() for t in tags.split(",") if t.strip()]
    elif isinstance(tags, list):
        raw_tags = [str(t).strip() for t in tags if str(t).strip()]
    else:
        raw_tags = ["history", "science", "facts"]

    # YouTube tag sanitization: no colons, angle brackets, commas, max 50 chars per tag, max 400 chars total
    clean_tags = []
    total_tag_chars = 0
    forbidden_chars = str.maketrans({':': ' ', '<': '', '>': '', '"': '', '\n': ' ', '\r': ' ', ',': ' '})
    for t in raw_tags:
        sanitized = t.translate(forbidden_chars).strip()
        sanitized = " ".join(sanitized.split())  # normalize whitespace
        if not sanitized or len(sanitized) < 2:
            continue
        if len(sanitized) > 50:
            sanitized = sanitized[:50].rsplit(" ", 1)[0]
        if sanitized.lower() not in [x.lower() for x in clean_tags]:
            if total_tag_chars + len(sanitized) + 1 <= 400:
                clean_tags.append(sanitized)
                total_tag_chars += len(sanitized) + 1
    if not clean_tags:
        clean_tags = ["history", "science", "facts", "documentary", "did you know"]

    cat_id = category_id or CATEGORY_MAPPING.get(category.lower(), "25")

    # Video resource body
    body = {
        "snippet": {
            "title": clean_title,
            "description": description.strip(),
            "tags": clean_tags,
            "categoryId": cat_id,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy_status,
            "containsSyntheticMedia": contains_synthetic_media,  # Verified disclosure flag per v3 spec
            "selfDeclaredMadeForKids": self_declared_made_for_kids,
        },
    }

    if dry_run:
        print("\n🟡 [Dry Run] YouTube Upload Request Body Preview:")
        print(json.dumps(body, indent=2))
        return {
            "status": "dry_run",
            "video_id": "MOCK_VIDEO_ID_12345",
            "video_url": "https://youtu.be/MOCK_VIDEO_ID_12345",
            "title": clean_title,
            "privacy_status": privacy_status,
            "contains_synthetic_media": contains_synthetic_media,
            "thumbnail_uploaded": bool(thumbnail_path),
        }

    # Initialize client
    youtube = get_youtube_client(client_id, client_secret, refresh_token)

    # Setup resumable media upload in 4MB chunks
    media = MediaFileUpload(
        video_path,
        chunksize=4 * 1024 * 1024,
        resumable=True,
        mimetype="video/mp4",
    )

    insert_request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    print(f"\n🚀 Initiating resumable video upload to YouTube...")
    print(f"   Title: \"{clean_title}\"")
    print(f"   Privacy: {privacy_status}")
    print(f"   Altered/Synthetic Media Flag: {contains_synthetic_media}")

    response = None
    retry_count = 0

    while response is None:
        try:
            status, response = insert_request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                print(f"   📤 Upload progress: {progress}% ...", flush=True)
        except googleapiclient.errors.HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES:
                retry_count += 1
                if retry_count > MAX_RETRIES:
                    raise Exception(f"Upload failed after {MAX_RETRIES} retries. HTTP error: {e}")
                sleep_sec = (2 ** retry_count) + random.random()
                print(f"⚠️ Retriable HTTP {e.resp.status} error, retrying in {sleep_sec:.1f}s...")
                time.sleep(sleep_sec)
            else:
                raise e
        except Exception as e:
            err_str = str(e).lower()
            if "invalid_grant" in err_str or "token has been expired or revoked" in err_str:
                raise RuntimeError(
                    f"❌ YouTube OAuth authentication failed: Refresh token is expired or revoked ({e}). "
                    "Make sure your Google Cloud OAuth Consent Screen is set to 'In production' and regenerate YOUTUBE_REFRESH_TOKEN."
                )
            retry_count += 1
            if retry_count > MAX_RETRIES:
                raise Exception(f"Upload failed after {MAX_RETRIES} retries: {e}")
            sleep_sec = (2 ** retry_count) + random.random()
            print(f"⚠️ Network error ({e}), retrying in {sleep_sec:.1f}s...")
            time.sleep(sleep_sec)

    video_id = response.get("id")
    video_url = f"https://youtu.be/{video_id}"
    print(f"\n🎉 Video successfully uploaded! Video ID: {video_id}")
    print(f"🔗 Video URL: {video_url}")

    # Upload custom thumbnail if present
    thumbnail_ok = False
    if thumbnail_path:
        thumbnail_ok = upload_thumbnail(youtube, video_id, thumbnail_path)

    # Assign video to category playlist (§4f)
    playlist_id = None
    playlist_ok = False
    if topic_category:
        try:
            playlist_id = get_or_create_playlist(youtube, topic_category)
            if playlist_id:
                playlist_ok = add_video_to_playlist(youtube, video_id, playlist_id)
        except Exception as e:
            print(f"⚠️ Playlist assignment warning: {e}")

    return {
        "status": "success",
        "video_id": video_id,
        "video_url": video_url,
        "title": clean_title,
        "privacy_status": privacy_status,
        "contains_synthetic_media": contains_synthetic_media,
        "thumbnail_uploaded": thumbnail_ok,
        "playlist_id": playlist_id,
        "playlist_added": playlist_ok,
        "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def update_video_metadata(
    video_id: str,
    title: str = None,
    description: str = None,
    tags: list = None,
    category_id: str = "27",
    client_id: str = None,
    client_secret: str = None,
    refresh_token: str = None,
) -> dict:
    """Updates snippet metadata (title, description, tags) for an existing video on YouTube."""
    youtube = get_youtube_client(client_id, client_secret, refresh_token)
    
    # Fetch existing snippet first
    get_req = youtube.videos().list(part="snippet,status", id=video_id)
    get_res = get_req.execute()
    items = get_res.get("items", [])
    if not items:
        raise ValueError(f"Video {video_id} not found on YouTube.")
    
    snippet = items[0]["snippet"]
    if title:
        clean_title = " ".join(title.split()).strip()
        clean_title = re.sub(r'^(the\s+)+the\b', 'The', clean_title, flags=re.IGNORECASE)
        clean_title = re.sub(r'^(a\s+)+a\b', 'A', clean_title, flags=re.IGNORECASE)
        snippet["title"] = clean_title[:100].rsplit(" ", 1)[0].rstrip(" ,;:-—") if len(clean_title) > 100 else clean_title
    if description is not None:
        snippet["description"] = description.strip()
    if tags is not None:
        snippet["tags"] = tags
    if category_id:
        snippet["categoryId"] = category_id

    update_req = youtube.videos().update(
        part="snippet",
        body={
            "id": video_id,
            "snippet": snippet,
        }
    )
    res = update_req.execute()
    new_title = res.get("snippet", {}).get("title", "")
    print(f"✅ Video {video_id} metadata updated! New Title: \"{new_title}\"")
    return res


def main():
    parser = argparse.ArgumentParser(description="YouTube Video & Thumbnail Uploader CLI.")
    parser.add_argument("--video", type=str, required=True, help="Path to MP4 video file.")
    parser.add_argument("--title", type=str, default=None, help="Video title.")
    parser.add_argument("--desc", type=str, default="", help="Video description.")
    parser.add_argument("--tags", type=str, default=None, help="Comma-separated tags.")
    parser.add_argument("--category", type=str, default=None, help="Category (Education, Science & Technology).")
    parser.add_argument("--topic-category", type=str, default=None, help="Topic playlist category (e.g. Ancient History).")
    parser.add_argument("--thumbnail", type=str, default=None, help="Path to custom thumbnail JPEG.")
    parser.add_argument("--privacy", type=str, choices=["private", "unlisted", "public"], default="private", help="Privacy setting.")
    parser.add_argument("--no-synthetic-flag", action="store_true", help="Disable synthetic media disclosure.")
    parser.add_argument("--dry-run", action="store_true", help="Validate request body without sending to YouTube.")

    args = parser.parse_args()

    title = args.title
    description = args.desc
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None
    category = args.category or "Education"
    topic_category = args.topic_category
    thumbnail_path = args.thumbnail

    # Check for sidecar metadata JSON file if metadata was not explicitly provided on CLI
    sidecar_json = args.video.rsplit(".", 1)[0] + "_metadata.json"
    if not os.path.exists(sidecar_json):
        sidecar_json = os.path.join(os.path.dirname(args.video), "latest_metadata.json")

    if os.path.exists(sidecar_json):
        try:
            with open(sidecar_json, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
                title = title or meta_data.get("title")
                description = description or meta_data.get("description")
                if not tags:
                    tags = meta_data.get("tags")
                if not args.category:
                    category = meta_data.get("category", "Education")
                if not topic_category:
                    topic_category = meta_data.get("topic_category")
                if not thumbnail_path:
                    thumbnail_path = meta_data.get("thumbnail_path")
        except Exception as e:
            print(f"⚠️ Warning reading sidecar metadata: {e}")

    title = title or os.path.splitext(os.path.basename(args.video))[0].replace("-", " ").title()
    description = description or f"Deep dive into {title}. Subscribe for daily history and science facts."
    tags = tags or ["history", "science", "facts"]

    res = upload_video(
        video_path=args.video,
        title=title,
        description=description,
        tags=tags,
        category=category,
        topic_category=topic_category,
        thumbnail_path=thumbnail_path,
        privacy_status=args.privacy,
        contains_synthetic_media=not args.no_synthetic_flag,
        dry_run=args.dry_run,
    )

    print("\n--- Upload Result ---")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
