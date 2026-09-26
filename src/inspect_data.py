import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"


def find_latest_file(pattern: str) -> Path:
    """尋找指定類型最新下載的原始檔。"""
    files = list(RAW_DATA_DIR.glob(pattern))

    if not files:
        raise FileNotFoundError(f"找不到檔案：{pattern}")

    return max(files, key=lambda path: path.stat().st_mtime)


def load_records(file_path: Path) -> list[dict]:
    """讀取先前保存的 TDCC 原始 JSON。"""
    with file_path.open("r", encoding="utf-8") as file:
        document = json.load(file)

    payload = document["payload"]

    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ("data", "records", "result"):
            records = payload.get(key)

            if isinstance(records, list):
                return records

    raise ValueError(f"無法辨識資料結構：{file_path}")


def clean_column_names(dataframe: pd.DataFrame) -> pd.DataFrame:
    """移除欄位名稱的 BOM 與前後空白。"""
    dataframe = dataframe.copy()
    dataframe.columns = [
        str(column).replace("\ufeff", "").strip()
        for column in dataframe.columns
    ]
    return dataframe


def count_missing(series: pd.Series) -> int:
    """同時計算空值及空白字串。"""
    normalized = series.astype("string").str.strip()
    return int((normalized.isna() | normalized.eq("")).sum())


def main():
    master_file = find_latest_file("bond_master_*.json")
    cashflow_file = find_latest_file("cashflow_*.json")

    master = clean_column_names(
        pd.DataFrame(load_records(master_file))
    )
    cashflow = clean_column_names(
        pd.DataFrame(load_records(cashflow_file))
    )

    master_codes = (
        master["債券代號"]
        .dropna()
        .astype("string")
        .str.strip()
    )

    cashflow_codes = (
        cashflow["債券代號"]
        .dropna()
        .astype("string")
        .str.strip()
    )

    master_code_set = set(master_codes)
    cashflow_code_set = set(cashflow_codes)
    unmatched_codes = sorted(cashflow_code_set - master_code_set)

    matched_rows = cashflow_codes.isin(master_code_set).sum()
    match_rate = matched_rows / len(cashflow) * 100

    report_lines = [
        "TDCC 資料品質檢查報告",
        "=" * 50,
        f"債券主檔：{master_file.name}",
        f"現金流檔：{cashflow_file.name}",
        "",
        f"債券主檔筆數：{len(master):,}",
        f"現金流筆數：{len(cashflow):,}",
        "",
        f"主檔債券代號缺漏：{count_missing(master['債券代號']):,}",
        f"主檔 ISIN 缺漏：{count_missing(master['ISIN Code']):,}",
        f"主檔重複債券代號列數："
        f"{master_codes.duplicated(keep=False).sum():,}",
        f"主檔重複 ISIN 列數："
        f"{master['ISIN Code'].astype('string').str.strip().duplicated(keep=False).sum():,}",
        "",
        f"現金流債券代號缺漏：{count_missing(cashflow['債券代號']):,}",
        f"成功對應主檔的現金流：{matched_rows:,}",
        f"現金流連接成功率：{match_rate:.2f}%",
        f"找不到主檔的債券代號數：{len(unmatched_codes):,}",
        f"未對應代號範例：{unmatched_codes[:10]}",
        "",
        "債券主檔前 3 筆：",
        master.head(3).to_string(index=False),
        "",
        "現金流前 3 筆：",
        cashflow.head(3).to_string(index=False),
    ]

    report = "\n".join(report_lines)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    report_path = PROCESSED_DATA_DIR / "data_quality_report.txt"
    report_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"\n報告已保存：{report_path}")


if __name__ == "__main__":
    main()