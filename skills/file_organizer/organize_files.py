"""
文件组织技能实现
"""
import os
import shutil
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
import datetime


async def organize_files(directory: str,
                         operations: List[str],
                         file_pattern: Optional[str] = None,
                         target_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    组织文件

    Args:
        directory: 目录路径
        operations: 要执行的操作列表
        file_pattern: 文件模式（如 *.txt, *.jpg）
        target_dir: 目标目录（用于移动/复制）

    Returns:
        组织结果
    """
    try:
        dir_path = Path(directory)
        if not dir_path.exists() or not dir_path.is_dir():
            return {"success": False, "error": f"目录不存在或不是目录: {directory}"}

        operations_performed = []
        files_processed = []
        total_size = 0

        # 获取文件列表
        if file_pattern:
            files = list(dir_path.rglob(file_pattern))
        else:
            files = list(dir_path.iterdir())

        # 过滤出文件（排除目录）
        files = [f for f in files if f.is_file()]

        if not files:
            return {"success": True, "message": "没有找到文件", "files_processed": []}

        for op in operations:
            if op == "categorize_by_type":
                categorized = await _categorize_by_type(files, dir_path)
                operations_performed.append(f"按类型分类: {categorized['categories']} 个类别")
                files_processed.extend(categorized.get("processed_files", []))

            elif op == "rename_by_pattern":
                if not target_dir:
                    target_dir = str(dir_path)
                renamed = await _rename_by_pattern(files, target_dir)
                operations_performed.append(f"按模式重命名: {renamed['renamed_count']} 个文件")
                files_processed.extend(renamed.get("processed_files", []))

            elif op == "find_duplicates":
                duplicates = await _find_duplicates(files)
                operations_performed.append(f"查找重复文件: {duplicates['duplicate_count']} 个重复文件组")
                files_processed.extend(duplicates.get("processed_files", []))

            elif op == "clean_temp_files":
                cleaned = await _clean_temp_files(files)
                operations_performed.append(f"清理临时文件: {cleaned['cleaned_count']} 个文件")
                files_processed.extend(cleaned.get("processed_files", []))

            elif op == "analyze_files":
                analysis = await _analyze_files(files)
                operations_performed.append(f"文件分析: 总计 {analysis['total_files']} 个文件")
                total_size = analysis.get("total_size", 0)
                files_processed.extend(analysis.get("processed_files", []))

            elif op == "move_to_target" and target_dir:
                moved = await _move_to_target(files, target_dir)
                operations_performed.append(f"移动到目标目录: {moved['moved_count']} 个文件")
                files_processed.extend(moved.get("processed_files", []))

            elif op == "copy_to_target" and target_dir:
                copied = await _copy_to_target(files, target_dir)
                operations_performed.append(f"复制到目标目录: {copied['copied_count']} 个文件")
                files_processed.extend(copied.get("processed_files", []))

        # 去重files_processed
        unique_files = []
        seen = set()
        for file_info in files_processed:
            file_path = file_info.get("path")
            if file_path and file_path not in seen:
                seen.add(file_path)
                unique_files.append(file_info)

        return {
            "success": True,
            "directory": directory,
            "total_files": len(files),
            "operations_performed": operations_performed,
            "files_processed": unique_files[:50],  # 限制返回数量
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2) if total_size > 0 else 0
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def _categorize_by_type(files: List[Path], base_dir: Path) -> Dict[str, Any]:
    """按文件类型分类"""
    categories = {}
    processed_files = []

    # 文件类型映射
    type_map = {
        "images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp"],
        "documents": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".md", ".csv", ".xls", ".xlsx"],
        "code": [".py", ".js", ".ts", ".java", ".cpp", ".c", ".h", ".html", ".css", ".json", ".yaml", ".yml"],
        "archives": [".zip", ".tar", ".gz", ".rar", ".7z"],
        "audio": [".mp3", ".wav", ".flac", ".aac", ".ogg"],
        "video": [".mp4", ".avi", ".mov", ".mkv", ".wmv"],
        "executables": [".exe", ".app", ".dmg", ".deb", ".rpm"]
    }

    for file_path in files:
        suffix = file_path.suffix.lower()
        category = "others"

        for cat, extensions in type_map.items():
            if suffix in extensions:
                category = cat
                break

        # 创建分类目录
        category_dir = base_dir / category
        category_dir.mkdir(exist_ok=True)

        # 移动文件到分类目录
        try:
            target_path = category_dir / file_path.name
            if file_path != target_path:
                shutil.move(str(file_path), str(target_path))
                processed_files.append({
                    "path": str(target_path),
                    "original_path": str(file_path),
                    "category": category,
                    "operation": "categorized"
                })
            else:
                processed_files.append({
                    "path": str(file_path),
                    "category": category,
                    "operation": "already_in_category"
                })

            if category not in categories:
                categories[category] = 0
            categories[category] += 1

        except Exception as e:
            processed_files.append({
                "path": str(file_path),
                "error": str(e),
                "operation": "failed"
            })

    return {
        "categories": len(categories),
        "category_counts": categories,
        "processed_files": processed_files
    }


async def _rename_by_pattern(files: List[Path], target_dir: str) -> Dict[str, Any]:
    """按模式重命名文件"""
    renamed_count = 0
    processed_files = []
    target_path = Path(target_dir)

    for i, file_path in enumerate(files):
        try:
            # 生成新文件名：前缀_序号_日期.扩展名
            timestamp = datetime.datetime.now().strftime("%Y%m%d")
            new_name = f"file_{i+1:04d}_{timestamp}{file_path.suffix}"
            new_path = target_path / new_name

            if file_path != new_path:
                shutil.move(str(file_path), str(new_path))
                renamed_count += 1
                processed_files.append({
                    "path": str(new_path),
                    "original_name": file_path.name,
                    "new_name": new_name,
                    "operation": "renamed"
                })
            else:
                processed_files.append({
                    "path": str(file_path),
                    "operation": "no_change"
                })

        except Exception as e:
            processed_files.append({
                "path": str(file_path),
                "error": str(e),
                "operation": "failed"
            })

    return {
        "renamed_count": renamed_count,
        "processed_files": processed_files
    }


async def _find_duplicates(files: List[Path]) -> Dict[str, Any]:
    """查找重复文件"""
    file_hashes = {}
    duplicates = []
    processed_files = []

    for file_path in files:
        try:
            # 计算文件哈希
            file_hash = _calculate_file_hash(file_path)

            if file_hash in file_hashes:
                duplicates.append({
                    "original": str(file_hashes[file_hash]),
                    "duplicate": str(file_path),
                    "hash": file_hash,
                    "size": file_path.stat().st_size
                })
                processed_files.append({
                    "path": str(file_path),
                    "hash": file_hash,
                    "status": "duplicate"
                })
            else:
                file_hashes[file_hash] = file_path
                processed_files.append({
                    "path": str(file_path),
                    "hash": file_hash,
                    "status": "unique"
                })

        except Exception as e:
            processed_files.append({
                "path": str(file_path),
                "error": str(e),
                "status": "error"
            })

    # 按重复组整理
    duplicate_groups = {}
    for dup in duplicates:
        hash_key = dup["hash"]
        if hash_key not in duplicate_groups:
            duplicate_groups[hash_key] = []
        duplicate_groups[hash_key].append(dup["duplicate"])

    return {
        "duplicate_count": len(duplicates),
        "unique_count": len(file_hashes),
        "duplicate_groups": duplicate_groups,
        "processed_files": processed_files
    }


def _calculate_file_hash(file_path: Path, chunk_size: int = 8192) -> str:
    """计算文件哈希"""
    hash_md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(chunk_size), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


async def _clean_temp_files(files: List[Path]) -> Dict[str, Any]:
    """清理临时文件"""
    cleaned_count = 0
    processed_files = []

    # 临时文件模式
    temp_patterns = [
        "~$",  # Office临时文件
        ".tmp",
        ".temp",
        ".bak",
        ".backup",
        "Thumbs.db",
        ".DS_Store"
    ]

    for file_path in files:
        try:
            file_name = file_path.name
            is_temp = any(pattern in file_name for pattern in temp_patterns)

            if is_temp:
                file_path.unlink()
                cleaned_count += 1
                processed_files.append({
                    "path": str(file_path),
                    "operation": "deleted",
                    "reason": "temp_file"
                })
            else:
                processed_files.append({
                    "path": str(file_path),
                    "operation": "kept",
                    "reason": "not_temp"
                })

        except Exception as e:
            processed_files.append({
                "path": str(file_path),
                "error": str(e),
                "operation": "failed"
            })

    return {
        "cleaned_count": cleaned_count,
        "processed_files": processed_files
    }


async def _analyze_files(files: List[Path]) -> Dict[str, Any]:
    """分析文件"""
    total_size = 0
    file_types = {}
    processed_files = []

    for file_path in files:
        try:
            file_stat = file_path.stat()
            file_size = file_stat.st_size
            total_size += file_size

            suffix = file_path.suffix.lower()
            if suffix:
                if suffix not in file_types:
                    file_types[suffix] = {"count": 0, "size": 0}
                file_types[suffix]["count"] += 1
                file_types[suffix]["size"] += file_size

            processed_files.append({
                "path": str(file_path),
                "size": file_size,
                "modified": file_stat.st_mtime,
                "type": suffix or "unknown"
            })

        except Exception as e:
            processed_files.append({
                "path": str(file_path),
                "error": str(e)
            })

    # 按大小排序文件类型
    sorted_types = sorted(
        file_types.items(),
        key=lambda x: x[1]["size"],
        reverse=True
    )

    return {
        "total_files": len(files),
        "total_size": total_size,
        "file_types": dict(sorted_types[:10]),  # 只返回前10种类型
        "processed_files": processed_files[:50]  # 限制返回数量
    }


async def _move_to_target(files: List[Path], target_dir: str) -> Dict[str, Any]:
    """移动文件到目标目录"""
    moved_count = 0
    processed_files = []
    target_path = Path(target_dir)
    target_path.mkdir(exist_ok=True)

    for file_path in files:
        try:
            target_file = target_path / file_path.name
            if file_path != target_file:
                shutil.move(str(file_path), str(target_file))
                moved_count += 1
                processed_files.append({
                    "path": str(target_file),
                    "original_path": str(file_path),
                    "operation": "moved"
                })
            else:
                processed_files.append({
                    "path": str(file_path),
                    "operation": "already_in_target"
                })

        except Exception as e:
            processed_files.append({
                "path": str(file_path),
                "error": str(e),
                "operation": "failed"
            })

    return {
        "moved_count": moved_count,
        "processed_files": processed_files
    }


async def _copy_to_target(files: List[Path], target_dir: str) -> Dict[str, Any]:
    """复制文件到目标目录"""
    copied_count = 0
    processed_files = []
    target_path = Path(target_dir)
    target_path.mkdir(exist_ok=True)

    for file_path in files:
        try:
            target_file = target_path / file_path.name
            if not target_file.exists():
                shutil.copy2(str(file_path), str(target_file))
                copied_count += 1
                processed_files.append({
                    "path": str(target_file),
                    "original_path": str(file_path),
                    "operation": "copied"
                })
            else:
                processed_files.append({
                    "path": str(file_path),
                    "operation": "already_exists"
                })

        except Exception as e:
            processed_files.append({
                "path": str(file_path),
                "error": str(e),
                "operation": "failed"
            })

    return {
        "copied_count": copied_count,
        "processed_files": processed_files
    }