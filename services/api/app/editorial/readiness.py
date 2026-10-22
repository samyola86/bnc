from datetime import datetime

from app.ingestion.service import now


def readiness(content, title, language, credits):
    checks = {
        "title": (bool(title.strip()), "Add a headline"),
        "body": (bool(content.get("body", "").strip()), "Add article content"),
        "category": (bool(content.get("category", "").strip()), "Add a category"),
        "tags": (bool(content.get("tags")), "Add at least one tag"),
        "contributors": (bool(content.get("contributors")), "Add a contributor"),
        "destinations": (bool(content.get("destinations")), "Select a publishing destination"),
        "format": (
            content.get("format", "article") in {"article", "news_bite"},
            "Select a valid format",
        ),
        "language": (language in {"bn", "en"}, "Select a valid language"),
    }
    if "instagram" in content.get("destinations", []):
        checks["cover_image_id"] = (
            bool(content.get("cover_image_id")),
            "Add an Instagram cover image",
        )
    if content.get("scheduled_at"):
        try:
            value = datetime.fromisoformat(content["scheduled_at"])
            valid = value.utcoffset() is not None and value > now()
        except (ValueError, TypeError):
            valid = False
        checks["scheduled_at"] = (valid, "Choose a future publication time in Dhaka")
    if any(credit.get("rights_status") == "prohibited" for credit in credits):
        checks["credits_rights"] = (False, "Resolve prohibited source usage rights")
    if content.get("format") == "news_bite":
        from app.newsbite.service import graphic_errors

        checks.pop("body", None)
        checks["news_bite"] = (True, "")
        checks.update({key: (False, message) for key, message in graphic_errors(content).items()})
    return {
        "complete": sum(valid for valid, _ in checks.values()),
        "total": len(checks),
        "errors": {key: message for key, (valid, message) in checks.items() if not valid},
    }
