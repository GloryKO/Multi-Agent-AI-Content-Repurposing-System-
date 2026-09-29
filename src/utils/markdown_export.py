"""
Exports a completed run into the same shape you'd hand off as a
publish-ready folder: article.md with the image already downloaded and
linked (not just a remote URL that can rot), plus each social variant
as its own markdown file, sitting next to it.

article.md uses YAML frontmatter (title/description/keyword/date/image)
because that's the format most static-site generators and headless
CMSs (Hugo, Jekyll, Next.js MDX, Ghost imports) expect out of the box —
a client can point their publishing pipeline at this folder with
minimal glue code.
"""
from __future__ import annotations

import datetime as dt

import requests

from src.logging_config import get_logger
from src.schemas import FinalPackage
from src.utils.retry import exhausted, with_retries
from src.utils.storage import run_dir
from tenacity import RetryError

log = get_logger(component="markdown_export")


@with_retries(exceptions=(requests.RequestException,))
def _download(url: str) -> bytes:
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return resp.content


def _download_image(image_url: str, dest_path) -> bool:
    """Best-effort: a failed image download shouldn't block the article
    export, same philosophy as the image agent itself being optional."""
    try:
        content = _download(image_url)
    except RetryError as e:
        log.warning("image_download_failed", error=str(exhausted(e, "image download")))
        return False
    except Exception as e:  # noqa: BLE001 - never let image download kill export
        log.warning("image_download_failed", error=str(e))
        return False
    dest_path.write_bytes(content)
    return True


def _yaml_str(value: str) -> str:
    """Quote a string for YAML frontmatter, escaping embedded quotes."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _frontmatter(package: FinalPackage, image_filename: str | None) -> str:
    article = package.article
    lines = [
        "---",
        f"title: {_yaml_str(article.title)}",
        f"description: {_yaml_str(article.meta_description)}",
        f"date: {dt.date.today().isoformat()}",
    ]
    if image_filename:
        lines.append(f"image: ./{image_filename}")
        lines.append(f"image_alt: {_yaml_str(package.image.alt_text)}")
    lines.append("---")
    return "\n".join(lines)


def export_markdown(package: FinalPackage) -> dict:
    """
    Writes to outputs/{run_id}/:
      article.md                - frontmatter + embedded image + full body, ready to publish
      image.<ext>                - the actual image file, downloaded locally
      social/twitter_thread.md
      social/linkedin_post.md
      social/email_snippet.md

    Returns a dict of the paths written, for logging/API responses.
    """
    folder = run_dir(package.run_id)
    written: dict[str, str] = {}

    image_filename = None
    if package.image:
        ext = package.image.url.split("?")[0].rsplit(".", 1)[-1] or "jpg"
        ext = ext if len(ext) <= 4 else "jpg"  # guard against a weird/no extension
        image_path = folder / f"image.{ext}"
        if _download_image(package.image.url, image_path):
            image_filename = image_path.name
            written["image"] = str(image_path)

    body_parts = [_frontmatter(package, image_filename), ""]
    body_parts.append(f"# {package.article.title}")
    body_parts.append("")

    if image_filename:
        body_parts.append(f"![{package.image.alt_text}](./{image_filename})")
        body_parts.append(
            f"*Photo by [{package.image.photographer}]({package.image.photographer_url}) on Pexels*"
        )
        body_parts.append("")

    body_parts.append(package.article.body_markdown)

    article_path = folder / "article.md"
    article_path.write_text("\n".join(body_parts))
    written["article"] = str(article_path)

    social_dir = folder / "social"
    social_dir.mkdir(exist_ok=True)

    twitter_path = social_dir / "twitter_thread.md"
    twitter_path.write_text("\n\n".join(package.social.twitter_thread))
    written["twitter_thread"] = str(twitter_path)

    linkedin_path = social_dir / "linkedin_post.md"
    linkedin_path.write_text(package.social.linkedin_post)
    written["linkedin_post"] = str(linkedin_path)

    email_path = social_dir / "email_snippet.md"
    email_path.write_text(package.social.email_newsletter_snippet)
    written["email_snippet"] = str(email_path)

    log.info("markdown_export_done", run_id=package.run_id, folder=str(folder))
    return written
