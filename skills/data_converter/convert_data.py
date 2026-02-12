"""
数据格式转换技能实现
"""
import json
import yaml
import csv
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, Optional
import chardet


async def convert_data(input_path: str,
                       output_path: str,
                       input_format: Optional[str] = None,
                       output_format: Optional[str] = None,
                       encoding: str = "utf-8") -> Dict[str, Any]:
    """
    数据格式转换

    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径
        input_format: 输入格式（json/yaml/csv/xml/auto）
        output_format: 输出格式（json/yaml/csv/xml）
        encoding: 文件编码

    Returns:
        转换结果
    """
    try:
        input_file = Path(input_path)
        if not input_file.exists():
            return {"success": False, "error": f"输入文件不存在: {input_path}"}

        if input_format is None:
            input_format = _detect_format(input_path)

        data = await _read_data(input_path, input_format, encoding)

        if output_format is None:
            ext = Path(output_path).suffix.lower()
            output_format = _extension_to_format(ext)

        result_data = await _write_data(data, output_path, output_format)

        return {
            "success": True,
            "input_path": input_path,
            "output_path": output_path,
            "input_format": input_format,
            "output_format": output_format,
            **result_data
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def _detect_format(file_path: str) -> str:
    """自动检测文件格式"""
    ext = Path(file_path).suffix.lower()
    return _extension_to_format(ext)


def _extension_to_format(ext: str) -> str:
    """扩展名转格式"""
    format_map = {
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".csv": "csv",
        ".xml": "xml"
    }
    return format_map.get(ext, "json")


async def _read_data(file_path: str, format: str, encoding: str) -> Any:
    """读取数据"""
    with open(file_path, 'rb') as f:
        raw_content = f.read()
        detected = chardet.detect(raw_content)
        if detected['confidence'] > 0.7:
            encoding = detected['encoding']
        content = raw_content.decode(encoding or 'utf-8')

    if format == "json":
        return json.loads(content)
    elif format == "yaml":
        return yaml.safe_load(content)
    elif format == "csv":
        return _read_csv(content)
    elif format == "xml":
        return _xml_to_dict(content)
    else:
        return content


async def _write_data(data: Any, output_path: str, format: str) -> Dict[str, Any]:
    """写入数据"""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if format == "json":
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    elif format == "yaml":
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
    elif format == "csv":
        _write_csv(data, output_path)
    elif format == "xml":
        _dict_to_xml(data, output_path)

    return {"file_size": Path(output_path).stat().st_size}


def _read_csv(content: str) -> list:
    """读取CSV为列表"""
    lines = content.strip().split('\n')
    reader = csv.DictReader(lines)
    return list(reader)


def _write_csv(data: list, output_path: str):
    """写入CSV"""
    if not data:
        return
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)


def _xml_to_dict(xml_str: str) -> Dict:
    """XML转字典"""
    root = ET.fromstring(xml_str)
    return {root.tag: _xml_element_to_dict(root)}


def _xml_element_to_dict(element) -> Any:
    """XML元素转字典"""
    if len(element) == 0:
        return element.text
    result = {}
    for child in element:
        child_data = _xml_element_to_dict(child)
        if child.tag in result:
            if not isinstance(result[child.tag], list):
                result[child.tag] = [result[child.tag]]
            result[child.tag].append(child_data)
        else:
            result[child.tag] = child_data
    return result


def _dict_to_xml(data: Dict, output_path: str):
    """字典转XML"""
    def dict_to_xml(parent, data):
        for key, value in data.items():
            if isinstance(value, list):
                for item in value:
                    child = ET.SubElement(parent, key)
                    dict_to_xml(child, item if isinstance(item, dict) else {'value': str(item)})
            elif isinstance(value, dict):
                child = ET.SubElement(parent, key)
                dict_to_xml(child, value)
            else:
                child = ET.SubElement(parent, key)
                child.text = str(value)

    root = ET.Element('root')
    dict_to_xml(root, data)
    tree = ET.ElementTree(root)
    tree.write(output_path, encoding='utf-8', xml_declaration=True)
