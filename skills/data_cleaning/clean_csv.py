"""
数据清洗技能实现
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
import os


async def clean_csv(file_path: str,
                    operations: List[str],
                    output_path: Optional[str] = None,
                    missing_method: str = "mean",
                    outlier_columns: Optional[List[str]] = None,
                    outlier_threshold: float = 3.0) -> Dict[str, Any]:
    """
    清洗CSV数据文件

    Args:
        file_path: CSV文件路径
        operations: 要执行的操作列表
        output_path: 输出文件路径
        missing_method: 缺失值填充方法（mean, median, mode, drop）
        outlier_columns: 要检测异常值的列
        outlier_threshold: 异常值阈值（Z-score）

    Returns:
        清洗结果
    """
    try:
        if not os.path.exists(file_path):
            return {"success": False, "error": f"文件不存在: {file_path}"}

        df = pd.read_csv(file_path)
        original_rows = len(df)
        operations_performed = []
        removed_count = 0

        for op in operations:
            if op == "remove_duplicates":
                before = len(df)
                df = df.drop_duplicates()
                removed_count += (before - len(df))
                operations_performed.append(f"去除重复行: {before - len(df)} 行")

            elif op == "fill_missing":
                before_missing = df.isnull().sum().sum()
                if missing_method == "drop":
                    df = df.dropna()
                else:
                    numeric_cols = df.select_dtypes(include=[np.number]).columns
                    for col in numeric_cols:
                        if df[col].isnull().any():
                            if missing_method == "mean":
                                df[col] = df[col].fillna(df[col].mean())
                            elif missing_method == "median":
                                df[col] = df[col].fillna(df[col].median())
                            elif missing_method == "mode":
                                df[col] = df[col].fillna(df[col].mode().iloc[0] if len(df[col].mode()) > 0 else df[col].mean())
                operations_performed.append(f"填充缺失值: {before_missing} -> {df.isnull().sum().sum()}")

            elif op == "normalize_text":
                text_cols = df.select_dtypes(include=['object']).columns
                for col in text_cols:
                    df[col] = df[col].astype(str).str.strip().str.lower()
                operations_performed.append(f"标准化文本列: {list(text_cols)}")

            elif op == "remove_outliers" and outlier_columns:
                before_outliers = len(df)
                for col in outlier_columns:
                    if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
                        z_scores = np.abs((df[col] - df[col].mean()) / df[col].std())
                        df = df[z_scores < outlier_threshold]
                removed_count += (before_outliers - len(df))
                operations_performed.append(f"移除异常值: {before_outliers - len(df)} 行")

            elif op == "convert_types":
                for col in df.columns:
                    if df[col].dtype == 'object':
                        numeric_cols = ['id', 'age', 'score', 'amount', 'price', 'count', 'qty']
                        if any(nc in col.lower() for nc in numeric_cols):
                            df[col] = pd.to_numeric(df[col], errors='ignore')
                operations_performed.append("尝试转换数据类型")

        output = output_path or file_path
        df.to_csv(output, index=False)

        return {
            "success": True,
            "file_path": output,
            "original_rows": original_rows,
            "final_rows": len(df),
            "rows_removed": removed_count,
            "operations_performed": operations_performed,
            "columns": list(df.columns),
            "data_types": {col: str(dtype) for col, dtype in df.dtypes.items()}
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
