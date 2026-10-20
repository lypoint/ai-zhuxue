"""菜单分类完整性与角色切换行为。"""
import json
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess

import pytest


INDEX = Path(__file__).resolve().parents[1] / "index.html"


class Layout(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.stack, self.nodes, self.ids, self.sections = [], [], [], []
        self.pages_by_id = {}
        self.feed(html)
        assert not self.stack

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        self.nodes.append(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
            self.pages_by_id[attrs["id"]] = next((a["data-page"] for a in [attrs, *reversed(self.stack)]
                                                        if "data-page" in a), None)
        if tag == "section":
            self.sections.append(next((a["data-page"] for a in [attrs, *reversed(self.stack)]
                                       if "data-page" in a), None))
        if tag not in {"meta", "link", "img", "input", "br", "hr"}:
            self.stack.append({**attrs, "_tag": tag})

    def handle_endtag(self, tag):
        assert self.stack[-1]["_tag"] == tag
        self.stack.pop()


def test_all_content_belongs_to_a_menu():
    layout = Layout(INDEX.read_text())
    menus = {node["data-nav"] for node in layout.nodes if "data-nav" in node}
    pages = {node["data-page"] for node in layout.nodes if "data-page" in node}
    assert menus == pages == {"overview", "families", "feedback", "teachers", "images",
                              "safety", "pricing", "users", "audit"}
    assert None not in layout.sections
    assert len(layout.ids) == len(set(layout.ids))
    assert all(node["aria-controls"] in layout.ids for node in layout.nodes if "data-nav" in node)


def test_navigation_respects_roles_and_replaces_visible_category():
    node = shutil.which("node")
    if not node:
        pytest.skip("JavaScript navigation check needs Node.js")
    html = INDEX.read_text()
    nodes = [n for n in Layout(html).nodes if "data-nav" in n or "data-page" in n]
    script = html[html.index("function canView("):html.index("async function createUser(")]
    harness = r'''
const assert = require('node:assert/strict');
const nodes = JSON.parse(process.argv[1]);
const makeElement = attributes => ({
  attributes: {...attributes},
  dataset: {nav: attributes['data-nav'], page: attributes['data-page']},
  hidden: 'hidden' in attributes,
  textContent: attributes['data-nav'],
  hasAttribute(key) { return key in this.attributes; },
  setAttribute(key, value) { this.attributes[key] = value; },
  removeAttribute(key) { delete this.attributes[key]; }
});
const buttons = nodes.filter(n => 'data-nav' in n).map(makeElement);
const panels = nodes.filter(n => 'data-page' in n).map(makeElement);
const classes = new Set();
const elements = {
  sidebar: {classList: {
    remove: key => classes.delete(key),
    toggle(key) { if (classes.delete(key)) return false; classes.add(key); return true; }
  }},
  pageTitle: {focus() {}}, menuToggle: makeElement({})
};
const $ = id => elements[id];
const document = {querySelectorAll: selector => selector === '[data-nav]' ? buttons : panels};
const storage = new Map();
const sessionStorage = {setItem: (key, value) => storage.set(key, value)};
const window = {scrollTo() {}};
let ROLE;
'''
    checks = r'''
for (ROLE of ['super', 'admin', 'support']) {
  const expected = ROLE === 'super' ? 9 : ROLE === 'admin' ? 7 : 3;
  for (const requested of [...buttons.map(b => b.dataset.nav), 'unknown']) {
    showPage(requested);
    const selected = buttons.filter(b => b.attributes['aria-current'] === 'page');
    assert.equal(selected.length, 1);
    assert.equal(selected[0].hidden, false);
    assert.equal(buttons.filter(b => !b.hidden).length, expected);
    const page = selected[0].dataset.nav;
    assert.equal(storage.get('cms_page'), page);
    assert.equal(elements.pageTitle.textContent, selected[0].textContent);
    for (const panel of panels) {
      assert.equal(!panel.hidden, panel.dataset.page === page && canView(panel));
    }
  }
  toggleMenu();
  assert.equal(elements.menuToggle.attributes['aria-expanded'], 'true');
  showPage('overview');
  assert.equal(classes.has('nav-open'), false);
  assert.equal(elements.menuToggle.attributes['aria-expanded'], 'false');
}
'''
    subprocess.run([node, "-e", harness + script + checks, json.dumps(nodes)], check=True,
                   capture_output=True, text=True)


def test_image_settings_belong_to_the_correct_category():
    layout = Layout(INDEX.read_text())
    assert layout.pages_by_id['teacherImages'] == 'teachers'
    assert layout.pages_by_id['imageModels'] == 'images'
    assert layout.pages_by_id['imageUsageTable'] == 'images'
    assert 'imageTeacherSelect' not in layout.ids
