#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
facebook_uploader.py — Automated Facebook Page Video & Reels Uploader Client.
Supports full 1080p long-form videos with custom thumbnails and 9:16 vertical Reels.
"""

import os
import sys
import time
import json
import argparse
import requests

# Reconfigure console for UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def get_fb_credentials():
    """Retrieves FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN from env or local config."""
    page_id = os.environ.get("FB_PAGE_ID")
    token = os.environ.get("FB_PAGE_ACCESS_TOKEN")

    if not (page_id and token):
        # Fallback to local fb_perm_token.json or .env
        base_dir = os.path.dirname(os.path.abspath(__file__))
        token_file = os.path.join(base_dir, "fb_perm_token.json")
        if os.path.exists(token_file):
            try:
                with open(token_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    page_id = page_id or data.get("page_id")
                    token = token or data.get("page_access_token")
            except Exception:
                pass

    if not (page_id and token):
        env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_file):
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("FB_PAGE_ID="):
                        page_id = page_id or line.split("=", 1)[1].strip()
                    elif line.startswith("FB_PAGE_ACCESS_TOKEN="):
                        token = token or line.split("=", 1)[1].strip()

    return page_id, token


def upload_video(
    video_path: str,
    title: str,
    description: str,
    thumbnail_path: str = None,
    page_id: str = None,
    access_token: str = None,
    published: bool = False
) -> dict:
    """
    Uploads a long-form video to the Facebook Page with title, description, and custom thumbnail.
    Safe execution: catches all exceptions without raising so parent pipeline never fails.
    """
    try:
        pid, tok = page_id or None, access_token or None
        if not (pid and tok):
            pid, tok = get_fb_credentials()

        if not (pid and tok):
            print("ℹ️ [Facebook Uploader] Facebook credentials missing (FB_PAGE_ID or FB_PAGE_ACCESS_TOKEN). Skipping Facebook upload.")
            return {"status": "skipped", "reason": "missing_credentials"}

        if not video_path or not os.path.exists(video_path):
            print(f"⚠️ [Facebook Uploader] Video file not found: {video_path}. Skipping.")
            return {"status": "skipped", "reason": "video_not_found"}

        file_size_bytes = os.path.getsize(video_path)
        file_size_mb = file_size_bytes / (1024 * 1024)
        print(f"\n🚀 [Facebook Uploader] Uploading video to Page ({file_size_mb:.1f} MB)...")
        print(f"   Title: \"{title}\"")

        url = f"https://graph-video.facebook.com/v20.0/{pid}/videos"

        # Use Resumable Chunked Upload for files > 900 MB (Facebook single-POST limit is 1 GB)
        if file_size_mb > 900:
            print("   📦 File > 900 MB — using Facebook Resumable Chunked Upload...")
            # Phase 1: Start
            start_res = requests.post(
                url,
                data={
                    "access_token": tok,
                    "upload_phase": "start",
                    "file_size": str(file_size_bytes),
                },
                timeout=60,
            )
            start_data = start_res.json()
            if "upload_session_id" not in start_data:
                print(f"⚠️ [Facebook Uploader] Chunked start failed: {start_data}")
                return {"status": "error", "error": start_data}

            session_id = start_data["upload_session_id"]
            fb_video_id = start_data.get("video_id")
            start_offset = int(start_data["start_offset"])
            end_offset = int(start_data["end_offset"])

            # Phase 2: Transfer chunks
            chunk_num = 0
            with open(video_path, "rb") as vf:
                while start_offset < file_size_bytes:
                    chunk_num += 1
                    chunk_size = end_offset - start_offset
                    if chunk_size <= 0:
                        break
                    vf.seek(start_offset)
                    chunk_bytes = vf.read(chunk_size)
                    pct = (end_offset / file_size_bytes) * 100
                    print(f"   ⬆️ Chunk {chunk_num}: {start_offset // (1024*1024)}–{end_offset // (1024*1024)} MB ({pct:.1f}%)")

                    tr_res = requests.post(
                        url,
                        data={
                            "access_token": tok,
                            "upload_phase": "transfer",
                            "upload_session_id": session_id,
                            "start_offset": str(start_offset),
                        },
                        files={"video_file_chunk": ("chunk.mp4", chunk_bytes, "application/octet-stream")},
                        timeout=300,
                    )
                    tr_data = tr_res.json()
                    if "start_offset" not in tr_data:
                        print(f"⚠️ [Facebook Uploader] Chunk {chunk_num} failed: {tr_data}")
                        return {"status": "error", "error": tr_data}
                    start_offset = int(tr_data["start_offset"])
                    end_offset = int(tr_data["end_offset"])

            # Phase 3: Finish
            finish_data = {
                "access_token": tok,
                "upload_phase": "finish",
                "upload_session_id": session_id,
                "title": title,
                "description": description,
                "published": "true" if published else "false",
            }
            tf = None
            files = {}
            try:
                if thumbnail_path and os.path.exists(thumbnail_path):
                    tf = open(thumbnail_path, "rb")
                    files["thumb"] = tf
                    print(f"   Custom Thumbnail: {os.path.basename(thumbnail_path)}")
                fin_res = requests.post(url, data=finish_data, files=files if files else None, timeout=120)
            finally:
                if tf:
                    try:
                        tf.close()
                    except Exception:
                        pass

            fin_json = fin_res.json()
            if fin_json.get("success") and fb_video_id:
                video_url = f"https://www.facebook.com/{pid}/videos/{fb_video_id}"
                print(f"🎉 [Facebook Uploader] Chunked upload complete! Video ID: {fb_video_id}")
                print(f"🔗 Video URL: {video_url}")
                return {"status": "success", "video_id": fb_video_id, "video_url": video_url}
            else:
                print(f"⚠️ [Facebook Uploader] Chunked finish returned: {fin_json}")
                return {"status": "error", "error": fin_json}

        data = {
            "access_token": tok,
            "title": title,
            "description": description,
            "published": "true" if published else "false"
        }

        files = {}
        tf = None
        try:
            with open(video_path, "rb") as vf:
                files["source"] = vf

                if thumbnail_path and os.path.exists(thumbnail_path):
                    tf = open(thumbnail_path, "rb")
                    files["thumb"] = tf
                    print(f"   Custom Thumbnail: {os.path.basename(thumbnail_path)}")

                res = requests.post(url, data=data, files=files, timeout=300)
        finally:
            if tf:
                try:
                    tf.close()
                except Exception:
                    pass

        try:
            res_data = res.json()
        except Exception:
            res_data = {"raw_text": res.text, "status_code": res.status_code}

        if isinstance(res_data, dict) and "id" in res_data:
            fb_video_id = res_data["id"]
            video_url = f"https://www.facebook.com/{pid}/videos/{fb_video_id}"
            print(f"🎉 [Facebook Uploader] Video uploaded successfully! Video ID: {fb_video_id}")
            print(f"🔗 Video URL: {video_url}")
            return {"status": "success", "video_id": fb_video_id, "video_url": video_url}
        else:
            print(f"⚠️ [Facebook Uploader] Video upload returned non-success response: {res_data}")
            return {"status": "error", "error": res_data}

    except Exception as e:
        print(f"⚠️ [Facebook Uploader] Non-blocking exception during video upload: {e}")
        return {"status": "error", "error": str(e)}


def upload_reel(
    reel_path: str,
    description: str,
    page_id: str = None,
    access_token: str = None,
    published: bool = False
) -> dict:
    """
    Uploads a 9:16 vertical Short as a Facebook Reel.
    Safe execution: catches all exceptions without raising so parent pipeline never fails.
    """
    try:
        pid, tok = page_id or None, access_token or None
        if not (pid and tok):
            pid, tok = get_fb_credentials()

        if not (pid and tok):
            return {"status": "skipped", "reason": "missing_credentials"}

        if not reel_path or not os.path.exists(reel_path):
            print(f"⚠️ [Facebook Uploader] Reel file not found: {reel_path}. Skipping.")
            return {"status": "skipped", "reason": "reel_not_found"}

        print(f"\n📱 [Facebook Uploader] Uploading Reel: {os.path.basename(reel_path)}...")

        url = f"https://graph-video.facebook.com/v20.0/{pid}/videos"
        data = {
            "access_token": tok,
            "description": description,
            "published": "true" if published else "false"
        }

        with open(reel_path, "rb") as rf:
            res = requests.post(url, data=data, files={"source": rf}, timeout=180)

        try:
            res_data = res.json()
        except Exception:
            res_data = {"raw_text": res.text, "status_code": res.status_code}

        if isinstance(res_data, dict) and "id" in res_data:
            reel_id = res_data["id"]
            reel_url = f"https://www.facebook.com/{pid}/videos/{reel_id}"
            print(f"🎉 [Facebook Uploader] Reel uploaded successfully! ID: {reel_id}")
            print(f"🔗 Reel URL: {reel_url}")
            return {"status": "success", "reel_id": reel_id, "reel_url": reel_url}
        else:
            print(f"⚠️ [Facebook Uploader] Reel upload returned non-success response: {res_data}")
            return {"status": "error", "error": res_data}
    except Exception as e:
        print(f"⚠️ [Facebook Uploader] Non-blocking exception during reel upload: {e}")
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Facebook Video Uploader CLI")
    parser.add_argument("--video", required=True, help="Path to MP4 video file")
    parser.add_argument("--title", default="", help="Video Title")
    parser.add_argument("--desc", default="", help="Video Description / Caption")
    parser.add_argument("--thumb", default=None, help="Path to Thumbnail Image")
    parser.add_argument("--reel", action="store_true", help="Upload as a Facebook Reel")

    args = parser.parse_args()

    if args.reel:
        upload_reel(args.video, args.desc)
    else:
        upload_video(args.video, args.title, args.desc, args.thumb)
