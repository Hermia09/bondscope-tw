import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
DATABASE_PATH = PROJECT_ROOT / "data" / "bondscope.db"


def find_latest_file(pattern: str) -> Path:
    files = list(RAW_DATA_DIR.glob(pattern))

    if not files:
        raise FileNotFoundError(f"找不到檔案：{pattern}")

    return max(files, key=lambda path: path.stat().st_mtime)


def load_document(file_path: Path):
    with file_path.open("r", encoding="utf-8") as file:
        document = json.load(file)

    payload = document["payload"]

    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = None

        for key in ("data", "records", "result"):
            if isinstance(payload.get(key), list):
                records = payload[key]
                break

        if records is None:
            raise ValueError(f"無法辨識資料結構：{file_path}")
    else:
        raise ValueError(f"無法辨識資料結構：{file_path}")

    dataframe = pd.DataFrame(records)
    dataframe.columns = [
        str(column).replace("\ufeff", "").strip()
        for column in dataframe.columns
    ]

    return document, dataframe


def normalize_text(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip()
    return values.mask(values.eq(""))


def normalize_date(series: pd.Series) -> pd.Series:
    values = normalize_text(series)
    parsed = pd.to_datetime(
        values,
        format="%Y%m%d",
        errors="coerce",
    )
    return parsed.dt.strftime("%Y-%m-%d")


def normalize_number(series: pd.Series) -> pd.Series:
    values = (
        series.astype("string")
        .str.replace(",", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(values, errors="coerce")


def replace_missing_with_none(dataframe: pd.DataFrame) -> pd.DataFrame:
    dataframe = dataframe.astype(object)
    return dataframe.where(pd.notna(dataframe), None)


def create_database_schema(connection: sqlite3.Connection):
    connection.execute("PRAGMA foreign_keys = ON")

    connection.executescript(
        """
        DROP TABLE IF EXISTS cashflow_events;
        DROP TABLE IF EXISTS data_quality_issues;
        DROP TABLE IF EXISTS bonds;
        DROP TABLE IF EXISTS import_batches;

        CREATE TABLE import_batches (
            batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
            imported_at TEXT NOT NULL,
            source_date TEXT,
            master_filename TEXT NOT NULL,
            cashflow_filename TEXT NOT NULL,
            master_rows INTEGER NOT NULL,
            cashflow_rows INTEGER NOT NULL,
            imported_cashflow_rows INTEGER NOT NULL,
            issue_count INTEGER NOT NULL
        );

        CREATE TABLE bonds (
            bond_code TEXT PRIMARY KEY,
            isin TEXT,
            bond_name TEXT,
            bond_short_name TEXT,
            currency TEXT,
            issue_date TEXT,
            maturity_date TEXT,
            coupon_rate REAL,
            rate_type TEXT,
            redemption_method TEXT,
            issue_par_code TEXT,
            registrar TEXT,
            paying_agent TEXT,
            source_date TEXT,
            import_batch_id INTEGER NOT NULL,
            FOREIGN KEY (import_batch_id)
                REFERENCES import_batches(batch_id)
        );

        CREATE TABLE cashflow_events (
            cashflow_id INTEGER PRIMARY KEY AUTOINCREMENT,
            bond_code TEXT NOT NULL,
            payment_sequence TEXT,
            scheduled_payment_date TEXT,
            actual_payment_date TEXT,
            interest_amount REAL,
            principal_amount REAL,
            minimum_amount_or_total_issue REAL,
            source_date TEXT,
            import_batch_id INTEGER NOT NULL,
            FOREIGN KEY (bond_code)
                REFERENCES bonds(bond_code),
            FOREIGN KEY (import_batch_id)
                REFERENCES import_batches(batch_id)
        );

        CREATE TABLE data_quality_issues (
            issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_type TEXT NOT NULL,
            dataset_name TEXT NOT NULL,
            record_key TEXT,
            details_json TEXT NOT NULL,
            detected_at TEXT NOT NULL,
            import_batch_id INTEGER NOT NULL,
            FOREIGN KEY (import_batch_id)
                REFERENCES import_batches(batch_id)
        );

        CREATE INDEX idx_bonds_isin
            ON bonds(isin);

        CREATE INDEX idx_cashflow_bond_code
            ON cashflow_events(bond_code);

        CREATE INDEX idx_cashflow_payment_date
            ON cashflow_events(scheduled_payment_date);
        """
    )


def main():
    master_file = find_latest_file("bond_master_*.json")
    cashflow_file = find_latest_file("cashflow_*.json")

    _, master_raw = load_document(master_file)
    _, cashflow_raw = load_document(cashflow_file)

    bonds = pd.DataFrame(
        {
            "bond_code": normalize_text(master_raw["債券代號"]),
            "isin": normalize_text(master_raw["ISIN Code"]),
            "bond_name": normalize_text(master_raw["債券名稱"]),
            "bond_short_name": normalize_text(master_raw["債券簡稱"]),
            "currency": normalize_text(master_raw["幣別"]),
            "issue_date": normalize_date(master_raw["發行日期"]),
            "maturity_date": normalize_date(master_raw["到期日"]),
            "coupon_rate": normalize_number(master_raw["利率"]),
            "rate_type": normalize_text(master_raw["利率別"]),
            "redemption_method": normalize_text(master_raw["還本方式"]),
            "issue_par_code": normalize_text(master_raw["發行面額"]),
            "registrar": normalize_text(master_raw["登錄機構"]),
            "paying_agent": normalize_text(
                master_raw["本息兌領機構名稱"]
            ),
            "source_date": normalize_date(master_raw["資料日期"]),
        }
    )

    cashflows_all = pd.DataFrame(
        {
            "bond_code": normalize_text(cashflow_raw["債券代號"]),
            "payment_sequence": normalize_text(
                cashflow_raw["還本付息期次"]
            ),
            "scheduled_payment_date": normalize_date(
                cashflow_raw["還本付息日"]
            ),
            "actual_payment_date": normalize_date(
                cashflow_raw["實際付款日"]
            ),
            "interest_amount": normalize_number(
                cashflow_raw["付息金額"]
            ),
            "principal_amount": normalize_number(
                cashflow_raw["還本金額"]
            ),
            "minimum_amount_or_total_issue": normalize_number(
                cashflow_raw["最小發行面額/發行總額"]
            ),
            "source_date": normalize_date(cashflow_raw["資料日期"]),
        }
    )

    valid_bond_codes = set(bonds["bond_code"].dropna())
    matched_mask = cashflows_all["bond_code"].isin(valid_bond_codes)

    cashflows = cashflows_all[matched_mask].copy()
    unmatched_cashflows = cashflows_all[~matched_mask].copy()

    detected_at = datetime.now(
        ZoneInfo("Asia/Taipei")
    ).isoformat()

    issues = []

    for row in bonds[bonds["isin"].isna()].itertuples():
        issues.append(
            {
                "issue_type": "MISSING_ISIN",
                "dataset_name": "bond_master",
                "record_key": row.bond_code,
                "details_json": json.dumps(
                    {
                        "bond_code": row.bond_code,
                        "bond_name": row.bond_name,
                    },
                    ensure_ascii=False,
                ),
                "detected_at": detected_at,
            }
        )

    for row in unmatched_cashflows.itertuples():
        issues.append(
            {
                "issue_type": "ORPHAN_CASHFLOW",
                "dataset_name": "cashflow",
                "record_key": (
                    f"{row.bond_code}:{row.payment_sequence}"
                ),
                "details_json": json.dumps(
                    {
                        "bond_code": row.bond_code,
                        "payment_sequence": row.payment_sequence,
                        "scheduled_payment_date":
                            row.scheduled_payment_date,
                        "interest_amount": row.interest_amount,
                        "principal_amount": row.principal_amount,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                "detected_at": detected_at,
            }
        )

    valid_isins = bonds["isin"].dropna()
    duplicate_isins = set(
        valid_isins[
            valid_isins.duplicated(keep=False)
        ]
    )

    for isin in sorted(duplicate_isins):
        duplicate_rows = bonds[bonds["isin"] == isin]

        for row in duplicate_rows.itertuples():
            issues.append(
                {
                    "issue_type": "DUPLICATE_ISIN",
                    "dataset_name": "bond_master",
                    "record_key": row.bond_code,
                    "details_json": json.dumps(
                        {
                            "isin": isin,
                            "bond_code": row.bond_code,
                            "bond_name": row.bond_name,
                        },
                        ensure_ascii=False,
                    ),
                    "detected_at": detected_at,
                }
            )

    source_dates = bonds["source_date"].dropna()
    source_date = (
        source_dates.max()
        if not source_dates.empty
        else None
    )

    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DATABASE_PATH) as connection:
        create_database_schema(connection)

        cursor = connection.execute(
            """
            INSERT INTO import_batches (
                imported_at,
                source_date,
                master_filename,
                cashflow_filename,
                master_rows,
                cashflow_rows,
                imported_cashflow_rows,
                issue_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                detected_at,
                source_date,
                master_file.name,
                cashflow_file.name,
                len(bonds),
                len(cashflows_all),
                len(cashflows),
                len(issues),
            ),
        )

        batch_id = cursor.lastrowid

        bonds["import_batch_id"] = batch_id
        cashflows["import_batch_id"] = batch_id

        issues_dataframe = pd.DataFrame(issues)
        issues_dataframe["import_batch_id"] = batch_id

        replace_missing_with_none(bonds).to_sql(
            "bonds",
            connection,
            if_exists="append",
            index=False,
        )

        replace_missing_with_none(cashflows).to_sql(
            "cashflow_events",
            connection,
            if_exists="append",
            index=False,
        )

        replace_missing_with_none(issues_dataframe).to_sql(
            "data_quality_issues",
            connection,
            if_exists="append",
            index=False,
        )

    print("SQLite 資料庫建立成功")
    print(f"資料庫位置：{DATABASE_PATH}")
    print(f"債券主檔：{len(bonds):,} 筆")
    print(f"已匯入現金流：{len(cashflows):,} 筆")
    print(f"未匯入孤立現金流：{len(unmatched_cashflows):,} 筆")
    print(f"資料品質問題：{len(issues):,} 筆")
    print(f"有效重複 ISIN 種類：{len(duplicate_isins):,}")


if __name__ == "__main__":
    main()