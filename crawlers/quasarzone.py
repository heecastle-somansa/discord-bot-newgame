import logging
import re

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from .base import BaseCrawler, Post

logger = logging.getLogger(__name__)


class QuasarzoneCrawler(BaseCrawler):
    """퀘이사존 게시판 크롤러. crawler_type: "quasarzone"

    Playwright(가상 브라우저)로 실제 Chrome처럼 동작하여 봇 차단을 우회합니다.

    sources.json 옵션:
      "popularity": true  →  베스트(인기) 게시물만 수집
    """

    MAX_CONTENT_LENGTH = 3000

    def _fetch_html(self, url: str, post_data: dict | None = None) -> str:
        """Playwright로 페이지 HTML을 가져옵니다."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="ko-KR",
                timezone_id="Asia/Seoul",
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()

            try:
                if post_data:
                    # 베스트 필터: 메인 페이지 먼저 방문 → CSRF 토큰 획득 → POST
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    token = page.evaluate(
                        "() => document.querySelector('meta[name=\"csrf-token\"]')?.content || ''"
                    )
                    if not token:
                        token_el = page.query_selector('input[name="_token"]')
                        token = token_el.get_attribute("value") if token_el else ""

                    if token:
                        post_data["_token"] = token
                        page.evaluate(f"""
                            () => {{
                                const form = document.createElement('form');
                                form.method = 'POST';
                                form.action = '{url}';
                                const data = {{ {', '.join(f'"{k}": "{v}"' for k, v in post_data.items())} }};
                                Object.entries(data).forEach(([k, v]) => {{
                                    const input = document.createElement('input');
                                    input.name = k;
                                    input.value = v;
                                    form.appendChild(input);
                                }});
                                document.body.appendChild(form);
                                form.submit();
                            }}
                        """)
                        page.wait_for_load_state("networkidle", timeout=30000)
                    else:
                        logger.warning(f"[{self.config['id']}] CSRF 토큰 미발견, 일반 목록으로 대체")
                else:
                    page.goto(url, wait_until="networkidle", timeout=30000)

                html = page.content()
                logger.info(f"[{self.config['id']}] 페이지 로드 성공: {url}")

                # 선택자 디버깅: 실제 HTML 앵커 태그 샘플 출력
                soup_debug = BeautifulSoup(html, "lxml")
                sample_links = [
                    a.get("href", "")
                    for a in soup_debug.select("a[href*='/views/']")[:3]
                ]
                logger.info(f"[{self.config['id']}] /views/ 링크 샘플: {sample_links}")

                # li 태그 구조 샘플
                li_sample = soup_debug.select("li")
                li_classes = list({
                    " ".join(li.get("class", [])) for li in li_sample[:20]
                    if li.get("class")
                })
                logger.info(f"[{self.config['id']}] li class 목록: {li_classes[:10]}")

                return html

            except Exception as e:
                logger.error(f"[{self.config['id']}] Playwright 실패: {e}")
                return ""
            finally:
                browser.close()

    def fetch_post_list(self) -> list[Post]:
        url = self.config["url"]
        use_popularity = self.config.get("popularity", False)

        post_data = (
            {
                "_method": "post",
                "type": "",
                "category": "",
                "popularity": "Y",
                "kind": "subject",
                "keyword": "",
                "sort": "num, reply",
                "direction": "DESC",
            }
            if use_popularity
            else None
        )

        html = self._fetch_html(url, post_data)
        if not html:
            logger.error(f"[{self.config['id']}] 목록 페이지 수집 실패")
            return []

        soup = BeautifulSoup(html, "lxml")
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
        html = self._fetch_html(url)
        if not html:
            return ""

        soup = BeautifulSoup(html, "lxml")

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
