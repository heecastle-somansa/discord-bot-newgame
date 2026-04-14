import logging
import re

import requests
from bs4 import BeautifulSoup

from .base import BaseCrawler, Post

logger = logging.getLogger(__name__)


class QuasarzoneCrawler(BaseCrawler):
    """퀘이사존 게시판 크롤러. crawler_type: "quasarzone"

    sources.json 옵션:
      "popularity": true  →  베스트(인기) 게시물만 수집
    """

    MAX_CONTENT_LENGTH = 3000

    def _fetch_page(self, url: str) -> requests.Response | None:
        """일반 또는 베스트 필터 페이지를 가져옵니다.
        popularity=true 일 때는 CSRF 토큰을 자동으로 추출하여 POST 요청합니다.
        """
        if not self.config.get("popularity"):
            return self._get(url)

        # 1) 먼저 페이지를 GET 해서 CSRF 토큰과 세션 쿠키 획득
        base_response = self._get(url)
        if not base_response:
            return None

        soup = BeautifulSoup(base_response.text, "lxml")
        token_tag = soup.select_one('meta[name="csrf-token"]') or soup.select_one(
            'input[name="_token"]'
        )
        if not token_tag:
            logger.warning(f"[{self.config['id']}] CSRF 토큰을 찾지 못했습니다. 일반 목록으로 대체합니다.")
            return base_response

        token = token_tag.get("content") or token_tag.get("value", "")
        cookies = dict(base_response.cookies)

        # 2) 세션에 쿠키가 유지된 상태로 베스트 필터 POST 요청
        try:
            response = self._session.post(
                url,
                data={
                    "_method": "post",
                    "_token": token,
                    "type": "",
                    "category": "",
                    "popularity": "Y",
                    "kind": "subject",
                    "keyword": "",
                    "sort": "num, reply",
                    "direction": "DESC",
                },
                timeout=20,
            )
            logger.info(f"[{self.config['id']}] 베스트 필터 POST → HTTP {response.status_code}")
            response.raise_for_status()
            return response
        except requests.HTTPError as e:
            logger.error(f"[{self.config['id']}] 베스트 필터 POST 실패 (HTTP {e.response.status_code})")
            return None
        except requests.RequestException as e:
            logger.error(f"[{self.config['id']}] 베스트 필터 POST 실패 ({type(e).__name__}): {e}")
            return None

    def fetch_post_list(self) -> list[Post]:
        url = self.config["url"]
        response = self._fetch_page(url)
        if not response:
            logger.error(f"[{self.config['id']}] 목록 페이지 요청 실패: {url}")
            return []

        soup = BeautifulSoup(response.text, "lxml")
        posts: list[Post] = []

        for row in soup.select("ul.list-board-wrap li.relative"):
            title_tag = row.select_one("p.subject a")
            if not title_tag:
                continue

            href = title_tag.get("href", "")
            if not href or "/views/" not in href:
                continue

            post_id = href.rstrip("/").split("/")[-1]
            title = title_tag.get_text(strip=True)
            full_url = (
                f"https://quasarzone.com{href}" if href.startswith("/") else href
            )

            category_tag = row.select_one("span.category-item")
            category = category_tag.get_text(strip=True) if category_tag else ""

            comment_tag = row.select_one("span.ctn-count")
            comment_count = comment_tag.get_text(strip=True) if comment_tag else "0"

            posts.append(
                Post(
                    id=post_id,
                    title=title,
                    url=full_url,
                    category=category,
                    comment_count=comment_count,
                )
            )

        logger.info(f"[{self.config['id']}] 목록 {len(posts)}개 수집")
        return posts

    def fetch_post_content(self, url: str) -> str:
        response = self._get(url)
        if not response:
            return ""

        soup = BeautifulSoup(response.text, "lxml")

        content_tag = (
            soup.select_one("div.view-content")
            or soup.select_one("div.article-body")
            or soup.select_one("div#article-content")
        )
        if not content_tag:
            return ""

        for tag in content_tag.select("script, style, iframe"):
            tag.decompose()

        text = content_tag.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[: self.MAX_CONTENT_LENGTH]
