from html.parser import HTMLParser

class MyHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        
    def handle_starttag(self, tag, attrs):
        if tag in ["img", "input", "br", "hr", "meta", "link", "circle", "polyline", "line", "polygon", "path", "rect", "svg", "button", "span", "a", "p", "h2", "h1", "h3"]: return
        
        self.stack.append(tag)
        for attr in attrs:
            if attr[0] == "id" and attr[1] in ["widgets-panel", "app", "workers-panel"]:
                print(f"Found {attr[1]} at line {self.getpos()[0]}, hierarchy: {' > '.join(self.stack)}")

    def handle_endtag(self, tag):
        if tag in ["img", "input", "br", "hr", "meta", "link", "circle", "polyline", "line", "polygon", "path", "rect", "svg", "button", "span", "a", "p", "h2", "h1", "h3"]: return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()

parser = MyHTMLParser()
with open("desktop/renderer/index.html", "r") as f:
    parser.feed(f.read())
