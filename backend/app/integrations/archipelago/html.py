from html.parser import HTMLParser


class HeadingCollector(HTMLParser):
    """Collect the text of elements matching a predicate (tag, attrs) -> bool."""

    def __init__(self, predicate):
        super().__init__(convert_charrefs=True)
        self._predicate = predicate
        self._stack: list[tuple[str, dict[str, str], list[str]]] = []
        self.items: list[tuple[str, dict[str, str], str]] = []

    def handle_starttag(self, tag, attrs):
        attr_map = {k: (v or "") for k, v in attrs}
        if self._predicate(tag, attr_map):
            self._stack.append((tag, attr_map, []))

    def handle_data(self, data):
        for _, _, buf in self._stack:
            buf.append(data)

    def handle_endtag(self, tag):
        if self._stack and self._stack[-1][0] == tag:
            t, attrs, buf = self._stack.pop()
            text = " ".join("".join(buf).split())
            if text:
                self.items.append((t, attrs, text))


def collect(html: str, predicate) -> list[tuple[str, dict[str, str], str]]:
    parser = HeadingCollector(predicate)
    parser.feed(html)
    parser.close()
    return parser.items
