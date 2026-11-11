from __future__ import annotations

from app.parser import ArticleParser


ARTICLE_HTML = """
<html>
  <head>
    <title>页面标题</title>
    <meta name="author" content="作者A">
    <meta name="keywords" content="Python, CSDN">
  </head>
  <body>
    <main id="content_views">
      <h1>正文标题</h1>
      <p>这是正文内容，用于测试文章提取。</p>
      <pre><code>print('hello')</code></pre>
      <img src="/images/a.png" onerror="alert(1)">
      <div class="comment">不应该被保存</div>
    </main>
    <aside class="recommend">推荐内容</aside>
  </body>
</html>
"""


def test_parser_keeps_body_and_removes_non_body_content() -> None:
    parsed = ArticleParser().parse(ARTICLE_HTML, "https://blog.csdn.net/demo/article/details/123")

    assert parsed.metadata.title == "正文标题"
    assert parsed.metadata.article_id == "123"
    assert parsed.metadata.author == "作者A"
    assert parsed.metadata.tags == ["Python", "CSDN"]
    assert "这是正文内容" in parsed.body_html
    assert "print('hello')" in parsed.body_html
    assert "不应该被保存" not in parsed.body_html
    assert "onerror" not in parsed.body_html
    assert parsed.resource_urls == ["https://blog.csdn.net/images/a.png"]
