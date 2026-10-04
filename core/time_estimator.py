import os
import json
import time

class TimeEstimator:
    @staticmethod
    def get_history_path():
        import config
        return os.path.join(os.path.dirname(config.USER_SETTINGS_PATH), "generation_history.json")

    @classmethod
    def load_history(cls):
        path = cls.get_history_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        return data.get("runs", [])
            except Exception:
                pass
        return []

    @classmethod
    def save_history(cls, history):
        path = cls.get_history_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except Exception:
            pass

    @classmethod
    def add_run(cls, aspect_ratio, target_duration, media_preference, enable_zoom, scene_count, video_clip_count, total_time_seconds):
        history = cls.load_history()
        history.append({
            "timestamp": time.time(),
            "aspect_ratio": aspect_ratio,
            "target_duration": target_duration,
            "media_preference": media_preference,
            "enable_zoom": enable_zoom,
            "scene_count": scene_count,
            "video_clip_count": video_clip_count,
            "total_time_seconds": total_time_seconds
        })
        # Keep only the last 30 runs for dynamic adaptation
        if len(history) > 30:
            history = history[-30:]
        cls.save_history(history)

    @classmethod
    def predict(cls, aspect_ratio, target_duration, media_preference, enable_zoom, scene_count=None, video_clip_count=None):
        """
        Predict total generation time using multi-variable regression or weighted averages from past runs.
        Falls back to a robust heuristic formula if history is sparse.
        """
        history = cls.load_history()
        
        # Estimate scene count if not provided
        est_scenes = scene_count if scene_count is not None else int(target_duration / 8.0)
        
        # Estimate video clip count if not provided
        if video_clip_count is not None:
            est_videos = video_clip_count
        else:
            if media_preference == "video_only":
                est_videos = est_scenes
            elif media_preference == "video_first":
                est_videos = int(est_scenes * 0.7)
            else:
                est_videos = 0
        est_images = est_scenes - est_videos

        # 1. Standard Heuristic Baseline
        t_script = 6.0
        t_tts = 1.0 + (target_duration * 0.15)
        t_download = (est_images * 4.0) + (est_videos * 10.0)
        
        render_factor = 1.5
        if enable_zoom:
            render_factor += 1.0
        render_factor += (est_videos / max(1, est_scenes)) * 2.0
        t_render = target_duration * render_factor
        
        heuristic_estimate = t_script + t_tts + t_download + t_render

        if len(history) < 3:
            return round(heuristic_estimate, 1)

        # 2. Smart AI Estimation (Weighted Similarity)
        similarities = []
        for run in history:
            ar_match = 1.0 if run.get("aspect_ratio") == aspect_ratio else 0.5
            mp_match = 1.0 if run.get("media_preference") == media_preference else 0.5
            zoom_match = 1.0 if run.get("enable_zoom") == enable_zoom else 0.7
            
            dur_ratio = min(run.get("target_duration", 60), target_duration) / max(run.get("target_duration", 60), target_duration)
            
            past_scenes = run.get("scene_count", int(run.get("target_duration", 60) / 8))
            scene_ratio = min(past_scenes, est_scenes) / max(past_scenes, est_scenes, 1)
            
            past_videos = run.get("video_clip_count", 0)
            if est_videos == 0 and past_videos == 0:
                video_ratio = 1.0
            else:
                video_ratio = min(past_videos, est_videos) / max(past_videos, est_videos, 1)

            score = (ar_match * 0.1) + (mp_match * 0.1) + (zoom_match * 0.1) + (dur_ratio * 0.3) + (scene_ratio * 0.2) + (video_ratio * 0.2)
            similarities.append((score, run))

        similarities.sort(key=lambda x: x[0], reverse=True)

        weighted_sum = 0.0
        weight_sum = 0.0
        
        for score, run in similarities[:5]:
            if score < 0.6:
                continue
            
            past_time = run["total_time_seconds"]
            past_dur = run.get("target_duration", 60)
            
            scaling = target_duration / max(past_dur, 1.0)
            if scene_count is not None:
                past_scenes = run.get("scene_count", 1)
                scaling = 0.5 * scaling + 0.5 * (scene_count / max(past_scenes, 1.0))
                
            adjusted_time = past_time * scaling
            weight = score ** 2
            weighted_sum += adjusted_time * weight
            weight_sum += weight

        if weight_sum > 0:
            ai_estimate = weighted_sum / weight_sum
            final_estimate = 0.8 * ai_estimate + 0.2 * heuristic_estimate
            return round(final_estimate, 1)
            
        return round(heuristic_estimate, 1)
