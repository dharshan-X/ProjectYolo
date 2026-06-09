from html.parser import HTMLParser

class MyHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.app_depth = -1
        self.app_close_line = -1

    def handle_starttag(self, tag, attrs):
        if tag in ["img", "input", "br", "hr", "meta", "link", "circle", "polyline", "line", "polygon", "path", "rect", "svg", "button", "span", "a", "p", "h2", "h1", "h3"]: return
        self.stack.append(tag)
        for attr in attrs:
            if attr[0] == "id" and attr[1] == "app":
                self.app_depth = len(self.stack)
                print(f"Found #app at depth {self.app_depth}, line {self.getpos()[0]}")

    def handle_endtag(self, tag):
        if tag in ["img", "input", "br", "hr", "meta", "link", "circle", "polyline", "line", "polygon", "path", "rect", "svg", "button", "span", "a", "p", "h2", "h1", "h3"]: return
        if self.app_depth == len(self.stack) and tag == "div":
            print(f"#app closes at line {self.getpos()[0]}")
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            print(f"Unmatched closing tag {tag} at line {self.getpos()[0]}, expected {self.stack[-1] if self.stack else 'nothing'}")

parser = MyHTMLParser()
with open("desktop/renderer/index.html", "r") as f:
    parser.feed(f.read())
print(f"Remaining stack: {parser.stack}")
