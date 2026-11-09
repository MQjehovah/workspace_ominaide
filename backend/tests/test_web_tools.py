import base64

import pytest

from ai.mcp.tools.web import _unwrap_bing_url, _validate_url, parse_bing_results


def test_parse_bing_results():
    html = """
    <ol id="b_results">
      <li class="b_algo">
        <h2><a href="https://example.com/article">示例标题</a></h2>
        <div class="b_caption"><p>这是摘要。</p></div>
        <cite>example.com</cite>
      </li>
    </ol>
    """
    results = parse_bing_results(html, 5)
    assert len(results) == 1
    assert results[0]["title"] == "示例标题"
    assert results[0]["url"] == "https://example.com/article"
    assert results[0]["snippet"] == "这是摘要。"


def test_unwrap_bing_redirect():
    target = "https://example.com/page"
    token = "a1" + base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
    href = f"https://www.bing.com/ck/a?u={token}&ntb=1"
    assert _unwrap_bing_url(href, "https://cn.bing.com") == target


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/health",
        "http://192.168.2.10:8123/api/states",
        "http://localhost/",
        "file:///etc/passwd",
    ],
)
def test_web_fetch_rejects_internal_targets(url):
    with pytest.raises(ValueError):
        _validate_url(url)
