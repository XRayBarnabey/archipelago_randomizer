import re
import unicodedata


def normalize_name(name: str) -> str:
    """Normalized form used for name based matching and deduplication."""
    text = re.sub(r"[™®©]", " ", name)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    if text.startswith("the "):
        text = text[4:]
    return text


def slugify(name: str) -> str:
    return normalize_name(name).replace(" ", "-")
