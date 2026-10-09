import sys
import os
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
# 配置区：后续新增项目、修改输入列名或输出名称，优先只改这里
# ============================================================

SPEC_MIN = 13.0
SPEC_MAX = 15.0
DECIMAL_PLACES = 3

SN_COLUMN = "SN"
TIME_COLUMN = "Onekey_Open Test End Time"

# 每一项就是最终输出中的一条 FAI 记录，列表顺序也是输出顺序。
#
# 字段说明：
# enabled      是否启用该项目
# output       输出到 FAI 列的名称
# operation    计算方式，支持：
#              direct / abs_diff / difference / average /
#              sum / min / max / multiply / divide
# inputs       原始数据中的输入列名
# spec_check   是否进行 Spec 检查
# spec_min/max 可选；不填写时使用全局 SPEC_MIN / SPEC_MAX
#
# 只修改输出名称的示例：
# 把 output: "FAI112_1" 改成 output: "FAI0112_Z1" 即可，
# 输入仍然从 FAI112-1 抓取，UniqueID 也会自动同步使用新名称。
ITEM_CONFIG: List[Dict[str, Any]] = [
    {
        "enabled": True,
        "output": "FAI112.4",
        "operation": "direct",
        "inputs": ["FAI112-4"],
        "spec_check": True,
    },
    {
        "enabled": True,
        "output": "FAI112.3",
        "operation": "direct",
        "inputs": ["FAI112-3"],
        "spec_check": True,
    },
    {
        "enabled": True,
        "output": "FAI112.2",
        "operation": "direct",
        "inputs": ["FAI112-2"],
        "spec_check": True,
    },
    {
        "enabled": True,
        "output": "FAI112.1",
        "operation": "direct",
        "inputs": ["FAI112-1"],
        "spec_check": True,
    },
    {
        "enabled": True,
        "output": "FAI112_1/4",
        "operation": "abs_diff",
        "inputs": ["FAI112-4", "FAI112-1"],
        "spec_check": False,
    },
    {
        "enabled": True,
        "output": "Ave(FAI112_1+112_4)",
        "operation": "average",
        "inputs": ["FAI112-4", "FAI112-1"],
        "spec_check": False,
    },
    {
        "enabled": True,
        "output": "FAI115.1.20N",
        "operation": "average",
        "inputs": ["FAI115-1"],
        "spec_check": False,
    },
    {
        "enabled": True,
        "output": "FAI115.2.20N",
        "operation": "average",
        "inputs": ["FAI115-2"],
        "spec_check": False,
    },
    {
        "enabled": True,
        "output": "FAI115.3.20N",
        "operation": "average",
        "inputs": ["FAI115-3"],
        "spec_check": False,
    },
    {
        "enabled": True,
        "output": "FAI115.4.20N",
        "operation": "average",
        "inputs": ["FAI115-4"],
        "spec_check": False,
    },
    {
        "enabled": True,
        "output": "FAI116.1.20N",
        "operation": "average",
        "inputs": ["FAI116-1"],
        "spec_check": False,
    },
    {
        "enabled": True,
        "output": "FAI116.2.20N",
        "operation": "average",
        "inputs": ["FAI116-2"],
        "spec_check": False,
    },
    {
        "enabled": True,
        "output": "FAI116.3.20N",
        "operation": "average",
        "inputs": ["FAI116-3"],
        "spec_check": False,
    },
    {
        "enabled": True,
        "output": "FAI116.4.20N",
        "operation": "average",
        "inputs": ["FAI116-4"],
        "spec_check": False,
    },
    {
        "enabled": True,
        "output": "FAI 7_3_CV2",
        "operation": "average",
        "inputs": ["FAI 7_3_CV2 Free"],
        "spec_check": False,
    },
    {
        "enabled": True,
        "output": "FAI122.1",
        "operation": "average",
        "inputs": ["FAI122_1"],
        "spec_check": False,
    },

]

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
    "average": None,   # 允许两个或更多输入
    "sum": None,
    "min": None,
    "max": None,
    "multiply": None,
    "divide": 2,
}


# ============================================================
# 配置辅助函数
# ============================================================

def unique_in_order(values: Sequence[str]) -> List[str]:
    """按首次出现顺序去重。"""
    result: List[str] = []
    seen = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def get_enabled_items() -> List[Dict[str, Any]]:
    return [item for item in ITEM_CONFIG if item.get("enabled", True)]


def get_numeric_input_columns() -> List[str]:
    columns: List[str] = []
    for item in get_enabled_items():
        columns.extend(item["inputs"])
    return unique_in_order(columns)


def get_required_columns() -> List[str]:
    return unique_in_order([SN_COLUMN, TIME_COLUMN] + get_numeric_input_columns())


def get_spec_items() -> List[Dict[str, Any]]:
    return [item for item in get_enabled_items() if item.get("spec_check", False)]


def validate_item_config() -> None:
    """启动处理前检查配置，尽早发现配置错误。"""
    items = get_enabled_items()
    if not items:
        raise ValueError("ITEM_CONFIG 中没有启用的项目。")

    output_names: List[str] = []

    for index, item in enumerate(items, start=1):
        output_name = str(item.get("output", "")).strip()
        operation = str(item.get("operation", "")).strip()
        inputs = item.get("inputs")

        if not output_name:
            raise ValueError(f"ITEM_CONFIG 第 {index} 项缺少 output。")
        if output_name in output_names:
            raise ValueError(f"ITEM_CONFIG 的 output 重复：{output_name}")
        output_names.append(output_name)

        if operation not in SUPPORTED_OPERATIONS:
            raise ValueError(
                f"ITEM_CONFIG 第 {index} 项 operation 不支持：{operation}\n"
                f"支持的 operation：{', '.join(sorted(SUPPORTED_OPERATIONS))}"
            )

        if not isinstance(inputs, list) or not inputs:
            raise ValueError(f"ITEM_CONFIG 第 {index} 项 inputs 必须是非空列表。")
        if any(not str(col).strip() for col in inputs):
            raise ValueError(f"ITEM_CONFIG 第 {index} 项 inputs 含空列名。")

        required_count = OPERATION_INPUT_COUNTS[operation]
        if required_count is not None and len(inputs) != required_count:
            raise ValueError(
                f"ITEM_CONFIG 第 {index} 项 operation={operation} "
                f"要求 {required_count} 个输入列，当前为 {len(inputs)} 个。"
            )

        if operation in {"average", "sum", "min", "max", "multiply"} and len(inputs) < 1:
            raise ValueError(
                f"ITEM_CONFIG 第 {index} 项 operation={operation} 至少需要 1 个输入列。"
            )

        if item.get("spec_check", False):
            spec_min = item.get("spec_min", SPEC_MIN)
            spec_max = item.get("spec_max", SPEC_MAX)
            if spec_min >= spec_max:
                raise ValueError(
                    f"ITEM_CONFIG 第 {index} 项 Spec 范围无效："
                    f"spec_min={spec_min}, spec_max={spec_max}"
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
# 数据校验与格式处理
# ============================================================

def validate_required_columns(df: pd.DataFrame) -> None:
    required_columns = get_required_columns()
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ValueError(
            "输入文件缺少必要列：\n"
            + "\n".join(missing)
            + "\n\n请检查原始数据表头或 ITEM_CONFIG 中的 inputs 是否正确。"
        )


def convert_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """根据 ITEM_CONFIG 自动转换所有参与输出/计算的输入列。"""
    result = df.copy()
    for column in get_numeric_input_columns():
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def format_test_start_time(series: pd.Series) -> pd.Series:
    """
    将 Onekey_Open Test End Time 格式化为 ISO 8601（东八区）。
    例如：2025-12-24T17:46:00+08:00

    无时区的原始时间按东八区本地时间处理；
    已带时区的时间统一转换到东八区。
    """

    def to_iso8601(value: Any) -> Any:
        if pd.isna(value):
            return pd.NA

        timestamp = pd.to_datetime(value, errors="coerce")
        if pd.isna(timestamp):
            return pd.NA

        timestamp = pd.Timestamp(timestamp)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("Asia/Shanghai")
        else:
            timestamp = timestamp.tz_convert("Asia/Shanghai")

        return timestamp.isoformat()

    return series.apply(to_iso8601)


def normalize_batch_date(date_text: str) -> str:
    """
    将 GUI 输入日期转换为 YYYYMMDD。
    支持 2026/04/08、2026-04-08、2026.04.08 等格式。
    """
    dt = pd.to_datetime(date_text, errors="coerce")
    if pd.isna(dt):
        raise ValueError("BatchID 日期格式无效，请输入如 2026/04/08 或 2026-04-08")
    return pd.Timestamp(dt).strftime("%Y%m%d")


def build_batch_id(config_value: str, batch_date_text: str) -> str:
    """BatchID = Config#YYYYMMDD。"""
    return f"{config_value}#{normalize_batch_date(batch_date_text)}"


# ============================================================
# 项目计算
# ============================================================

def calculate_item_value(row: pd.Series, item: Dict[str, Any]) -> Any:
    """根据配置计算单个项目。"""
    operation = item["operation"]
    values = [row[column] for column in item["inputs"]]

    # 任一输入无法转换为数字时，计算结果保持为空。
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

    # validate_item_config 已提前拦截，正常情况下不会走到这里。
    raise ValueError(f"不支持的 operation：{operation}")


# ============================================================
# Spec 检查
# ============================================================

def check_spec(df_numeric: pd.DataFrame) -> Tuple[bool, pd.DataFrame]:
    """
    根据 ITEM_CONFIG 中 spec_check=True 的项目进行 Spec 检查。

    当前配置中四个直接尺寸仍按原逻辑检查 13.0~15.0；
    后续单个项目可在配置中增加 spec_min / spec_max 覆盖全局范围。
    """
    mask = pd.Series(False, index=df_numeric.index)
    check_columns: List[str] = []

    for item in get_spec_items():
        output_name = item["output"]
        values = df_numeric.apply(lambda row: calculate_item_value(row, item), axis=1)
        values = pd.to_numeric(values, errors="coerce")

        spec_min = float(item.get("spec_min", SPEC_MIN))
        spec_max = float(item.get("spec_max", SPEC_MAX))

        item_mask = values.isna() | (values < spec_min) | (values > spec_max)
        mask = mask | item_mask

        # 为异常报告保留动态计算值；避免多个输出使用同一个输入列时互相覆盖。
        report_column = f"__SPEC__{output_name}"
        df_numeric[report_column] = values
        check_columns.append(report_column)

    report_base_columns = [SN_COLUMN, TIME_COLUMN]
    bad_df = df_numeric.loc[mask, report_base_columns + check_columns].copy()
    bad_df["__DataFrameIndex__"] = bad_df.index

    return bad_df.empty, bad_df


def format_bad_rows_message(bad_df: pd.DataFrame, max_rows: int = 20) -> str:
    """将动态 Spec 异常行整理成日志文本。"""
    if bad_df.empty:
        return ""

    spec_items = get_spec_items()
    lines: List[str] = []

    for _, row in bad_df.head(max_rows).iterrows():
        # DataFrame 索引 0 通常对应 Excel 第 2 行（第 1 行为表头）。
        source_row = row.get("__DataFrameIndex__")
        try:
            excel_row = int(source_row) + 2
        except (TypeError, ValueError):
            excel_row = source_row

        parts = [
            f"ExcelRow={excel_row}",
            f"SN={row.get(SN_COLUMN, pd.NA)}",
            f"Time={row.get(TIME_COLUMN, pd.NA)}",
        ]

        for item in spec_items:
            output_name = item["output"]
            report_column = f"__SPEC__{output_name}"
            value = row.get(report_column, pd.NA)
            spec_min = item.get("spec_min", SPEC_MIN)
            spec_max = item.get("spec_max", SPEC_MAX)
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
    vendor_site_code: str,
    target_site_code: str,
    build_value: str,
    config_value: str,
    station_type: str,
    batch_date_text: str,
) -> pd.DataFrame:
    """按照 ITEM_CONFIG 顺序生成堆叠输出。"""
    df = df_numeric.copy()
    df["__TestStartTime__"] = format_test_start_time(df[TIME_COLUMN])
    batch_id_value = build_batch_id(config_value, batch_date_text)

    records: List[Dict[str, Any]] = []

    for _, row in df.iterrows():
        sn = row[SN_COLUMN]
        test_start_time = row["__TestStartTime__"]

        for item in get_enabled_items():
            fai_name = item["output"]
            measurement = calculate_item_value(row, item)

            records.append(
                {
                    "SerialNumber": sn,
                    "VendorSiteCode": vendor_site_code,
                    "TargetSiteCode": target_site_code,
                    "Build": build_value,
                    "Config": config_value,
                    "StationType": station_type,
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
    ).round(DECIMAL_PLACES)

    return df_out


def save_output(df_out: pd.DataFrame, output_path: str) -> None:
    suffix = Path(output_path).suffix.lower()
    if suffix != ".csv":
        raise ValueError("输出文件必须为 .csv 格式")

    df_out.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
        float_format=f"%.{DECIMAL_PLACES}f",
    )


# ============================================================
# GUI
# ============================================================

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FAI 配置化堆叠输出工具")
        self.resize(950, 650)
        self.init_ui()

    def init_ui(self) -> None:
        self.input_label = QLabel("原始数据文件：")
        self.input_edit = QLineEdit()
        self.input_btn = QPushButton("选择文件")
        self.input_btn.clicked.connect(self.select_input_file)

        self.build_label = QLabel("Build：")
        self.build_edit = QLineEdit()

        self.config_label = QLabel("Config：")
        self.config_edit = QLineEdit()

        self.batch_date_label = QLabel("BatchID日期：")
        self.batch_date_edit = QLineEdit()
        self.batch_date_edit.setPlaceholderText("例如 2026/04/08")

        self.vendor_label = QLabel("VendorSiteCode：")
        self.vendor_edit = QLineEdit("AMHU")

        self.target_label = QLabel("TargetSiteCode：")
        self.target_edit = QLineEdit("IPLH")

        self.station_label = QLabel("StationType：")
        self.station_edit = QLineEdit("AOI")

        self.output_label = QLabel("输出CSV文件：")
        self.output_edit = QLineEdit()
        self.output_btn = QPushButton("选择输出路径")
        self.output_btn.clicked.connect(self.select_output_file)

        self.spec_label = QLabel(self.build_spec_label_text())

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.run_btn = QPushButton("开始转换")
        self.run_btn.clicked.connect(self.run_process)

        grid = QGridLayout()
        grid.addWidget(self.input_label, 0, 0)
        grid.addWidget(self.input_edit, 0, 1)
        grid.addWidget(self.input_btn, 0, 2)

        grid.addWidget(self.build_label, 1, 0)
        grid.addWidget(self.build_edit, 1, 1)

        grid.addWidget(self.config_label, 2, 0)
        grid.addWidget(self.config_edit, 2, 1)

        grid.addWidget(self.batch_date_label, 3, 0)
        grid.addWidget(self.batch_date_edit, 3, 1)

        grid.addWidget(self.vendor_label, 4, 0)
        grid.addWidget(self.vendor_edit, 4, 1)

        grid.addWidget(self.target_label, 5, 0)
        grid.addWidget(self.target_edit, 5, 1)

        grid.addWidget(self.station_label, 6, 0)
        grid.addWidget(self.station_edit, 6, 1)

        grid.addWidget(self.output_label, 7, 0)
        grid.addWidget(self.output_edit, 7, 1)
        grid.addWidget(self.output_btn, 7, 2)

        grid.addWidget(self.spec_label, 8, 0, 1, 3)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.run_btn)

        main_layout = QVBoxLayout()
        main_layout.addLayout(grid)
        main_layout.addWidget(QLabel("运行日志："))
        main_layout.addWidget(self.log_text)
        main_layout.addLayout(btn_layout)

        self.setLayout(main_layout)

    @staticmethod
    def build_spec_label_text() -> str:
        items = get_spec_items()
        if not items:
            return "Spec检查：未启用"

        descriptions = []
        for item in items:
            spec_min = item.get("spec_min", SPEC_MIN)
            spec_max = item.get("spec_max", SPEC_MAX)
            descriptions.append(f"{item['output']}({spec_min}~{spec_max})")

        return "Spec检查：" + "；".join(descriptions)

    def log(self, text: str) -> None:
        self.log_text.append(text)

    def select_input_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择原始数据文件",
            "",
            "Data Files (*.csv *.xlsx *.xls)",
        )
        if file_path:
            self.input_edit.setText(file_path)

            input_file = Path(file_path)
            default_output = input_file.with_name(input_file.stem + "_stack_output.csv")
            if not self.output_edit.text().strip():
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
        input_path = self.input_edit.text().strip()
        output_path = self.output_edit.text().strip()
        build_value = self.build_edit.text().strip()
        config_value = self.config_edit.text().strip()
        batch_date_text = self.batch_date_edit.text().strip()
        vendor_site_code = self.vendor_edit.text().strip()
        target_site_code = self.target_edit.text().strip()
        station_type = self.station_edit.text().strip()

        self.log_text.clear()

        try:
            validate_item_config()

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
            if not vendor_site_code:
                raise ValueError("VendorSiteCode 不能为空。")
            if not target_site_code:
                raise ValueError("TargetSiteCode 不能为空。")
            if not station_type:
                raise ValueError("StationType 不能为空。")

            normalize_batch_date(batch_date_text)

            self.log("开始读取原始数据...")
            df_raw = try_read_table(input_path)
            self.log(f"读取成功，数据维度：{df_raw.shape[0]} 行 × {df_raw.shape[1]} 列")

            validate_required_columns(df_raw)
            self.log(
                f"配置读取成功：启用 {len(get_enabled_items())} 个输出项目，"
                f"涉及 {len(get_numeric_input_columns())} 个数值输入列。"
            )

            df_numeric = convert_numeric(df_raw)

            if get_spec_items():
                self.log("开始进行 Spec 检查...")
                ok, bad_df = check_spec(df_numeric)

                if not ok:
                    error_text = format_bad_rows_message(bad_df, max_rows=20)
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
                self.log("ITEM_CONFIG 未启用 Spec 检查，已跳过。")

            self.log("开始生成配置化堆叠输出...")
            df_out = build_output_dataframe(
                df_numeric=df_numeric,
                vendor_site_code=vendor_site_code,
                target_site_code=target_site_code,
                build_value=build_value,
                config_value=config_value,
                station_type=station_type,
                batch_date_text=batch_date_text,
            )

            self.log(f"输出数据维度：{df_out.shape[0]} 行 × {df_out.shape[1]} 列")
            self.log("开始保存 CSV 文件...")
            save_output(df_out, output_path)

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
