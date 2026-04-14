from .base import Post, BaseCrawler
from .quasarzone import QuasarzoneCrawler

CRAWLER_REGISTRY: dict[str, type[BaseCrawler]] = {
    "quasarzone": QuasarzoneCrawler,
}

__all__ = ["Post", "BaseCrawler", "CRAWLER_REGISTRY"]
