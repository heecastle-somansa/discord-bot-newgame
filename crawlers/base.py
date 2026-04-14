"""
새 크롤러 추가 방법:
1. 이 파일의 BaseCrawler를 상속받는 클래스를 crawlers/ 폴더에 새 파일로 작성
2. fetch_post_list() 와 fetch_post_content() 구현
3. crawlers/__init__.py 의 CRAWLER_REGISTRY 에 등록
4. config/sources.json 에 "crawler_type": "등록한_키" 로 소스 추가
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import requests


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
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    REQUEST_DELAY = 1.5

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def fetch_post_list(self) -> list[Post]:
        """게시판 목록 페이지에서 포스트 목록을 수집합니다."""

    @abstractmethod
    def fetch_post_content(self, url: str) -> str:
        """개별 게시글 URL에서 본문 텍스트를 추출합니다."""

    def _get(self, url: str, timeout: int = 15) -> requests.Response | None:
        try:
            response = requests.get(url, headers=self.HEADERS, timeout=timeout)
            response.raise_for_status()
            time.sleep(self.REQUEST_DELAY)
            return response
        except requests.RequestException:
            return None
