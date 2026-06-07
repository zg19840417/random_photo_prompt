from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_CONTENT_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"

ET.register_namespace("", NS_MAIN)
ET.register_namespace("r", NS_REL)


def _xml_text(value) -> str:
    if value is None:
        return ""
    return str(value)


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _column_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - 64
    return index


def _sheet_xml(rows: list[list[object]]) -> bytes:
    worksheet = ET.Element(f"{{{NS_MAIN}}}worksheet")
    sheet_data = ET.SubElement(worksheet, f"{{{NS_MAIN}}}sheetData")
    for row_index, row in enumerate(rows, 1):
        row_node = ET.SubElement(sheet_data, f"{{{NS_MAIN}}}row", {"r": str(row_index)})
        for column_index, value in enumerate(row, 1):
            text = _xml_text(value)
            cell_ref = f"{_column_name(column_index)}{row_index}"
            cell = ET.SubElement(row_node, f"{{{NS_MAIN}}}c", {"r": cell_ref, "t": "inlineStr"})
            inline = ET.SubElement(cell, f"{{{NS_MAIN}}}is")
            ET.SubElement(inline, f"{{{NS_MAIN}}}t").text = text
    return ET.tostring(worksheet, encoding="utf-8", xml_declaration=True)


def _workbook_xml(sheet_names: list[str]) -> bytes:
    workbook = ET.Element(f"{{{NS_MAIN}}}workbook")
    sheets = ET.SubElement(workbook, f"{{{NS_MAIN}}}sheets")
    for index, name in enumerate(sheet_names, 1):
        ET.SubElement(
            sheets,
            f"{{{NS_MAIN}}}sheet",
            {"name": name, "sheetId": str(index), f"{{{NS_REL}}}id": f"rId{index}"},
        )
    return ET.tostring(workbook, encoding="utf-8", xml_declaration=True)


def _workbook_rels_xml(sheet_names: list[str]) -> bytes:
    rels = ET.Element(f"{{{NS_PACKAGE_REL}}}Relationships")
    for index, _name in enumerate(sheet_names, 1):
        ET.SubElement(
            rels,
            f"{{{NS_PACKAGE_REL}}}Relationship",
            {
                "Id": f"rId{index}",
                "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
                "Target": f"worksheets/sheet{index}.xml",
            },
        )
    return ET.tostring(rels, encoding="utf-8", xml_declaration=True)


def _root_rels_xml() -> bytes:
    rels = ET.Element(f"{{{NS_PACKAGE_REL}}}Relationships")
    ET.SubElement(
        rels,
        f"{{{NS_PACKAGE_REL}}}Relationship",
        {
            "Id": "rId1",
            "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
            "Target": "xl/workbook.xml",
        },
    )
    return ET.tostring(rels, encoding="utf-8", xml_declaration=True)


def _content_types_xml(sheet_count: int) -> bytes:
    types = ET.Element(f"{{{NS_CONTENT_TYPES}}}Types")
    ET.SubElement(types, f"{{{NS_CONTENT_TYPES}}}Default", {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"})
    ET.SubElement(types, f"{{{NS_CONTENT_TYPES}}}Default", {"Extension": "xml", "ContentType": "application/xml"})
    ET.SubElement(types, f"{{{NS_CONTENT_TYPES}}}Override", {"PartName": "/xl/workbook.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"})
    for index in range(1, sheet_count + 1):
        ET.SubElement(types, f"{{{NS_CONTENT_TYPES}}}Override", {"PartName": f"/xl/worksheets/sheet{index}.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"})
    return ET.tostring(types, encoding="utf-8", xml_declaration=True)


def write_workbook(path: Path, sheets: dict[str, list[list[object]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet_names = list(sheets)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", _content_types_xml(len(sheet_names)))
        workbook.writestr("_rels/.rels", _root_rels_xml())
        workbook.writestr("xl/workbook.xml", _workbook_xml(sheet_names))
        workbook.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml(sheet_names))
        for index, name in enumerate(sheet_names, 1):
            workbook.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(sheets[name]))


def _load_shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall(f".//{{{NS_MAIN}}}si"):
        texts = [node.text or "" for node in item.findall(f".//{{{NS_MAIN}}}t")]
        values.append("".join(texts))
    return values


def _cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(f".//{{{NS_MAIN}}}t"))
    value_node = cell.find(f"{{{NS_MAIN}}}v")
    if value_node is None or value_node.text is None:
        return ""
    if cell_type == "s":
        try:
            return shared_strings[int(value_node.text)]
        except (ValueError, IndexError):
            return ""
    if cell_type == "b":
        return "1" if value_node.text == "1" else "0"
    return value_node.text


def _read_sheet(workbook: zipfile.ZipFile, path: str, shared_strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(workbook.read(path))
    rows: list[list[str]] = []
    for row in root.findall(f".//{{{NS_MAIN}}}row"):
        values: list[str] = []
        for cell in row.findall(f"{{{NS_MAIN}}}c"):
            column = _column_index(cell.attrib.get("r", "A")) or len(values) + 1
            while len(values) < column - 1:
                values.append("")
            values.append(_cell_text(cell, shared_strings))
        rows.append(values)
    return rows


def read_workbook(path: Path) -> dict[str, list[list[str]]]:
    with zipfile.ZipFile(path, "r") as workbook:
        shared_strings = _load_shared_strings(workbook)
        workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
        rels_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels_root.findall(f"{{{NS_PACKAGE_REL}}}Relationship")
        }
        result: dict[str, list[list[str]]] = {}
        for sheet in workbook_root.findall(f".//{{{NS_MAIN}}}sheet"):
            name = sheet.attrib["name"]
            rel_id = sheet.attrib.get(f"{{{NS_REL}}}id")
            target = rel_targets.get(rel_id or "")
            if not target:
                continue
            sheet_path = target.lstrip("/")
            if not sheet_path.startswith("xl/"):
                sheet_path = f"xl/{sheet_path}"
            result[name] = _read_sheet(workbook, sheet_path, shared_strings)
        return result
