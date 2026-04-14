"""
새 크롤러 추가 방법:
1. 이 파일의 BaseCrawler를 상속받는 클래스를 crawlers/ 폴더에 새 파일로 작성
2. fetch_post_list() 와 fetch_post_content() 구현
3. crawlers/__init__.py 의 CRAWLER_REGISTRY 에 등록
4. config/sources.json 에 "crawler_type": "등록한_키" 로 소스 추가
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class Post:
    id: str
    title: str
    url: str
    category: str = ""
    comment_count: str = "0"
    content: str = ""


class BaseCrawler(ABC):
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }
    REQUEST_DELAY = 2.0

    def __init__(self, config: dict):
        self.config = config
        self._session = requests.Session()
        self._session.headers.update(self.HEADERS)

    @abstractmethod
    def fetch_post_list(self) -> list[Post]:
        """게시판 목록 페이지에서 포스트 목록을 수집합니다."""

    @abstractmethod
    def fetch_post_content(self, url: str) -> str:
        """개별 게시글 URL에서 본문 텍스트를 추출합니다."""

    def _get(self, url: str, timeout: int = 20) -> requests.Response | None:
        try:
            response = self._session.get(url, timeout=timeout)
            logger.info(f"GET {url} → HTTP {response.status_code}")
            response.raise_for_status()
            time.sleep(self.REQUEST_DELAY)
            return response
        except requests.HTTPError as e:
            logger.error(f"GET 실패 (HTTP {e.response.status_code}): {url}")
            return None
        except requests.RequestException as e:
            logger.error(f"GET 실패 ({type(e).__name__}): {url}")
            return None
