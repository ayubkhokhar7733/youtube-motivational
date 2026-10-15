#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
update_youtube_thumbnails.py — Push updated high-CTR thumbnails directly to YouTube.
"""

import os
import sys
import time
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
import google.auth.transport.requests

# Reconfigure console for UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def get_client():
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

    cid = os.environ.get("YOUTUBE_CLIENT_ID")
    csec = os.environ.get("YOUTUBE_CLIENT_SECRET")
    rtoken = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    creds = Credentials(
        token=None,
        refresh_token=rtoken,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cid,
        client_secret=csec
    )
    req = google.auth.transport.requests.Request()
    creds.refresh(req)
    return build("youtube", "v3", credentials=creds)

THUMBNAIL_MAPPING = {
    "0z_cqFdncrE": "01_Oct09_Publico_Olvidas_Al_Entrar_Habitacion.jpg",
    "UviitFGauks": "02_Oct10_Publico_Por_Que_Olvidas_Lo_Leido.jpg",
    "GzLAt0dRXx8": "03_Oct11_Publico_Camina_Y_Transforma_Cerebro.jpg",
    "TScApOCz26M": "04_Oct12_HOY_Tu_Cerebro_Pide_Ayuda.jpg",
    "rjtLmdpyPK0": "05_Oct13_Programado_Frota_Tus_Manos_30s.jpg",
    "rBEj6P5DX5M": "06_Oct14_Programado_Soltar_Aprobacion_Ajena.jpg",
    "3uvKz0WZsdc": "07_Privado_Respira_Lento_60_Segundos.jpg",
    "7lAo07dCaH8": "08_Privado_15_Claves_Renacer_Despues_60.jpg",
}

def update_all_thumbnails(target_video_id=None):
    youtube = get_client()
    thumbs_dir = os.path.join(os.path.dirname(__file__), "output", "thumbnails")

    targets = [target_video_id] if target_video_id else list(THUMBNAIL_MAPPING.keys())

    for vid in targets:
        filename = THUMBNAIL_MAPPING.get(vid)
        if not filename:
            print(f"Skipping {vid}: no thumbnail mapped.")
            continue
        thumb_path = os.path.join(thumbs_dir, filename)
        if not os.path.exists(thumb_path):
            print(f"File not found: {thumb_path}")
            continue

        print(f"Uploading thumbnail for video {vid} ({filename})...")
        try:
            request = youtube.thumbnails().set(
                videoId=vid,
                media_body=MediaFileUpload(thumb_path, mimetype="image/jpeg")
            )
            res = request.execute()
            print(f"  Successfully updated thumbnail for {vid}!")
            time.sleep(1)
        except Exception as e:
            print(f"  Error updating {vid}: {e}")

if __name__ == "__main__":
    vid_arg = sys.argv[1] if len(sys.argv) > 1 else None
    update_all_thumbnails(vid_arg)
