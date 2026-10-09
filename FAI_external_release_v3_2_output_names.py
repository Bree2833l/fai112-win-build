import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QTextEdit,
    QSizePolicy,
)


# ============================================================
# 程序常量
# ============================================================
APP_TITLE = "To9045 堆叠输出工具"
CONFIG_FILE_NAME = "config.json"
SUPPORTED_CONFIG_MAJOR_VERSION = "1"

OUTPUT_COLUMNS = [
    "SerialNumber",
    "VendorSiteCode",
    "TargetSiteCode",
    "Build",
    "Config",
    "StationType",
    "TestStartTime",
    "FAI",
    "Measurement",
    "UniqueID",
    "BatchID",
]

SUPPORTED_OPERATIONS = {
    "direct",
    "abs_diff",
    "difference",
    "average",
    "sum",
    "min",
    "max",
    "multiply",
    "divide",
}

OPERATION_INPUT_COUNTS = {
    "direct": 1,
    "abs_diff": 2,
    "difference": 2,
    "average": None,
    "sum": None,
    "min": None,
    "max": None,
    "multiply": None,
    "divide": 2,
}


# ============================================================
# 外部配置读取
# ============================================================
def get_app_dir() -> Path:
    """
    获取程序所在目录。

    - 普通 .py 运行：返回脚本所在目录
    - PyInstaller EXE：返回 EXE 所在目录

    config.json 固定放在这个目录下，因此打包后无需写入 EXE 内部。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_config_path() -> Path:
    return get_app_dir() / CONFIG_FILE_NAME


def load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(
            f"未找到配置文件：\n{config_path}\n\n"
            f"请将 {CONFIG_FILE_NAME} 放在程序/EXE同一文件夹内。"
        )

    try:
        with config_path.open("r", encoding="utf-8-sig") as f:
            config = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"配置文件 JSON 格式错误：\n{config_path}\n\n"
            f"第 {exc.lineno} 行，第 {exc.colno} 列：{exc.msg}"
        ) from exc

    validate_config(config)
    return config


def validate_config(config: Dict[str, Any]) -> None:
    """启动时校验 config.json，尽早发现维护配置时的错误。"""
    if not isinstance(config, dict):
        raise ValueError("config.json 顶层必须是 JSON Object。")

    version = str(config.get("config_version", "")).strip()
    if not version:
        raise ValueError("config.json 缺少 config_version。")
    if version.split(".")[0] != SUPPORTED_CONFIG_MAJOR_VERSION:
        raise ValueError(
            f"不支持的 config_version：{version}\n"
            f"当前程序支持主版本：{SUPPORTED_CONFIG_MAJOR_VERSION}.x"
        )

    required_text_fields = [
        "vendor_site_code",
        "target_site_code",
        "station_type",
        "sn_column",
        "time_column",
        "output_suffix",
        "timezone",
    ]
    for key in required_text_fields:
        value = config.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"config.json 字段 {key} 必须是非空字符串。")

    sn_validation = config.get("sn_validation")
    if not isinstance(sn_validation, dict):
        raise ValueError("config.json 缺少 sn_validation，或其格式不是 JSON Object。")

    sn_validation_enabled = sn_validation.get("enabled", True)
    if not isinstance(sn_validation_enabled, bool):
        raise ValueError("sn_validation.enabled 必须是 true 或 false。")

    required_prefix = sn_validation.get("required_prefix")
    if not isinstance(required_prefix, str) or not required_prefix.strip():
        raise ValueError("sn_validation.required_prefix 必须是非空字符串。")

    required_length = sn_validation.get("required_length")
    if not isinstance(required_length, int) or required_length <= 0:
        raise ValueError("sn_validation.required_length 必须是大于 0 的整数。")

    decimal_places = config.get("decimal_places")
    if not isinstance(decimal_places, int) or not (0 <= decimal_places <= 10):
        raise ValueError("decimal_places 必须是 0~10 的整数。")

    default_spec_min = config.get("default_spec_min")
    default_spec_max = config.get("default_spec_max")
    if not isinstance(default_spec_min, (int, float)) or not isinstance(default_spec_max, (int, float)):
        raise ValueError("default_spec_min/default_spec_max 必须是数字。")
    if default_spec_min >= default_spec_max:
        raise ValueError("default_spec_min 必须小于 default_spec_max。")

    output_suffix = config["output_suffix"].strip()
    if not output_suffix.lower().endswith(".csv"):
        raise ValueError("output_suffix 必须以 .csv 结尾。")

    items = config.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("config.json 中 items 必须是非空列表。")

    enabled_items = [item for item in items if isinstance(item, dict) and item.get("enabled", True)]
    if not enabled_items:
        raise ValueError("config.json 中没有启用的输出项目。")

    seen_outputs = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"items 第 {index} 项必须是 JSON Object。")

        if not item.get("enabled", True):
            continue

        output_name = str(item.get("output", "")).strip()
        operation = str(item.get("operation", "")).strip()
        inputs = item.get("inputs")

        if not output_name:
            raise ValueError(f"items 第 {index} 项缺少 output。")
        if output_name in seen_outputs:
            raise ValueError(f"items 中 output 重复：{output_name}")
        seen_outputs.add(output_name)

        if operation not in SUPPORTED_OPERATIONS:
            raise ValueError(
                f"items 第 {index} 项 operation 不支持：{operation}\n"
                f"支持：{', '.join(sorted(SUPPORTED_OPERATIONS))}"
            )

        if not isinstance(inputs, list) or not inputs:
            raise ValueError(f"items 第 {index} 项 inputs 必须是非空列表。")
        if any(not isinstance(col, str) or not col.strip() for col in inputs):
            raise ValueError(f"items 第 {index} 项 inputs 含空列名或非字符串列名。")

        required_count = OPERATION_INPUT_COUNTS[operation]
        if required_count is not None and len(inputs) != required_count:
            raise ValueError(
                f"items 第 {index} 项 operation={operation} "
                f"要求 {required_count} 个 inputs，当前为 {len(inputs)} 个。"
            )

        if item.get("spec_check", False):
            spec_min = item.get("spec_min", default_spec_min)
            spec_max = item.get("spec_max", default_spec_max)
            if not isinstance(spec_min, (int, float)) or not isinstance(spec_max, (int, float)):
                raise ValueError(f"items 第 {index} 项 spec_min/spec_max 必须是数字。")
            if spec_min >= spec_max:
                raise ValueError(
                    f"items 第 {index} 项 Spec 范围无效："
                    f"spec_min={spec_min}, spec_max={spec_max}"
                )


def unique_in_order(values: Sequence[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def get_enabled_items(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [item for item in config["items"] if item.get("enabled", True)]


def get_output_item_names(config: Dict[str, Any]) -> List[str]:
    """按 config.json 中的顺序返回所有启用项目的输出名称。"""
    return [str(item["output"]).strip() for item in get_enabled_items(config)]


def get_spec_items(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [item for item in get_enabled_items(config) if item.get("spec_check", False)]


def get_numeric_input_columns(config: Dict[str, Any]) -> List[str]:
    columns: List[str] = []
    for item in get_enabled_items(config):
        columns.extend(item["inputs"])
    return unique_in_order(columns)


def get_required_columns(config: Dict[str, Any]) -> List[str]:
    return unique_in_order(
        [config["sn_column"], config["time_column"]] + get_numeric_input_columns(config)
    )


# ============================================================
# 文件读取
# ============================================================
def try_read_csv(file_path: str) -> pd.DataFrame:
    """自动尝试多种编码读取 CSV。"""
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb18030", "latin1"]
    last_error: Optional[Exception] = None

    for encoding in encodings:
        try:
            return pd.read_csv(file_path, encoding=encoding)
        except Exception as exc:
            last_error = exc

    raise ValueError(f"无法读取文件，已尝试多种编码仍失败：{last_error}")


def try_read_table(file_path: str) -> pd.DataFrame:
    """支持读取 csv / xlsx / xls。"""
    suffix = Path(file_path).suffix.lower()

    if suffix == ".csv":
        return try_read_csv(file_path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(file_path)

    raise ValueError(f"不支持的输入文件格式：{suffix}，请使用 csv / xlsx / xls")


# ============================================================
# 数据校验 / 格式处理
# ============================================================
def validate_required_columns(df: pd.DataFrame, config: Dict[str, Any]) -> None:
    missing = [column for column in get_required_columns(config) if column not in df.columns]
    if missing:
        raise ValueError(
            "输入文件缺少必要列：\n"
            + "\n".join(missing)
            + "\n\n请检查原始数据表头或 config.json 中 items.inputs 是否正确。"
        )


def normalize_sn_series(series: pd.Series) -> pd.Series:
    """
    将 SN 统一按字符串处理，并去除首尾空格。
    空值保持为 <NA>，避免被转换成字符串 "nan"。
    """
    return series.astype("string").str.strip()


def validate_sn_values(
    df: pd.DataFrame,
    config: Dict[str, Any],
) -> Tuple[bool, pd.DataFrame]:
    """
    校验 SN：
    1. 必须非空
    2. 必须以 config.json 中 required_prefix 开头
    3. 长度必须等于 required_length

    默认配置：CYV 开头、48 位。
    """
    rule = config["sn_validation"]
    if not rule.get("enabled", True):
        return True, pd.DataFrame()

    sn_column = config["sn_column"]
    required_prefix = rule["required_prefix"].strip()
    required_length = int(rule["required_length"])

    normalized = normalize_sn_series(df[sn_column])

    valid_mask = (
        normalized.notna()
        & normalized.ne("")
        & normalized.str.startswith(required_prefix, na=False)
        & normalized.str.len().eq(required_length)
    )

    invalid_df = pd.DataFrame(index=df.index[~valid_mask])
    invalid_df[sn_column] = normalized.loc[~valid_mask]
    invalid_df["__DataFrameIndex__"] = invalid_df.index

    def reason_for(value: Any) -> str:
        if pd.isna(value) or str(value).strip() == "":
            return "SN为空"
        value = str(value).strip()
        reasons: List[str] = []
        if not value.startswith(required_prefix):
            reasons.append(f"不是以 {required_prefix} 开头")
        if len(value) != required_length:
            reasons.append(f"长度为 {len(value)}，要求 {required_length} 位")
        return "；".join(reasons) if reasons else "SN格式不符合要求"

    invalid_df["__Reason__"] = [
        reason_for(value) for value in invalid_df[sn_column].tolist()
    ]

    return invalid_df.empty, invalid_df


def format_invalid_sn_message(
    invalid_df: pd.DataFrame,
    config: Dict[str, Any],
    max_rows: int = 20,
) -> str:
    if invalid_df.empty:
        return ""

    sn_column = config["sn_column"]
    lines: List[str] = []

    for _, row in invalid_df.head(max_rows).iterrows():
        source_row = row.get("__DataFrameIndex__")
        try:
            excel_row = int(source_row) + 2
        except (TypeError, ValueError):
            excel_row = source_row

        lines.append(
            f"ExcelRow={excel_row}, SN={row.get(sn_column, pd.NA)}, "
            f"原因={row.get('__Reason__', '')}"
        )

    if len(invalid_df) > max_rows:
        lines.append(f"... 其余还有 {len(invalid_df) - max_rows} 行未展示")

    return "\n".join(lines)


def convert_numeric(df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
    result = df.copy()

    # SN 输出前统一去除首尾空格，确保验证值与最终输出一致。
    result[config["sn_column"]] = normalize_sn_series(result[config["sn_column"]])

    for column in get_numeric_input_columns(config):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def format_test_start_time(series: pd.Series, timezone_name: str) -> pd.Series:
    """
    将原始 Test End Time 格式化为 ISO 8601。
    默认 config.json 使用 Asia/Shanghai，即 +08:00。
    """

    def to_iso8601(value: Any) -> Any:
        if pd.isna(value):
            return pd.NA

        timestamp = pd.to_datetime(value, errors="coerce")
        if pd.isna(timestamp):
            return pd.NA

        timestamp = pd.Timestamp(timestamp)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(timezone_name)
        else:
            timestamp = timestamp.tz_convert(timezone_name)

        return timestamp.isoformat()

    return series.apply(to_iso8601)


def normalize_batch_date(date_text: str) -> str:
    """将 GUI 输入日期转换为 YYYYMMDD。"""
    dt = pd.to_datetime(date_text, errors="coerce")
    if pd.isna(dt):
        raise ValueError("BatchID 日期格式无效，请输入如 2026/04/08 或 2026-04-08")
    return pd.Timestamp(dt).strftime("%Y%m%d")


def build_batch_id(config_value: str, batch_date_text: str) -> str:
    return f"{config_value}#{normalize_batch_date(batch_date_text)}"


# ============================================================
# 项目计算
# ============================================================
def calculate_item_value(row: pd.Series, item: Dict[str, Any]) -> Any:
    operation = item["operation"]
    values = [row[column] for column in item["inputs"]]

    if any(pd.isna(value) for value in values):
        return pd.NA

    if operation == "direct":
        return values[0]
    if operation == "abs_diff":
        return abs(values[0] - values[1])
    if operation == "difference":
        return values[0] - values[1]
    if operation == "average":
        return sum(values) / len(values)
    if operation == "sum":
        return sum(values)
    if operation == "min":
        return min(values)
    if operation == "max":
        return max(values)
    if operation == "multiply":
        result = 1
        for value in values:
            result *= value
        return result
    if operation == "divide":
        if values[1] == 0:
            return pd.NA
        return values[0] / values[1]

    raise ValueError(f"不支持的 operation：{operation}")


# ============================================================
# Spec 检查
# ============================================================
def check_spec(df_numeric: pd.DataFrame, config: Dict[str, Any]) -> Tuple[bool, pd.DataFrame]:
    """后台 Spec 检查。GUI 不再固定展示 Spec 信息。"""
    mask = pd.Series(False, index=df_numeric.index)
    check_columns: List[str] = []

    default_spec_min = float(config["default_spec_min"])
    default_spec_max = float(config["default_spec_max"])

    report_df = df_numeric.copy()

    for item in get_spec_items(config):
        output_name = item["output"]
        values = report_df.apply(lambda row: calculate_item_value(row, item), axis=1)
        values = pd.to_numeric(values, errors="coerce")

        spec_min = float(item.get("spec_min", default_spec_min))
        spec_max = float(item.get("spec_max", default_spec_max))

        item_mask = values.isna() | (values < spec_min) | (values > spec_max)
        mask = mask | item_mask

        report_column = f"__SPEC__{output_name}"
        report_df[report_column] = values
        check_columns.append(report_column)

    sn_column = config["sn_column"]
    time_column = config["time_column"]
    bad_df = report_df.loc[mask, [sn_column, time_column] + check_columns].copy()
    bad_df["__DataFrameIndex__"] = bad_df.index

    return bad_df.empty, bad_df


def format_bad_rows_message(
    bad_df: pd.DataFrame,
    config: Dict[str, Any],
    max_rows: int = 20,
) -> str:
    if bad_df.empty:
        return ""

    sn_column = config["sn_column"]
    time_column = config["time_column"]
    default_spec_min = config["default_spec_min"]
    default_spec_max = config["default_spec_max"]

    lines: List[str] = []

    for _, row in bad_df.head(max_rows).iterrows():
        source_row = row.get("__DataFrameIndex__")
        try:
            excel_row = int(source_row) + 2
        except (TypeError, ValueError):
            excel_row = source_row

        parts = [
            f"ExcelRow={excel_row}",
            f"SN={row.get(sn_column, pd.NA)}",
            f"Time={row.get(time_column, pd.NA)}",
        ]

        for item in get_spec_items(config):
            output_name = item["output"]
            report_column = f"__SPEC__{output_name}"
            value = row.get(report_column, pd.NA)
            spec_min = item.get("spec_min", default_spec_min)
            spec_max = item.get("spec_max", default_spec_max)
            parts.append(f"{output_name}={value} (Spec:{spec_min}~{spec_max})")

        lines.append(", ".join(parts))

    if len(bad_df) > max_rows:
        lines.append(f"... 其余还有 {len(bad_df) - max_rows} 行未展示")

    return "\n".join(lines)


# ============================================================
# 输出生成
# ============================================================
def build_output_dataframe(
    df_numeric: pd.DataFrame,
    config: Dict[str, Any],
    build_value: str,
    config_value: str,
    batch_date_text: str,
) -> pd.DataFrame:
    df = df_numeric.copy()

    time_column = config["time_column"]
    sn_column = config["sn_column"]

    df["__TestStartTime__"] = format_test_start_time(
        df[time_column],
        config["timezone"],
    )
    batch_id_value = build_batch_id(config_value, batch_date_text)

    records: List[Dict[str, Any]] = []

    for _, row in df.iterrows():
        sn = row[sn_column]
        test_start_time = row["__TestStartTime__"]

        for item in get_enabled_items(config):
            fai_name = item["output"]
            measurement = calculate_item_value(row, item)

            records.append(
                {
                    "SerialNumber": sn,
                    "VendorSiteCode": config["vendor_site_code"],
                    "TargetSiteCode": config["target_site_code"],
                    "Build": build_value,
                    "Config": config_value,
                    "StationType": config["station_type"],
                    "TestStartTime": test_start_time,
                    "FAI": fai_name,
                    "Measurement": measurement,
                    "UniqueID": f"{sn}_{fai_name}",
                    "BatchID": batch_id_value,
                }
            )

    df_out = pd.DataFrame(records, columns=OUTPUT_COLUMNS)
    df_out["Measurement"] = pd.to_numeric(
        df_out["Measurement"], errors="coerce"
    ).round(config["decimal_places"])

    return df_out


def save_output(df_out: pd.DataFrame, output_path: str, config: Dict[str, Any]) -> None:
    suffix = Path(output_path).suffix.lower()
    if suffix != ".csv":
        raise ValueError("输出文件必须为 .csv 格式")

    df_out.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
        float_format=f"%.{config['decimal_places']}f",
    )


# ============================================================
# GUI
# ============================================================
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.config_path = get_config_path()
        self.app_config: Optional[Dict[str, Any]] = None
        self.config_error: Optional[str] = None

        try:
            self.app_config = load_config(self.config_path)
        except Exception as exc:
            self.config_error = str(exc)

        self.setWindowTitle(APP_TITLE)
        self.resize(950, 610)
        self.init_ui()
        self.apply_loaded_config()

    def init_ui(self) -> None:
        self.input_label = QLabel("原始数据文件：")
        self.input_edit = QLineEdit()
        self.input_btn = QPushButton("选择文件")
        self.input_btn.clicked.connect(self.select_input_file)

        self.output_label = QLabel("输出CSV文件：")
        self.output_edit = QLineEdit()
        self.output_btn = QPushButton("选择输出路径")
        self.output_btn.clicked.connect(self.select_output_file)

        self.build_label = QLabel("Build：")
        self.build_edit = QLineEdit()

        self.config_label = QLabel("Config：")
        self.config_edit = QLineEdit()

        self.batch_date_label = QLabel("BatchID日期：")
        self.batch_date_edit = QLineEdit()
        self.batch_date_edit.setPlaceholderText("例如 2026/04/08")

        self.vendor_label = QLabel("VendorSiteCode：")
        self.vendor_edit = QLineEdit()
        self.vendor_edit.setReadOnly(True)

        self.target_label = QLabel("TargetSiteCode：")
        self.target_edit = QLineEdit()
        self.target_edit.setReadOnly(True)

        self.station_label = QLabel("StationType：")
        self.station_edit = QLineEdit()
        self.station_edit.setReadOnly(True)

        self.config_status_label = QLabel("配置：尚未加载")
        self.config_status_label.setWordWrap(True)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.run_btn = QPushButton("开始转换")
        self.run_btn.clicked.connect(self.run_process)

        grid = QGridLayout()
        grid.addWidget(self.input_label, 0, 0)
        grid.addWidget(self.input_edit, 0, 1)
        grid.addWidget(self.input_btn, 0, 2)

        grid.addWidget(self.output_label, 1, 0)
        grid.addWidget(self.output_edit, 1, 1)
        grid.addWidget(self.output_btn, 1, 2)

        grid.addWidget(self.build_label, 2, 0)
        grid.addWidget(self.build_edit, 2, 1)

        grid.addWidget(self.config_label, 3, 0)
        grid.addWidget(self.config_edit, 3, 1)

        grid.addWidget(self.batch_date_label, 4, 0)
        grid.addWidget(self.batch_date_edit, 4, 1)

        grid.addWidget(self.vendor_label, 5, 0)
        grid.addWidget(self.vendor_edit, 5, 1)

        grid.addWidget(self.target_label, 6, 0)
        grid.addWidget(self.target_edit, 6, 1)

        grid.addWidget(self.station_label, 7, 0)
        grid.addWidget(self.station_edit, 7, 1)

        grid.addWidget(self.config_status_label, 8, 0, 1, 3)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.run_btn)

        main_layout = QVBoxLayout()
        main_layout.addLayout(grid)
        main_layout.addWidget(QLabel("运行日志："))
        main_layout.addWidget(self.log_text)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def apply_loaded_config(self) -> None:
        """将 config.json 中的固定参数显示到只读 GUI，并显示加载状态。"""
        if self.app_config is None:
            self.vendor_edit.setText("配置加载失败")
            self.target_edit.setText("配置加载失败")
            self.station_edit.setText("配置加载失败")
            self.config_status_label.setText(f"配置：加载失败 | {self.config_path}")
            self.run_btn.setEnabled(False)
            self.log_text.setPlainText(f"[CONFIG ERROR]\n{self.config_error}")
            QMessageBox.critical(self, "配置文件错误", self.config_error or "未知配置错误")
            return

        self.vendor_edit.setText(self.app_config["vendor_site_code"])
        self.target_edit.setText(self.app_config["target_site_code"])
        self.station_edit.setText(self.app_config["station_type"])

        output_names = get_output_item_names(self.app_config)
        output_text = "、".join(output_names)

        self.config_status_label.setText(
            f"配置：{self.config_path.name} | 输出项目：{output_text}"
        )
        self.log_text.setPlainText(
            "配置加载成功。\n"
            f"配置文件：{self.config_path}\n"
            f"输出项目：{output_text}\n"
            f"VendorSiteCode：{self.app_config['vendor_site_code']}\n"
            f"TargetSiteCode：{self.app_config['target_site_code']}\n"
            f"StationType：{self.app_config['station_type']}\n"
            f"SN规则：{self.app_config['sn_validation']['required_prefix']} 开头，"
            f"长度 {self.app_config['sn_validation']['required_length']} 位"
        )

    def log(self, text: str) -> None:
        self.log_text.append(text)

    def select_input_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择原始数据文件",
            "",
            "Data Files (*.csv *.xlsx *.xls)",
        )
        if not file_path:
            return

        self.input_edit.setText(file_path)

        # 每一次选择原始数据文件，都重新生成默认输出路径。
        # 不再只在输出栏为空时才生成。
        input_file = Path(file_path)
        suffix = self.app_config["output_suffix"] if self.app_config else "_stack_output.csv"
        default_output = input_file.with_name(input_file.stem + suffix)
        self.output_edit.setText(str(default_output))

    def select_output_file(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "选择输出CSV文件",
            self.output_edit.text().strip() or "FAI_stack_output.csv",
            "CSV Files (*.csv)",
        )
        if file_path:
            if not file_path.lower().endswith(".csv"):
                file_path += ".csv"
            self.output_edit.setText(file_path)

    def run_process(self) -> None:
        if self.app_config is None:
            QMessageBox.critical(
                self,
                "配置文件错误",
                self.config_error or "配置文件未正确加载。",
            )
            return

        input_path = self.input_edit.text().strip()
        output_path = self.output_edit.text().strip()
        build_value = self.build_edit.text().strip()
        config_value = self.config_edit.text().strip()
        batch_date_text = self.batch_date_edit.text().strip()

        self.log_text.clear()
        output_text = "、".join(get_output_item_names(self.app_config))
        self.log(
            f"配置加载：{self.config_path}\n"
            f"输出项目：{output_text}"
        )

        try:
            # 每次运行前再次校验，允许用户在程序未关闭时修改 JSON 后重新启动程序使用。
            # 当前版本固定在启动时载入，因此若修改 config.json，需要重启程序。
            validate_config(self.app_config)

            if not input_path:
                raise ValueError("请选择原始数据文件。")
            if not os.path.exists(input_path):
                raise FileNotFoundError(f"输入文件不存在：{input_path}")
            if not output_path:
                raise ValueError("请选择输出路径。")
            if not output_path.lower().endswith(".csv"):
                raise ValueError("输出文件必须为 .csv 格式。")
            if not build_value:
                raise ValueError("请输入 Build。")
            if not config_value:
                raise ValueError("请输入 Config。")
            if not batch_date_text:
                raise ValueError("请输入 BatchID 日期。")

            normalize_batch_date(batch_date_text)

            self.log("开始读取原始数据...")
            df_raw = try_read_table(input_path)
            self.log(f"读取成功，数据维度：{df_raw.shape[0]} 行 × {df_raw.shape[1]} 列")

            validate_required_columns(df_raw, self.app_config)
            self.log(
                f"输入字段检查通过：涉及 {len(get_numeric_input_columns(self.app_config))} 个数值输入列。"
            )

            # SN 格式验证：默认要求 48 位，且以 CYV 开头。
            sn_rule = self.app_config["sn_validation"]
            if sn_rule.get("enabled", True):
                self.log(
                    f"开始进行 SN 检查：必须以 {sn_rule['required_prefix']} 开头，"
                    f"长度必须为 {sn_rule['required_length']} 位..."
                )
                sn_ok, invalid_sn_df = validate_sn_values(df_raw, self.app_config)
                if not sn_ok:
                    error_text = format_invalid_sn_message(
                        invalid_sn_df,
                        self.app_config,
                        max_rows=20,
                    )
                    self.log(f"发现 {len(invalid_sn_df)} 行 SN 格式异常，已中止输出。")
                    self.log(error_text)

                    QMessageBox.critical(
                        self,
                        "SN 检查失败",
                        f"发现 {len(invalid_sn_df)} 行 SN 不符合要求。\n"
                        f"要求：以 {sn_rule['required_prefix']} 开头，"
                        f"长度 {sn_rule['required_length']} 位。\n\n"
                        f"前 20 行如下：\n{error_text}",
                    )
                    return

                self.log("SN 检查通过。")
            else:
                self.log("配置未启用 SN 检查，已跳过。")

            df_numeric = convert_numeric(df_raw, self.app_config)

            if get_spec_items(self.app_config):
                self.log("开始进行 Spec 检查...")
                ok, bad_df = check_spec(df_numeric, self.app_config)

                if not ok:
                    error_text = format_bad_rows_message(
                        bad_df,
                        self.app_config,
                        max_rows=20,
                    )
                    self.log("发现超出 Spec 或无法转换为数字的记录，已中止输出。")
                    self.log(error_text)

                    QMessageBox.critical(
                        self,
                        "Spec 检查失败",
                        f"发现 {len(bad_df)} 行超出 Spec 或包含空值/非数字，"
                        f"程序已中止输出。\n\n前 20 行如下：\n{error_text}",
                    )
                    return

                self.log("Spec 检查通过。")
            else:
                self.log("配置未启用 Spec 检查，已跳过。")

            self.log("开始生成堆叠输出...")
            df_out = build_output_dataframe(
                df_numeric=df_numeric,
                config=self.app_config,
                build_value=build_value,
                config_value=config_value,
                batch_date_text=batch_date_text,
            )

            self.log(f"输出数据维度：{df_out.shape[0]} 行 × {df_out.shape[1]} 列")
            self.log("开始保存 CSV 文件...")
            save_output(df_out, output_path, self.app_config)

            self.log(f"保存成功：{output_path}")
            QMessageBox.information(self, "完成", f"输出成功：\n{output_path}")

        except Exception as exc:
            self.log(f"[ERROR] {exc}")
            QMessageBox.critical(self, "错误", str(exc))


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
