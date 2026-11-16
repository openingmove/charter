"""The sparse-history example with the Establish worked example's draft and template in place, shared by the template and Migrate walkthrough tests."""

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPARSE = ROOT / "examples" / "sparse-history"
TEMPLATES_DOC = ROOT / "skills" / "establish" / "templates.md"
DRAFT = "charter.draft.yaml"


def worked_example():
    text = TEMPLATES_DOC.read_text("utf-8")
    assert "### Worked example" in text, "templates.md lost the heading that introduces the worked example"
    example = text.split("### Worked example")[1].split("\n## 3.")[0]  # the template's own "## " headings rule out splitting on any H2
    draft = re.search(r"```yaml\n(.*?)```", example, re.S)
    template = re.search(r"```markdown\n(.*?)```", example, re.S)
    assert draft and template, "the worked example needs one yaml block and one markdown block"
    return draft.group(1), template.group(1)


def sparse_kb(tmp_path):
    folder = tmp_path / "sparse-history"
    shutil.copytree(SPARSE, folder)
    draft, template = worked_example()
    (folder / "Templates").mkdir()
    (folder / "Templates" / "Story.md").write_text(template, encoding="utf-8")
    (folder / DRAFT).write_text(draft, encoding="utf-8")
    return folder
