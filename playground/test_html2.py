from html.parser import HTMLParser

class MyHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.app_depth = -1

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag)
        for attr in attrs:
            if attr[0] == "id" and attr[1] == "app":
                self.app_depth = len(self.stack)
        
        if self.app_depth != -1 and len(self.stack) == self.app_depth + 1:
            id_attr = next((a[1] for a in attrs if a[0] == "id"), None)
            class_attr = next((a[1] for a in attrs if a[0] == "class"), None)
            print(f"Direct child of #app: tag={tag}, id={id_attr}, class={class_attr}, line={self.getpos()[0]}")

    def handle_endtag(self, tag):
        if self.app_depth == len(self.stack):
            self.app_depth = -1 # exited app
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()

parser = MyHTMLParser()
with open("desktop/renderer/index.html", "r") as f:
    parser.feed(f.read())
