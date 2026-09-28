"""
Phase 7 - Document Agent (implemented).

Real file manipulation using python-docx, openpyxl, python-pptx, and pypdf -
no GUI automation. Always preserves the original file: every "edit" writes
to a new path unless the user explicitly passes overwrite=True.
"""
from __future__ import annotations

from pathlib import Path

from app.security.permissions import PermissionLevel
from app.tools.base import Tool, ToolResult


def _safe_output_path(path: Path, overwrite: bool, suffix: str = "_edited") -> Path:
    if overwrite:
        return path
    return path.with_name(f"{path.stem}{suffix}{path.suffix}")


class OpenDocxTool(Tool):
    name = "documents.open_docx"
    description = "Open a Word document and return its structure (paragraphs, headings)."
    permission_level = PermissionLevel.OBSERVE
    parameters_schema = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}

    def run(self, path: str, **kwargs) -> ToolResult:
        try:
            import docx
        except ImportError:
            return ToolResult(success=False, error="python-docx is not installed. pip install python-docx")

        file_path = Path(path).expanduser()
        if not file_path.exists():
            return ToolResult(success=False, error=f"File does not exist: {file_path}")
        try:
            document = docx.Document(str(file_path))
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Could not open document: {e}")

        paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
        title = paragraphs[0] if paragraphs else ""
        return ToolResult(
            success=True,
            data={"path": str(file_path), "title": title, "paragraph_count": len(paragraphs), "paragraphs": paragraphs},
        )


class EditDocxTool(Tool):
    name = "documents.edit_docx"
    description = (
        "Edit a Word document: change the title (first paragraph/heading) and/or "
        "find-and-replace text. Writes to a new file unless overwrite=True."
    )
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "new_title": {"type": "string"},
            "find": {"type": "string"},
            "replace": {"type": "string"},
            "output_path": {"type": "string", "description": "Optional explicit output path"},
            "overwrite": {"type": "boolean"},
        },
        "required": ["path"],
    }

    def run(
        self,
        path: str,
        new_title: str | None = None,
        find: str | None = None,
        replace: str | None = None,
        output_path: str | None = None,
        overwrite: bool = False,
        **kwargs,
    ) -> ToolResult:
        try:
            import docx
        except ImportError:
            return ToolResult(success=False, error="python-docx is not installed. pip install python-docx")

        file_path = Path(path).expanduser()
        if not file_path.exists():
            return ToolResult(success=False, error=f"File does not exist: {file_path}")

        try:
            document = docx.Document(str(file_path))
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Could not open document: {e}")

        if new_title is not None and document.paragraphs:
            document.paragraphs[0].text = new_title
            for run in document.paragraphs[0].runs[1:]:
                run.text = ""

        if find is not None and replace is not None:
            for paragraph in document.paragraphs:
                if find in paragraph.text:
                    for run in paragraph.runs:
                        if find in run.text:
                            run.text = run.text.replace(find, replace)
                    if find in paragraph.text and not any(find in r.text for r in paragraph.runs):
                        # find spanned multiple runs; rebuild paragraph text as a fallback
                        full_text = paragraph.text.replace(find, replace)
                        for run in paragraph.runs:
                            run.text = ""
                        if paragraph.runs:
                            paragraph.runs[0].text = full_text
                        else:
                            paragraph.text = full_text

        out_path = Path(output_path).expanduser() if output_path else _safe_output_path(file_path, overwrite)
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            document.save(str(out_path))
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Could not save document: {e}")

        return ToolResult(success=True, data={"output_path": str(out_path)})

    def verify(self, result: ToolResult, **kwargs) -> ToolResult:
        if result.success:
            result.success = Path(result.data["output_path"]).exists()
        return result


class CreateReportTool(Tool):
    name = "documents.create_report"
    description = "Create a new, formatted Word document from a title and body content."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "content": {"type": "string", "description": "Body text; blank lines become paragraph breaks"},
            "output_path": {"type": "string"},
        },
        "required": ["title", "content", "output_path"],
    }

    def run(self, title: str, content: str, output_path: str, **kwargs) -> ToolResult:
        try:
            import docx
        except ImportError:
            return ToolResult(success=False, error="python-docx is not installed. pip install python-docx")

        document = docx.Document()
        document.add_heading(title, level=1)
        for para in content.split("\n\n"):
            if para.strip():
                document.add_paragraph(para.strip())

        out_path = Path(output_path).expanduser()
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            document.save(str(out_path))
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Could not save document: {e}")

        return ToolResult(success=True, data={"output_path": str(out_path)})

    def verify(self, result: ToolResult, **kwargs) -> ToolResult:
        if result.success:
            result.success = Path(result.data["output_path"]).exists()
        return result


class SummarizePdfTool(Tool):
    name = "documents.extract_pdf_text"
    description = "Extract text content from a PDF file (page by page)."
    permission_level = PermissionLevel.OBSERVE
    parameters_schema = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}

    def run(self, path: str, max_pages: int = 50, **kwargs) -> ToolResult:
        try:
            from pypdf import PdfReader
        except ImportError:
            return ToolResult(success=False, error="pypdf is not installed. pip install pypdf")

        file_path = Path(path).expanduser()
        if not file_path.exists():
            return ToolResult(success=False, error=f"File does not exist: {file_path}")

        try:
            reader = PdfReader(str(file_path))
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Could not open PDF: {e}")

        pages_text = []
        for page in reader.pages[:max_pages]:
            try:
                pages_text.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001
                pages_text.append("")

        return ToolResult(
            success=True,
            data={"page_count": len(reader.pages), "pages": pages_text, "text": "\n\n".join(pages_text)},
        )


class ExcelCalculateTotalsTool(Tool):
    name = "documents.excel_column_totals"
    description = "Open an Excel file and compute the sum of one or more numeric columns."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "sheet_name": {"type": "string"},
            "columns": {"type": "array", "items": {"type": "string"}, "description": "Column letters, e.g. ['B','C']"},
            "output_path": {"type": "string"},
        },
        "required": ["path", "columns"],
    }

    def run(
        self, path: str, columns: list[str], sheet_name: str | None = None, output_path: str | None = None, **kwargs
    ) -> ToolResult:
        try:
            import openpyxl
        except ImportError:
            return ToolResult(success=False, error="openpyxl is not installed. pip install openpyxl")

        file_path = Path(path).expanduser()
        if not file_path.exists():
            return ToolResult(success=False, error=f"File does not exist: {file_path}")

        try:
            workbook = openpyxl.load_workbook(str(file_path))
            sheet = workbook[sheet_name] if sheet_name else workbook.active
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Could not open workbook: {e}")

        totals: dict[str, float] = {}
        for col in columns:
            total = 0.0
            for cell in sheet[col]:
                if isinstance(cell.value, (int, float)):
                    total += cell.value
            totals[col] = total

        if output_path:
            last_row = sheet.max_row + 2
            sheet.cell(row=last_row, column=1, value="TOTAL")
            for col in columns:
                col_index = openpyxl.utils.column_index_from_string(col)
                sheet.cell(row=last_row, column=col_index, value=totals[col])
            out_path = Path(output_path).expanduser()
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                workbook.save(str(out_path))
            except Exception as e:  # noqa: BLE001
                return ToolResult(success=False, error=f"Could not save workbook: {e}")
            return ToolResult(success=True, data={"totals": totals, "output_path": str(out_path)})

        return ToolResult(success=True, data={"totals": totals})


class CreatePptxFromReportTool(Tool):
    name = "documents.create_pptx_from_report"
    description = "Create a simple PowerPoint deck from a title and a list of slide bullet sections."
    permission_level = PermissionLevel.NORMAL
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "slides": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"heading": {"type": "string"}, "bullets": {"type": "array", "items": {"type": "string"}}},
                },
            },
            "output_path": {"type": "string"},
        },
        "required": ["title", "slides", "output_path"],
    }

    def run(self, title: str, slides: list[dict], output_path: str, **kwargs) -> ToolResult:
        try:
            from pptx import Presentation
            from pptx.util import Inches
        except ImportError:
            return ToolResult(success=False, error="python-pptx is not installed. pip install python-pptx")

        prs = Presentation()
        title_slide = prs.slides.add_slide(prs.slide_layouts[0])
        title_slide.shapes.title.text = title

        bullet_layout = prs.slide_layouts[1]
        for slide_spec in slides:
            slide = prs.slides.add_slide(bullet_layout)
            slide.shapes.title.text = slide_spec.get("heading", "")
            body = slide.placeholders[1].text_frame
            bullets = slide_spec.get("bullets", [])
            if bullets:
                body.text = bullets[0]
                for bullet in bullets[1:]:
                    p = body.add_paragraph()
                    p.text = bullet

        out_path = Path(output_path).expanduser()
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            prs.save(str(out_path))
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=f"Could not save presentation: {e}")

        return ToolResult(success=True, data={"output_path": str(out_path)})

    def verify(self, result: ToolResult, **kwargs) -> ToolResult:
        if result.success:
            result.success = Path(result.data["output_path"]).exists()
        return result
