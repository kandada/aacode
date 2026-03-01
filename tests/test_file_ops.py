import pytest
import asyncio
import tempfile
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.file_ops import FileOps


class TestFileOps:
    """测试文件操作工具类"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.asyncio
    async def test_read_file(self, temp_dir):
        """测试读取文件"""
        test_file = temp_dir / "test.txt"
        test_content = "Hello, World!"
        test_file.write_text(test_content)

        result = await FileOps.read_file(test_file)
        assert result == test_content

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, temp_dir):
        """测试读取不存在的文件"""
        test_file = temp_dir / "nonexistent.txt"

        with pytest.raises(FileNotFoundError):
            await FileOps.read_file(test_file)

    @pytest.mark.asyncio
    async def test_write_file(self, temp_dir):
        """测试写入文件"""
        test_file = temp_dir / "write_test.txt"
        test_content = "Test content"

        result = await FileOps.write_file(test_file, test_content)
        assert result is True
        assert test_file.read_text() == test_content

    @pytest.mark.asyncio
    async def test_write_file_append(self, temp_dir):
        """测试追加写入文件"""
        test_file = temp_dir / "append_test.txt"
        test_file.write_text("Line 1\n")

        await FileOps.write_file(test_file, "Line 2\n", append=True)
        
        content = test_file.read_text()
        assert "Line 1" in content
        assert "Line 2" in content

    @pytest.mark.asyncio
    async def test_delete_file(self, temp_dir):
        """测试删除文件"""
        test_file = temp_dir / "delete_test.txt"
        test_file.write_text("To be deleted")

        result = await FileOps.delete_file(test_file)
        assert result is True
        assert not test_file.exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file(self, temp_dir):
        """测试删除不存在的文件"""
        test_file = temp_dir / "nonexistent.txt"

        # delete_file在文件不存在时返回True
        result = await FileOps.delete_file(test_file)
        assert result is True

    @pytest.mark.asyncio
    async def test_copy_file(self, temp_dir):
        """测试复制文件"""
        source = temp_dir / "source.txt"
        dest = temp_dir / "dest.txt"
        source.write_text("Copy me")

        result = await FileOps.copy_file(source, dest)
        assert result is True
        assert dest.read_text() == "Copy me"

    @pytest.mark.asyncio
    async def test_move_file(self, temp_dir):
        """测试移动文件"""
        source = temp_dir / "source.txt"
        dest = temp_dir / "moved.txt"
        source.write_text("Move me")

        result = await FileOps.move_file(source, dest)
        assert result is True
        assert not source.exists()
        assert dest.read_text() == "Move me"

    @pytest.mark.asyncio
    async def test_create_directory(self, temp_dir):
        """测试创建目录"""
        new_dir = temp_dir / "new_dir"

        result = await FileOps.create_dir(new_dir)
        assert result is True
        assert new_dir.exists()
        assert new_dir.is_dir()

    @pytest.mark.asyncio
    async def test_list_directory(self, temp_dir):
        """测试列出目录内容"""
        (temp_dir / "file1.txt").write_text("content1")
        (temp_dir / "file2.txt").write_text("content2")
        (temp_dir / "subdir").mkdir()

        result = await FileOps.list_files(temp_dir)
        assert len(result) == 2
        assert "file1.txt" in result
        assert "file2.txt" in result

    @pytest.mark.asyncio
    async def test_get_file_info(self, temp_dir):
        """测试获取文件信息"""
        test_file = temp_dir / "info_test.txt"
        test_content = "Test content for info"
        test_file.write_text(test_content)

        size = await FileOps.get_file_size(test_file)
        
        assert size > 0

    @pytest.mark.asyncio
    async def test_calculate_file_hash(self, temp_dir):
        """测试计算文件哈希"""
        test_file = temp_dir / "hash_test.txt"
        test_file.write_text("Content for hashing")

        hash_result = await FileOps.get_file_hash(test_file)
        
        assert hash_result is not None
        assert len(hash_result) > 0

    @pytest.mark.asyncio
    async def test_batch_write_files(self, temp_dir):
        """测试批量写入文件"""
        files_content = {
            "file1.txt": "Content 1",
            "file2.txt": "Content 2",
            "subdir/file3.txt": "Content 3"
        }

        for file_path, content in files_content.items():
            full_path = temp_dir / file_path
            if "subdir" in file_path:
                await FileOps.create_dir(full_path.parent)
            await FileOps.write_file(full_path, content)
        
        assert (temp_dir / "file1.txt").read_text() == "Content 1"
        assert (temp_dir / "file2.txt").read_text() == "Content 2"
        assert (temp_dir / "subdir/file3.txt").read_text() == "Content 3"
